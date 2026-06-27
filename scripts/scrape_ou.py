#!/usr/bin/env python3
"""Scrape University of Oklahoma course catalog from CourseLeaf."""
import re, csv, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests

PROXY = 'http://127.0.0.1:43429'
CA = '/root/.ccr/ca-bundle.crt'
BASE = 'https://ou-public.courseleaf.com'
COURSES_INDEX = BASE + '/courses/'
NAME = 'University of Oklahoma'
KEY = 'ou'
AY = '2024_2025'
AY_LABEL = '2024-2025'

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

HUMANITIES_D = {'AFAM','ART','ARTD','ARTH','ARTZ','CRIT','CRW','ENGL','FILM',
    'FLF','FR','GERM','GRLT','GRK','HIST','HON','HUM','IAS','ITAL','JPN',
    'LATN','LIB','LING','MUS','MUSP','MUTH','PHIL','PORT','REL','RUSS','SLAV',
    'SPAN','THE','THEA','WGS','WRIT','AMS','AMST','CL','CLASS','ENST',}
SOCIAL_D = {'ANTH','BCH','COM','ECON','EDU','EDLT','GEOG','GESP','IR','LSE',
    'NAMS','POL','POLS','PSY','PSYC','SCPH','SOC','SOCI','SWK','URP',}
STEM_D = {'AME','B','BCH','BIOL','CH','CHEM','CS','ECE','ENGR','GEOL','ISE',
    'MATH','MIC','OCS','PHYS','PMED','PNEU','STAT','AAI','ACS','AGSC',}
PROFESSIONAL_D = {'ACCT','AHS','ALD','AMGT','BUS','EDAH','EDLT','EDPS','EDSP',
    'FAIR','FIN','HES','HS','HTM','IMD','JMC','JOUR','LAW','LEAM','LEGM',
    'LSB','LSTD','MBA','MGT','MIS','MKT','NURS','OHR','OM','OPM','REAL',}

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


def get_dept_urls(sess):
    r = sess.get(COURSES_INDEX, timeout=15)
    soup = BeautifulSoup(r.text, 'html.parser')
    urls = []
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if re.match(r'^/courses/[a-z0-9]+/$', href):
            full = BASE + href
            if full not in seen:
                seen.add(full)
                urls.append(full)
    return urls


def parse_dept_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    courses = []
    for block in soup.find_all('div', class_='courseblock'):
        title_p = block.find('p', class_='courseblocktitle')
        desc_p = block.find('p', class_='courseblockdesc')
        if not title_p:
            continue
        # Format: <span class="courseblockcode"> ACCT 2113</span>. Course Title.
        code_span = title_p.find('span', class_='courseblockcode')
        if code_span:
            code_text = code_span.get_text(strip=True)
        else:
            code_text = title_p.get_text(strip=True)
        m = re.match(r'^([A-Z\s]+?)\s+(\d+\w*)', code_text.strip())
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        # Title: everything after the code span
        full_title_text = title_p.get_text(' ', strip=True)
        # Remove the code part and credits part
        title = re.sub(r'^[A-Z\s]+\s+\d+\w*\s*\.?\s*', '', full_title_text).strip()
        title = re.sub(r'\s*\d+\s*Credit\s*Hours?\s*\.?\s*$', '', title, flags=re.IGNORECASE).strip()
        title = title.rstrip('.')
        desc = desc_p.get_text(' ', strip=True)[:2000] if desc_p else ''
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


def fetch_dept(sess, url):
    try:
        r = sess.get(url, timeout=20)
        if r.status_code == 200:
            return parse_dept_page(r.text)
    except Exception as e:
        print(f'Error {url}: {e}', flush=True)
    return []


def main():
    if OUT_FILE.exists():
        print(f'Already exists: {OUT_FILE}')
        return

    sess = make_sess()
    print('Collecting department URLs...')
    dept_urls = get_dept_urls(sess)
    print(f'Found {len(dept_urls)} departments')

    print('Fetching course data (8 workers)...')
    all_courses = []
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_dept, sess, url): url for url in dept_urls}
        for fut in as_completed(futs):
            done += 1
            courses = fut.result()
            all_courses.extend(courses)
            if done % 30 == 0:
                print(f'  {done}/{len(dept_urls)} depts, {len(all_courses)} courses', flush=True)

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
        'notes': f'CourseLeaf HTML at ou-public.courseleaf.com. AY={AY_LABEL}.',
    }
    prog['completed'] = sum(1 for v in prog['universities'].values() if v.get('status') == 'completed')
    import datetime
    prog['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    (ROOT / 'progress.json').write_text(json.dumps(prog, indent=2))
    print(f'progress.json: {KEY} → completed ({prog["completed"]} total)')


if __name__ == '__main__':
    main()
