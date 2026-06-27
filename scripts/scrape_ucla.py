#!/usr/bin/env python3
"""Scrape UCLA General Catalog from catalog.registrar.ucla.edu."""
import re, csv, json, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests

PROXY = 'http://127.0.0.1:43429'
CA = '/root/.ccr/ca-bundle.crt'
BASE = 'https://catalog.registrar.ucla.edu'
SITEMAP_BASE = BASE + '/sitemap-'
NAME = 'University of California, Los Angeles'
KEY = 'ucla'
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

HUMANITIES_D = {'AFRC','AHI','ANTHRO','AIS','ANG','AOS','ARABIC','ARCH','ARMS',
    'ART','ARTS','ARTHI','ASIAN','CHIN','CLASSIC','CLUSTER','COM','DANCE','DUTCH',
    'EE BIOL','ENGL','ETHNMUS','FILM','FREN','GJ','GERMAN','GLBL','GREEK','HEBREW',
    'HIST','HUM','HUNG','HNRS','IND','IRANIAN','ISLM','ITAL','JAPAN','JEWISH',
    'KOR','LATN','LBR STS','LGBTQS','LING','LPS','M PHARM','MATLBE',
    'MED','MESNM','MUS','NR EAST','PHILOS','PORTGSE','REL','ROM','RUSS',
    'SCAND','SEMITIC','SL SLAV','SPA','SPAN','THEATER','THA','UGS','UKRN',
    'VIET','WL ARTS','WI SEM','WOMN ST','YID',}
SOCIAL_D = {'AERO','AF AMER','AM IND','ANTHRO','ASIAN AM','BOT','CHICANO',
    'COM HLT','COMM','COMM ST','DIGSOC','ECON','EDUC','EPS','GENDER','GEOG',
    'GLBL ST','I E STDS','I STD','INTL DV','IS','LAW','LBR STS','LGBTQS',
    'MCD BIO','MGMT','MHS','MILS','POL SCI','PUB AFF','PUB HLT','PUB POL',
    'PSYCH','RES COG','SEMIOL','SOC','SOC TH','SOCIOL','STITCH','STS','SW',
    'URB PLN',}
STEM_D = {'A&O SCI','AERO','ANAT','ARCH','BE BIOL','BIOL','BIOMATH','BIOMED',
    'BMD RES','C&S BIO','C EE','CE','CHEM','C ENGR','CM','COM SCI','COM SCI',
    'C&S BIO','EC ENGR','ECE','EE','EL ENGR','ENGR','ENVIRON','EPS','GEN','GEOG',
    'GEO','HUM GEN','I ENG','LIFESCI','M ENG','MA ENG','MATH','MATLBE','M E','ME',
    'MED','MHI','MLS','MICRBIO','MOLBIO','MOL BIO','MS ENG','NEURO','NS','OB/GYN',
    'PHYSCI','PHYSICS','PHYSIOL','PUBHLT','RSTRS','STAT','SYS BIO','SYS ENGR',}
PROFESSIONAL_D = {'ACCTG','BUSN','CIVIL','ENV','FIN','GEN BUS','GLOB','HLT MG',
    'IM','INFO ST','INF SYS','IS','LAW','MGMT','MKT','NRS','PHARM','SOC WLF',}
MEDICAL_D = {'ANESTHES','DENT','MED','NURS','OB/GYN','OBGYN','OPHTH','PATH',
    'PEDS','PHARM','PHYSIOL','PSYCH','PUB HLT','RAD','SURG','UROL',}

def broad_area(dept):
    d = dept.upper().strip()
    if d in MEDICAL_D: return 'Medical Sciences'
    if d in PROFESSIONAL_D: return 'Professional'
    if d in STEM_D: return 'STEM'
    if d in SOCIAL_D: return 'Social Sciences'
    if d in HUMANITIES_D: return 'Humanities'
    return 'Other'

def course_level(num):
    try:
        n = int(re.search(r'\d+', str(num)).group())
        if n < 100: return 'Lower'
        if n < 200: return 'Upper'
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


