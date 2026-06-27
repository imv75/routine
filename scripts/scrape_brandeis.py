#!/usr/bin/env python3
"""Scrape Brandeis University course catalog from their online bulletin."""
import re, csv, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests

PROXY = 'http://127.0.0.1:43429'
CA = '/root/.ccr/ca-bundle.crt'
BASE = 'https://www.brandeis.edu/registrar/bulletin/2025-2026'
SUBJECTS_URL = BASE + '/courses/subjects/index.html'
NAME = 'Brandeis University'
KEY = 'brandeis'
AY = '2025_2026'
AY_LABEL = '2025-2026'

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / 'data' / KEY
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / f'{KEY}_{AY}.csv'

PROGRESSIVE_KEYWORDS = [
    'diversity','racial','racism','anti-racism','antiracism','equity','equitable',
    'inclusion','inclusive','belonging','systemic racism','white supremacy',
    'privilege','oppression','marginalized','colonialism','decolonize','decolonial',
    'indigenous knowledge','settler','intersectionality','social justice',
    'environmental justice','queer theory','queer studies','gender studies',
    'feminist','feminism','patriarchy','heteronormativity','transgender','latinx',
    'bipoc','positionality','lived experience','microaggression','implicit bias',
    'unconscious bias','allyship','critical race','whiteness','reparations',
    'abolition','anti-capitalist','land acknowledgment','liberation',
]
WESTERN_CANON_KEYWORDS = [
    'shakespeare','plato','aristotle','socrates','homer','virgil','dante','milton',
    'chaucer','cervantes','descartes','kant','hegel','nietzsche','locke','hobbes',
    'rousseau','voltaire','classical antiquity','ancient greece','ancient rome',
    'medieval philosophy','renaissance humanism','western civilization',
    'great books','socratic','platonic','stoicism','epicureanism','thomism',
    'scholasticism','classical literature','greek tragedy','roman history',
    'byzantine','augustine','aquinas',
]
CLIMATE_NARROW_KEYWORDS = [
    'climate change','global warming','greenhouse gas','carbon emission',
    'decarbonization','net zero','paris agreement','ipcc','sea level rise',
    'permafrost','carbon capture','carbon sequestration','climate model',
    'climate science','climate policy','climate adaptation','climate mitigation',
    'climate justice','climate refugee','climate crisis','fossil fuel',
]
CLIMATE_BROAD_KEYWORDS = [
    'sustainability','sustainable development','renewable energy','solar power',
    'wind energy','energy transition','clean energy','carbon footprint',
    'carbon neutral','environmental policy','environmental law','environmental science',
    'ecology','ecosystem','biodiversity','habitat loss','species extinction',
    'ocean acidification','air pollution','water scarcity','environmental degradation',
    'circular economy','environmental impact','environmental assessment',
    'sustainable agriculture','environmental ethics',
]

def sig(text, kws): return 1 if any(k in text.lower() for k in kws) else 0

HUMANITIES_D = {'ANTH','ARBC','CHIN','CLAS','COMP','ENG','FILM','FREN','GER','GREK',
    'HIST','HUM','ITS','JAPN','LATN','LGLS','LIT','MUS','NEJS','PAX','PHIL','PORT',
    'RUS','SPAN','THA','WGS','AAAS','AMST','IECS','AAPI','IGS','REL','ART','FA',}
SOCIAL_D = {'ANTH','ECON','ED','HWL','HS','NPSY','POL','PSYC','SOC','SAS','COSI',
    'NBIO','BI','BIO','BIOL','CHEM','GHS','HSSP','JOUR','LGLS','SL','SW',}
STEM_D = {'BCHM','BIOL','CHEM','COSI','MATH','NBIO','PHYS','PSYC','QBIO','SCI',
    'MRSM','BIO',}
PROFESSIONAL_D = {'BUS','IMES','MBA','ACC','FIN','MGT','MKT','OB','OM',}

def broad_area(dept):
    d = dept.upper()
    if d in PROFESSIONAL_D: return 'Professional'
    if d in STEM_D: return 'STEM'
    if d in SOCIAL_D: return 'Social Sciences'
    if d in HUMANITIES_D: return 'Humanities'
    return 'Other'

def course_level(num):
    try:
        n = int(re.search(r'\d+', str(num)).group())
        if n >= 1000:
            if n < 2000: return 'Lower'
            if n < 5000: return 'Upper'
            return 'Graduate'
        if n < 100: return 'Lower'
        if n < 200: return 'Lower'
        if n < 300: return 'Lower'
        if n < 500: return 'Upper'
        return 'Graduate'
    except: return 'Other'

CSV_FIELDS = ['university','academic_year','academic_year_label','department_code',
              'course_number','title','description','broad_area','level',
              'progressive_signal','western_canon_signal','climate_narrow_signal',
              'climate_broad_signal','cross_listed','deduplicated']


def make_sess():
    s = requests.Session()
    s.proxies = {'https': PROXY, 'http': PROXY}
    s.verify = CA
    s.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    return s


