#!/usr/bin/env python3
"""Scrape University of Pittsburgh (Acalog, no WAF — direct requests work)."""
import re, csv, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests

PROXY = 'http://127.0.0.1:43429'
CA = '/root/.ccr/ca-bundle.crt'
BASE = 'https://catalog.upp.pitt.edu'
CATOID = 235
NAVOID = 24840
NAME = 'University of Pittsburgh'
KEY = 'pitt'
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

HUMANITIES_D = {'ENGL','ENG','HIST','PHIL','ART','MUS','MUSC','THTR','FILM','LING',
    'CLAS','GREK','LATN','ARBC','CHIN','FREN','GERM','ITAL','JAPN','KORE','PORT',
    'RUSS','SPAN','ARTH','LIT','WRIT','CRWR','RELI','REL','DANC','THEA','HUM',
    'AMST','AFAM','WMST','LACS','GLBL','AAAS','AFRI','ASAM','CHST','ETHN','COMM',}
SOCIAL_D = {'SOC','SOCY','PSYC','PSY','ECON','POLS','POL','POLI','GEOG','ANTH',
    'CRIM','CRIJ','SOCI','GOVT','IR','INTL','EDUC','SW','SOWK','URBS','PLAN',
    'PUBL','PUBA','PADM','GLST','DEMG',}
STEM_D = {'MATH','STAT','PHYS','CHEM','BIOL','BIO','CS','CSE','CSCI','ECE','EE',
    'ME','CHE','CEE','AERO','BME','MAE','MECH','ELEC','EECS','ENGR','ENER',
    'ENVS','ENVR','ATMO','GEOS','GEOL','ASTR','GENE','MICR','BCMB','BIOC','NEUR',
    'NEURO','ANSC','AGRO','PLSC','COGS','APMA','AMTH','ORIE','INFO','IS','MIS',}
MEDICAL_D = {'MED','MDSC','BMED','NURS','PHMD','PHRM','PHCY','DENT','HLTH','HPH',
    'PH','PUBH','EPID','BIOM','PHSP','HSCI','HSAD','OCTH','PHTH','SLHS','SPPA',
    'ANAT','PATH','PHSL','IMMU',}
PROFESSIONAL_D = {'BUAD','BUSI','BUSN','MGMT','MKTG','FIN','FINC','ACCT','ACCY',
    'OB','OPER','HRM','ENTR','INTB','LAWS','LAW','LAWG','LAWD','LAWI','JURI',
    'EDLD','KINE','KNES','EXSC','SPRT','RECR','HOSP','PRST','JOUR','JRNL','ARCH',
    'LAAR','URPL',}

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
        # Handle 4-digit course numbers (Pitt/many universities: 1xxx=Lower, 2xxx-3xxx=Upper, 4xxx+=Graduate)
        if n >= 1000:
            if n < 2000: return 'Lower'
            if n < 5000: return 'Upper'
            return 'Graduate'
        # Standard 3-digit numbering
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


def get_all_coids(sess):
    coids = []
    pg = 1
    consecutive_empty = 0
    while consecutive_empty < 3:
        url = (f'{BASE}/content.php?catoid={CATOID}&navoid={NAVOID}'
               f'&filter%5Bitem_type%5D=3&filter%5Bonly_active%5D=1'
               f'&filter%5B3%5D=1&filter%5Bcpage%5D={pg}&filter%5Blimit%5D=500')
        try:
            r = sess.get(url, timeout=20)
            soup = BeautifulSoup(r.text, 'html.parser')
            links = soup.find_all('a', href=re.compile(r'preview_course.*coid=\d+'))
            if not links:
                consecutive_empty += 1
                print(f'p{pg}: 0 links (empty #{consecutive_empty})', flush=True)
            else:
                consecutive_empty = 0
                page_coids = []
                for a in links:
                    m = re.search(r'coid=(\d+)', a['href'])
                    if m:
                        page_coids.append((int(m.group(1)), a.get_text(strip=True)))
                coids.extend(page_coids)
                print(f'p{pg}: {len(links)} links (total {len(coids)})', flush=True)
        except Exception as e:
            consecutive_empty += 1
            print(f'p{pg}: ERROR {str(e)[:50]} (empty #{consecutive_empty})', flush=True)
        pg += 1
        if pg > 200:
            break
    return coids