def get_course_urls(sess):
    # Fetch the root sitemap index
    r = sess.get(BASE + '/sitemap.xml', timeout=15)
    soup = BeautifulSoup(r.text, 'xml')
    sitemap_locs = [loc.get_text(strip=True) for loc in soup.find_all('loc')]
    print(f'Found {len(sitemap_locs)} sub-sitemaps', flush=True)

    # Collect 2024 course URLs from all sub-sitemaps
    course_urls = []
    for i, sm_url in enumerate(sitemap_locs, 1):
        try:
            r2 = sess.get(sm_url, timeout=20)
            sm_soup = BeautifulSoup(r2.text, 'xml')
            for loc in sm_soup.find_all('loc'):
                url = loc.get_text(strip=True)
                if '/course/2024/' in url:
                    course_urls.append(url)
            print(f'  Sitemap {i}/{len(sitemap_locs)}: {len(course_urls)} total', flush=True)
        except Exception as e:
            print(f'  Sitemap {i} error: {e}', flush=True)
    return course_urls


def parse_course_page(html, url):
    soup = BeautifulSoup(html, 'html.parser')
    script = soup.find('script', id='__NEXT_DATA__')
    if not script:
        return None
    try:
        data = json.loads(script.string)
        content = data['props']['pageProps'].get('pageContent')
        if not content:
            return None

        code = content.get('code', '')
        # code is like "ECON 101" or "COM SCI 31"
        m = re.match(r'^(.+?)\s+(\d+[A-Z]?)$', code.strip())
        if m:
            dept_code = m.group(1).strip()
            course_num = m.group(2).strip()
        else:
            # Try to extract from URL
            path = url.rstrip('/').split('/')[-1]
            mn = re.match(r'^([A-Za-z]+)(\d+[A-Za-z]?)$', path)
            if mn:
                dept_code = mn.group(1)
                course_num = mn.group(2)
            else:
                dept_code = code
                course_num = ''

        title = content.get('title', '')
        # Description may contain HTML
        desc_raw = content.get('description', '')
        if desc_raw:
            desc = BeautifulSoup(desc_raw, 'html.parser').get_text(' ', strip=True)[:2000]
        else:
            desc = ''

        # Get course level from content field
        level_str = content.get('course_level', '')
        if 'lower' in level_str.lower():
            level = 'Lower'
        elif 'upper' in level_str.lower():
            level = 'Upper'
        elif 'graduate' in level_str.lower() or 'grad' in level_str.lower():
            level = 'Graduate'
        else:
            level = course_level(course_num)

        combined = f'{title} {desc}'
        return {
            'dept_code': dept_code,
            'course_number': course_num,
            'title': title,
            'description': desc,
            'broad_area': broad_area(dept_code),
            'level': level,
            'progressive_signal': sig(combined, PROGRESSIVE_KEYWORDS),
            'western_canon_signal': sig(combined, WESTERN_CANON_KEYWORDS),
            'climate_narrow_signal': sig(combined, CLIMATE_NARROW_KEYWORDS),
            'climate_broad_signal': sig(combined, CLIMATE_BROAD_KEYWORDS),
            'cross_listed': 0,
            'deduplicated': 0,
        }
    except Exception as e:
        return None


def fetch_course(sess, url):
    for attempt in range(3):
        try:
            r = sess.get(url, timeout=30)
            if r.status_code == 200:
                return parse_course_page(r.text, url)
            elif r.status_code == 429:
                time.sleep(2 ** attempt)
        except Exception:
            time.sleep(1)
    return None


def main():
    if OUT_FILE.exists():
        print(f'Already exists: {OUT_FILE}')
        return

    sess = make_sess()
    print('Collecting course URLs from sitemaps...')
    course_urls = get_course_urls(sess)
    print(f'Total 2024 course URLs: {len(course_urls)}')

    if not course_urls:
        print('No URLs found, aborting')
        return

    print('Fetching course pages (20 workers)...')
    all_courses = []
    done = 0
    errors = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        futs = {ex.submit(fetch_course, sess, url): url for url in course_urls}
        for fut in as_completed(futs):
            done += 1
            course = fut.result()
            if course:
                all_courses.append(course)
            else:
                errors += 1
            if done % 500 == 0:
                print(f'  {done}/{len(course_urls)} fetched, {len(all_courses)} parsed, {errors} errors', flush=True)

    print(f'Total: {len(all_courses)} courses from {len(course_urls)} URLs ({errors} errors)')

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
        'notes': f'Next.js SSR general catalog (catalog.registrar.ucla.edu). AY={AY_LABEL}.',
    }
    prog['completed'] = sum(1 for v in prog['universities'].values() if v.get('status') == 'completed')
    import datetime
    prog['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    (ROOT / 'progress.json').write_text(json.dumps(prog, indent=2))
    print(f'progress.json: {KEY} → completed ({prog["completed"]} total)')


if __name__ == '__main__':
    main()
