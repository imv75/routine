#!/usr/bin/env python3
"""Scrape University of South Carolina course catalog from CourseLeaf bulletin."""
import re, csv, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests

PROXY = 'http://127.0.0.1:43429'
CA = '/root/.ccr/ca-bundle.crt'
BASE = 'https://academicbulletins.sc.edu'
COURSES_INDEX = BASE + '/undergraduate/course-descriptions/'
NAME = 'University of South Carolina'
KEY = 'sc'
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

HUMANITIES_D = {'AFAM','ARAB','ARTH','ARTS','CHIN','CLAS','CPLT','CRWT','DANC',
    'DMSB','ENGL','FILM','FREN','GERM','GREK','HIST','ITAL','JAPN','JRTM','LATN',
    'LING','MUSC','MUSP','MUTH','PHIL','PORT','RELI','RUSS','SIGN','SPAN','THEA',
    'WGST','WRIT','LGLS','HUM','ASL','ASLG','ART',}
SOCIAL_D = {'ANTH','CRJU','ECON','EDCE','EDCS','EDEC','EDEL','EDEX','EDFI','EDHE',
    'EDID','EDKN','EDLT','EDML','EDPY','EDRM','EDSE','EDST','ENVR','GEOG',
    'POLI','PSYC','SOC','SOCY','SPTE','SW','SOWK','COMM','JOUR','MGSC','MKTG',
    'RETL','SCHC','HPEB','HSPM','HRTM',}
STEM_D = {'ASTR','BCHE','BIOL','BMEN','BIOS','CHEM','COMD','CSCE','EMCH','ENGR',
    'ENHS','ENVT','GEOL','ITEC','MATH','MSCI','NURS','NURO','PHYS','STAT','SWAH',
    'BIOL','ECHE','ECIV','EELE','ELCT','AESP',}
PROFESSIONAL_D = {'ACCT','BLAW','DMSB','FINA','HOSP','HMGT','IBUS','MGMT','RETL',
    'SCHC','SPTE','HRTM','HSPM','MARK','MKTG','MGSC','FINC','FMBA',}
MEDICAL_D = {'NURS','NURO','PHCY','PHTH','RASC','RESP',}

def broad_area(dept):
    d = dept.upper()
    if d in MEDICAL_D: return 'Medical Sciences'
    if d in PROFESSIONAL_D: return 'Professional'
    if d in STEM_D: return 'STEM'
    if d in SOCIAL_D: return 'Social Sciences'
    if d in HUMANITIES_D: return 'Humanities'
    return 'Other'

def course_level(num):
    try:
        n = int(re.search(r'\d+', str(num)).group())
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
        if re.match(r'^/undergraduate/course-descriptions/[a-z]+/$', href):
            full = BASE + href
            if full not in seen:
                seen.add(full)
                urls.append(full)
    return urls


def parse_dept_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    courses = []
    for block in soup.find_all('div', class_='courseblock'):
        code_span = block.find('span', class_='detail-code')
        title_span = block.find('span', class_='detail-title')
        desc_div = block.find('div', class_='courseblockextra')
        if not code_span:
            continue
        code_text = code_span.get_text(strip=True)
        m = re.match(r'^([A-Z]+)\s+(\d+\w*)', code_text)
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = title_span.get_text(strip=True).lstrip('- ').strip() if title_span else ''
        desc = desc_div.get_text(' ', strip=True)[:2000] if desc_div else ''
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
        'notes': f'CourseLeaf HTML bulletin. AY={AY_LABEL}.',
    }
    prog['completed'] = sum(1 for v in prog['universities'].values() if v.get('status') == 'completed')
    import datetime
    prog['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    (ROOT / 'progress.json').write_text(json.dumps(prog, indent=2))
    print(f'progress.json: {KEY} → completed ({prog["completed"]} total)')


if __name__ == '__main__':
    main()