def parse_pitt_detail(html):
    soup = BeautifulSoup(html, 'html.parser')
    block = (soup.find('td', class_=lambda x: x and 'block_content_popup' in x) or
             soup.find('div', class_=lambda x: x and 'block_content_popup' in x) or
             soup.find('td', class_=lambda x: x and 'block_content' in x))
    if not block:
        return None

    text = block.get_text(' ', strip=True)
    # Remove "Print-Friendly Page (opens a new window) Add to Portfolio ." prefix
    text = re.sub(r'^Print-Friendly.*?Portfolio\s*\.?\s*', '', text).strip()

    # Pattern: "DEPT NNNN - Course Title Credits: N Description text"
    m = re.match(r'^([A-Z]+(?:\s+[A-Z]+)?)\s+(\d+\w*)\s*[-–]\s*(.+?)(?:\s+(?:Minimum Credits|Credits|Units):.*)?$',
                 text, re.DOTALL)
    if not m:
        # Try simpler
        m = re.match(r'^([A-Z]{2,8})\s+(\d+\w*)\s+(.*)', text)
    if not m:
        return None

    dept = m.group(1).strip()
    num = m.group(2).strip()
    rest = m.group(3).strip() if m.lastindex >= 3 else ''

    # Title ends at first line break or at "Minimum Credits:"
    title_m = re.match(r'^(.+?)(?:\s+Minimum Credits:.*|\s+Credits:.*|\s+Units:.*)?$', rest, re.DOTALL)
    if title_m:
        title_part = title_m.group(1).strip()
        # title is up to first sentence-ending period that looks like a title stop
        title_lines = title_part.split('\n')
        title = title_lines[0].strip()
        if len(title) > 150:
            title = title[:150]
    else:
        title = rest[:100]

    # Description: everything after "credits" line
    desc_m = re.search(r'(?:Maximum Credits:\s*\d+|Credits:\s*[\d.]+)\s+(.*)', text, re.DOTALL)
    if desc_m:
        desc = desc_m.group(1).strip()[:2000]
    else:
        # Fallback: paragraphs
        paras = block.find_all('p')
        desc = ' '.join(p.get_text(' ', strip=True) for p in paras if len(p.get_text(strip=True)) > 10)[:2000]

    combined = f'{title} {desc}'
    return {
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
    }


def fetch_detail(sess, coid):
    url = f'{BASE}/preview_course.php?catoid={CATOID}&coid={coid}'
    for attempt in range(3):
        try:
            r = sess.get(url, timeout=20)
            if r.status_code == 200 and len(r.content) > 100:
                return parse_pitt_detail(r.text)
            elif r.status_code == 429:
                import time; time.sleep(2 ** attempt)
        except Exception:
            import time; time.sleep(1)
    return None


def main():
    if OUT_FILE.exists():
        print(f'Already exists: {OUT_FILE}')
        return

    sess = make_sess()
    print('Collecting course IDs...')
    coids = get_all_coids(sess)
    print(f'Total: {len(coids)} courses')

    print('Fetching course details (4 workers)...')
    rows = []
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_detail, sess, c[0]): c for c in coids}
        for fut in as_completed(futs):
            done += 1
            if done % 100 == 0:
                print(f'  {done}/{len(coids)} done, {len(rows)} parsed', flush=True)
            course = fut.result()
            if course and (course['dept_code'] or course['title']):
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

    print(f'Parsed {len(rows)} / {len(coids)}')
    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerows(rows)
    print(f'Saved: {OUT_FILE}')

    # Update progress.json
    prog = json.loads((ROOT / 'progress.json').read_text())
    if 'pitt' in prog.get('dynamic_js_only', []):
        prog['dynamic_js_only'].remove('pitt')
    prog['universities']['pitt'] = {
        **prog['universities'].get('pitt', {}),
        'status': 'completed',
        'name': NAME,
        'data_files': [str(OUT_FILE)],
        'courses_count': len(rows),
        'progressive_pct': round(sum(1 for r in rows if r['progressive_signal']) / len(rows) * 100, 2) if rows else 0,
        'canon_pct': round(sum(1 for r in rows if r['western_canon_signal']) / len(rows) * 100, 2) if rows else 0,
        'notes': f'Acalog direct requests (no WAF). catoid={CATOID}, navoid={NAVOID}.',
    }
    prog['completed'] = sum(1 for v in prog['universities'].values() if v.get('status') == 'completed')
    import datetime
    prog['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    (ROOT / 'progress.json').write_text(json.dumps(prog, indent=2))
    print(f'progress.json updated: pitt → completed ({prog["completed"]} total)')


if __name__ == '__main__':
    main()