def get_subject_urls(sess):
    r = sess.get(SUBJECTS_URL, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    import urllib.parse
    urls = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('#'):
            continue
        resolved = urllib.parse.urljoin(SUBJECTS_URL, href)
        if ('/subjects/' in resolved and resolved.endswith('.html')
                and resolved != SUBJECTS_URL and 'index.html' not in resolved
                and resolved not in seen):
            seen.add(resolved)
            urls.append(resolved)
    return urls


def parse_subject_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    courses = []

    # Course entries are in <p> tags where the first child is <strong>DEPT NNN Title</strong>
    for p in soup.find_all('p'):
        strong = p.find('strong')
        if not strong:
            continue
        strong_text = strong.get_text(' ', strip=True)
        # Match: DEPT NNN[a/b] Title
        m = re.match(r'^([A-Z]{2,8})\s+(\d+[a-zA-Z]?)\s+(.+)$', strong_text.strip())
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = m.group(3).strip()

        # Description: text after the strong tag (skip bracket content like [qr ss])
        # The description is usually in a nested <p> or as text nodes
        desc = ''
        inner_p = p.find('p')
        if inner_p:
            desc = inner_p.get_text(' ', strip=True)
        else:
            # Get all text after strong
            all_text = p.get_text(' ', strip=True)
            # Remove the strong text portion
            after_strong = all_text[len(strong_text):].strip()
            # Remove requirement codes like [qr ss]
            after_strong = re.sub(r'\[.*?\]', '', after_strong).strip()
            desc = after_strong

        desc = desc[:2000]
        combined = f'{title} {desc}'

        courses.append({
            'dept_code': dept,
            'course_number': num,
            'title': title,
            'description': desc,
            'broad_area': broad_area(dept),
            'level': course_level(num),
            'progressive_signal': sig(combined, PROGRESSIVE_KEYWORDS),
            'western_canon_signal': sig(combined, WESTERN_CANON_KEYWORDS),
            'climate_narrow_signal': sig(combined, CLIMATE_NARROW_KEYWORDS),
            'climate_broad_signal': sig(combined, CLIMATE_BROAD_KEYWORDS),
            'cross_listed': 0,
            'deduplicated': 0,
        })

    return courses


def fetch_subject(sess, url):
    try:
        r = sess.get(url, timeout=20)
        if r.status_code == 200:
            return parse_subject_page(r.text)
    except Exception as e:
        print(f'Error {url}: {e}', flush=True)
    return []


def main():
    if OUT_FILE.exists():
        print(f'Already exists: {OUT_FILE}')
        return

    sess = make_sess()
    print('Collecting subject URLs...')
    subject_urls = get_subject_urls(sess)
    print(f'Found {len(subject_urls)} subject pages')

    print('Fetching course data (5 workers)...')
    all_courses = []
    done = 0
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fetch_subject, sess, url): url for url in subject_urls}
        for fut in as_completed(futs):
            done += 1
            courses = fut.result()
            all_courses.extend(courses)
            if done % 10 == 0:
                print(f'  {done}/{len(subject_urls)} pages, {len(all_courses)} courses', flush=True)

    print(f'Total courses: {len(all_courses)}')

    rows = []
    for course in all_courses:
        if course['dept_code'] or course['title']:
            rows.append({
                'university': NAME,
                'academic_year': AY,
                'academic_year_label': AY_LABEL,
                'department_code': course['dept_code'],
                'course_number': course['course_number'],
                'title': course['title'],
                'description': course['description'],
                'broad_area': course['broad_area'],
                'level': course['level'],
                'progressive_signal': course['progressive_signal'],
                'western_canon_signal': course['western_canon_signal'],
                'climate_narrow_signal': course['climate_narrow_signal'],
                'climate_broad_signal': course['climate_broad_signal'],
                'cross_listed': 0, 'deduplicated': 0,
            })

    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerows(rows)
    print(f'Saved: {OUT_FILE} ({len(rows)} courses)')

    prog = json.loads((ROOT / 'progress.json').read_text())
    if KEY in prog.get('dynamic_js_only', []):
        prog['dynamic_js_only'].remove(KEY)
    if KEY in prog.get('blocked_by_network', []):
        prog['blocked_by_network'].remove(KEY)
    prog['universities'][KEY] = {
        **prog['universities'].get(KEY, {}),
        'status': 'completed',
        'name': NAME,
        'data_files': [str(OUT_FILE)],
        'courses_count': len(rows),
        'progressive_pct': round(sum(1 for r in rows if r['progressive_signal']) / len(rows) * 100, 2) if rows else 0,
        'canon_pct': round(sum(1 for r in rows if r['western_canon_signal']) / len(rows) * 100, 2) if rows else 0,
        'notes': f'HTML bulletin scrape. AY={AY_LABEL}.',
    }
    prog['completed'] = sum(1 for v in prog['universities'].values() if v.get('status') == 'completed')
    import datetime
    prog['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    (ROOT / 'progress.json').write_text(json.dumps(prog, indent=2))
    print(f'progress.json: {KEY} → completed ({prog["completed"]} total)')


if __name__ == '__main__':
    main()
