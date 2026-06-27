#!/usr/bin/env python3
"""
Comprehensive Acalog scraper using Playwright route interception.
Chrome handles JS rendering; Python requests handles network through proxy.
"""
import sys
import os
import re
import csv
import json
import time
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests as req_lib
from playwright.sync_api import sync_playwright, Route, Page

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)

PROXY = 'http://127.0.0.1:43429'
CA_BUNDLE = '/root/.ccr/ca-bundle.crt'

# ── keyword lists ─────────────────────────────────────────────────────────────
PROGRESSIVE_KEYWORDS = [
    'diversity','racial','racism','anti-racism','antiracism','equity','equitable',
    'inclusion','inclusive','belonging','systemic','systemic racism','white supremacy',
    'privilege','oppression','oppressive','marginalized','marginalization','colonialism',
    'decolonize','decolonial','indigenous knowledge','indigenous studies','settler',
    'intersectionality','intersectional','social justice','environmental justice',
    'queer theory','queer studies','gender studies','feminist','feminism','patriarchy',
    'heteronormativity','cisgender','transgender','nonbinary','latinx','bipoc',
    'positionality','standpoint','lived experience','microaggression','implicit bias',
    'unconscious bias','allyship','woke','critical race','whiteness','colorblind',
    'reparations','abolition','defund','anti-capitalist','neoliberal critique',
    'land acknowledgment','solidarity','liberation','social movement','activism',
]

WESTERN_CANON_KEYWORDS = [
    'shakespeare','plato','aristotle','socrates','homer','virgil','dante','milton',
    'chaucer','cervantes','descartes','kant','hegel','nietzsche','locke','hobbes',
    'rousseau','voltaire','enlightenment thought','classical antiquity','ancient greece',
    'ancient rome','medieval philosophy','renaissance humanism','western civilization',
    'great books','great texts','liberal arts tradition','socratic','platonic',
    'stoicism','epicureanism','thomism','scholasticism','classical literature',
    'greek tragedy','roman history','byzantine','augustine','aquinas',
]

CLIMATE_NARROW_KEYWORDS = [
    'climate change','global warming','greenhouse gas','carbon emission','decarbonization',
    'net zero','paris agreement','ipcc','sea level rise','arctic ice','permafrost',
    'carbon capture','carbon sequestration','climate model','climate science',
    'climate policy','climate adaptation','climate mitigation','climate justice',
    'climate refugee','climate crisis','climate emergency','fossil fuel phase',
]

CLIMATE_BROAD_KEYWORDS = [
    'sustainability','sustainable development','renewable energy','solar power',
    'wind energy','energy transition','clean energy','green energy','carbon footprint',
    'carbon neutral','environmental policy','environmental law','environmental science',
    'ecology','ecosystem','biodiversity','habitat loss','species extinction',
    'ocean acidification','air pollution','water scarcity','environmental degradation',
    'circular economy','environmental impact','environmental assessment','green building',
    'leed','sustainable agriculture','food security','environmental ethics',
]

def check_progressive(text):
    t = text.lower()
    return any(kw in t for kw in PROGRESSIVE_KEYWORDS)

def check_western_canon(text):
    t = text.lower()
    return any(kw in t for kw in WESTERN_CANON_KEYWORDS)

def check_climate_narrow(text):
    t = text.lower()
    return any(kw in t for kw in CLIMATE_NARROW_KEYWORDS)

def check_climate_broad(text):
    t = text.lower()
    return any(kw in t for kw in CLIMATE_BROAD_KEYWORDS)

HUMANITIES_DEPTS = {
    'ENGL','ENG','HIST','PHIL','ART','MUS','MUSC','THTR','FILM','LANG','LING',
    'CLAS','GREK','LATN','ARBC','CHIN','FREN','GERM','ITAL','JAPN','KORE','PORT',
    'RUSS','SPAN','ARTH','ARTD','LIT','WRIT','CRWR','COMPLIT','ANTH','RELI','REL',
    'CREA','JOURN','COMM','FINA','DANC','THEA','ARCH','HUM','AMST','AFAM','WMST',
    'LACS','GLBL','AAAS','AFRI','ASAM','CHST','ETHN',
}

SOCIAL_SCI_DEPTS = {
    'SOC','SOCY','PSYC','PSY','ECON','POLS','POL','POLI','GEOG','ANTH','CRIM',
    'CRIJ','SOCI','GOVT','IR','INTL','COMM','MEDIA','EDUC','SW','SOWK','HUSV',
    'CLAS','DEMG','URBS','PLAN','PUBL','PUBA','PADM','INTD','GLST',
}

STEM_DEPTS = {
    'MATH','STAT','PHYS','CHEM','BIOL','BIO','CS','CSE','CSCI','ECE','EE','ME',
    'CHE','CEE','AERO','BME','MAE','MECH','ELEC','EECS','ENGS','ENGR','ENER',
    'ENVS','ENVR','ATMO','GEOS','GEOL','ASTR','ASTRO','GENE','MICR','BCMB',
    'BIOC','NEUR','NEURO','ANSC','AGRO','PLSC','FSCI','NASC','COGS',
    'APMA','AMTH','ORIE','SYSE','INFS','INFO','IS','MIS',
}

MEDICAL_DEPTS = {
    'MED','MDSC','BMED','NURS','NRSG','PHMD','PHRM','PHCY','DENT','HLTH','HPH',
    'PH','PUBH','EPID','BIOM','PHSP','HSCI','HSAD','HPSC','OCTH','PHTH','SLHS',
    'SPPA','ANAT','PATH','PHSL','IMMU','GENE',
}

PROFESSIONAL_DEPTS = {
    'BUAD','BUSI','BUSN','MGMT','MKTG','FIN','FINC','ACCT','ACCY','OB','OPER',
    'ORGS','HRM','ENTR','INTB','LAWS','LAW','LAWG','LAWD','LAWI','JURI','EDUC',
    'EDSP','EDUE','EDLD','COUN','KINE','KNES','EXSC','SPRT','RECR','HOSP','HIM',
    'COMN','PRST','JOUR','JRNL','LIBR','ARCH','LAAR','LAND','URPL','FAES',
}

def classify_broad_area(dept_code):
    d = dept_code.upper()
    if d in MEDICAL_DEPTS: return 'Medical Sciences'
    if d in PROFESSIONAL_DEPTS: return 'Professional'
    if d in STEM_DEPTS: return 'STEM'
    if d in SOCIAL_SCI_DEPTS: return 'Social Sciences'
    if d in HUMANITIES_DEPTS: return 'Humanities'
    return 'Other'

def classify_level(course_num):
    try:
        n = int(re.search(r'\d+', str(course_num)).group())
        if n < 100: return 'Other'
        if n < 200: return 'Lower'
        if n < 300: return 'Lower'
        if n < 400: return 'Upper'
        if n < 500: return 'Upper'
        return 'Graduate'
    except Exception:
        return 'Other'

# ── Acalog university configs ─────────────────────────────────────────────────
ACALOG_UNIVERSITIES = {
    'usc': {
        'name': 'University of Southern California',
        'base_url': 'https://catalogue.usc.edu',
        'catoid': None,  # auto-discover
        'short_name': 'usc',
    },
    'osu': {
        'name': 'Ohio State University',
        'base_url': 'https://catalog.osu.edu',
        'catoid': None,
        'short_name': 'osu',
    },
    'pitt': {
        'name': 'University of Pittsburgh',
        'base_url': 'https://catalog.upp.pitt.edu',
        'catoid': None,
        'short_name': 'pitt',
    },
    'ou': {
        'name': 'University of Oklahoma',
        'base_url': 'https://catalog.ou.edu',
        'catoid': None,
        'short_name': 'ou',
    },
    'unlv': {
        'name': 'University of Nevada Las Vegas',
        'base_url': 'https://catalog.unlv.edu',
        'catoid': None,
        'short_name': 'unlv',
    },
    'baylor': {
        'name': 'Baylor University',
        'base_url': 'https://catalog.baylor.edu',
        'catoid': None,
        'short_name': 'baylor',
    },
    'ttu': {
        'name': 'Texas Tech University',
        'base_url': 'https://catalog.ttu.edu',
        'catoid': None,
        'short_name': 'ttu',
    },
    'uh': {
        'name': 'University of Houston',
        'base_url': 'https://publications.uh.edu',
        'catoid': None,
        'short_name': 'uh',
    },
    'uc': {
        'name': 'University of Cincinnati',
        'base_url': 'https://catalog.uc.edu',
        'catoid': None,
        'short_name': 'uc',
    },
    'udel': {
        'name': 'University of Delaware',
        'base_url': 'https://catalog.udel.edu',
        'catoid': None,
        'short_name': 'udel',
    },
    'uva': {
        'name': 'University of Virginia',
        'base_url': 'https://records.ureg.virginia.edu',
        'catoid': None,
        'short_name': 'uva',
    },
    'rpi': {
        'name': 'Rensselaer Polytechnic Institute',
        'base_url': 'https://catalog.rpi.edu',
        'catoid': None,
        'short_name': 'rpi',
    },
    'utk': {
        'name': 'University of Tennessee Knoxville',
        'base_url': 'https://catalog.utk.edu',
        'catoid': None,
        'short_name': 'utk',
    },
    'stonybrook': {
        'name': 'Stony Brook University',
        'base_url': 'https://www.stonybrook.edu',
        'catoid': None,
        'short_name': 'stonybrook',
        'is_acalog': False,
    },
    'lsu': {
        'name': 'Louisiana State University',
        'base_url': 'https://catalog.lsu.edu',
        'catoid': None,
        'short_name': 'lsu',
    },
}


def make_session():
    sess = req_lib.Session()
    sess.proxies = {'https': PROXY, 'http': PROXY}
    sess.verify = CA_BUNDLE
    sess.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    return sess


def make_route_handler(sess):
    def handle_route(route: Route):
        url = route.request.url
        method = route.request.method
        headers = {k: v for k, v in route.request.headers.items()
                   if k.lower() not in ('host',)}
        post_data = route.request.post_data
        try:
            r = sess.request(
                method=method, url=url, headers=headers,
                data=post_data.encode() if post_data else None,
                timeout=20, allow_redirects=True,
            )
            # Don't forward content-encoding since we decode it in requests
            resp_headers = {k: v for k, v in r.headers.items()
                           if k.lower() not in ('content-encoding', 'transfer-encoding')}
            route.fulfill(
                status=r.status_code,
                headers=resp_headers,
                body=r.content,
            )
        except Exception as e:
            route.abort()
    return handle_route


def discover_catoid(sess, base_url):
    """Find current catoid from the Acalog main page."""
    try:
        r = sess.get(base_url + '/', timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        # Look for catalog links with catoid
        links = soup.find_all('a', href=re.compile(r'catoid=(\d+)'))
        catoids = set()
        for link in links:
            m = re.search(r'catoid=(\d+)', link.get('href', ''))
            if m:
                catoids.add(int(m.group(1)))
        if catoids:
            return max(catoids)
    except Exception as e:
        log.warning(f"discover_catoid failed for {base_url}: {e}")
    return None


def get_catalog_years(sess, base_url):
    """Get list of (catoid, year_label) pairs from Acalog."""
    result = []
    try:
        r = sess.get(base_url + '/', timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        # Find catalog selection links
        for link in soup.find_all('a', href=re.compile(r'catoid=\d+')):
            href = link.get('href', '')
            m = re.search(r'catoid=(\d+)', href)
            if m:
                catoid = int(m.group(1))
                label = link.get_text(strip=True)
                if label and any(c.isdigit() for c in label):
                    result.append((catoid, label))
    except Exception as e:
        log.warning(f"get_catalog_years failed for {base_url}: {e}")
    # Deduplicate and sort
    seen = set()
    deduped = []
    for item in result:
        if item[0] not in seen:
            seen.add(item[0])
            deduped.append(item)
    return sorted(deduped, key=lambda x: x[0])


def get_course_ids_from_filter(page, base_url, catoid, limit=40):
    """Use Acalog JS filter to get all course IDs."""
    all_coids = []
    page_num = 1
    navoid = None

    while True:
        url = (f"{base_url}/content.php?catoid={catoid}"
               f"&filter[item_type]=3&filter[only_active]=1"
               f"&filter[3]=1&filter[cpage]={page_num}&filter[limit]={limit}")

        try:
            resp = page.goto(url, wait_until='networkidle', timeout=45000)
            content = page.content()
            soup = BeautifulSoup(content, 'html.parser')

            # Find navoid if not set
            if navoid is None:
                m = re.search(r'navoid=(\d+)', content)
                if m:
                    navoid = int(m.group(1))

            # Extract course links
            links = soup.find_all('a', href=re.compile(r'preview_course_nopop'))
            if not links:
                log.info(f"  No courses on page {page_num}, stopping")
                break

            for link in links:
                href = link.get('href', '')
                m = re.search(r'coid=(\d+)', href)
                if m:
                    coid = int(m.group(1))
                    title_text = link.get_text(strip=True)
                    all_coids.append((coid, title_text))

            log.info(f"  Page {page_num}: found {len(links)} courses (total: {len(all_coids)})")

            # Check if there's a next page
            next_link = soup.find('a', string=re.compile(r'Next'))
            if not next_link:
                # Also check for >> or > navigation
                next_link = soup.find('a', href=re.compile(r'cpage=\d+'))
                if next_link:
                    href = next_link.get('href', '')
                    m = re.search(r'cpage=(\d+)', href)
                    if m and int(m.group(1)) > page_num:
                        page_num = int(m.group(1))
                        continue
                break

            if next_link:
                href = next_link.get('href', '')
                m = re.search(r'cpage=(\d+)', href)
                if m:
                    page_num = int(m.group(1))
                else:
                    page_num += 1
            else:
                break

        except Exception as e:
            log.error(f"  Error on filter page {page_num}: {e}")
            break

    return all_coids, navoid


def fetch_course_detail_pw(page, base_url, catoid, coid):
    """Fetch and parse a single course detail page using Playwright."""
    url = f"{base_url}/preview_course_nopop.php?catoid={catoid}&coid={coid}"
    try:
        resp = page.goto(url, wait_until='networkidle', timeout=30000)
        content = page.content()
        return parse_course_detail(content, base_url, catoid, coid)
    except Exception as e:
        log.warning(f"    Detail fetch error coid={coid}: {e}")
        return None


def fetch_course_detail_requests(sess, base_url, catoid, coid):
    """Fetch course detail using requests (for non-JS Acalog or as fallback)."""
    url = f"{base_url}/preview_course_nopop.php?catoid={catoid}&coid={coid}"
    try:
        r = sess.get(url, timeout=15)
        return parse_course_detail(r.text, base_url, catoid, coid)
    except Exception as e:
        log.warning(f"    Detail requests error coid={coid}: {e}")
        return None


def parse_course_detail(html, base_url, catoid, coid):
    """Parse Acalog course detail HTML into a course dict."""
    soup = BeautifulSoup(html, 'html.parser')

    # Try multiple selectors for course content block
    block = (soup.find('td', class_='block_content') or
             soup.find('div', class_='block_content') or
             soup.find('div', id=re.compile(r'course', re.I)) or
             soup.find('body'))

    if not block:
        return None

    text = block.get_text(' ', strip=True)

    # Extract course number + title
    # Typical format: "DEPT 101 Course Title"
    title_el = block.find('h1') or block.find('h2') or block.find('strong')
    title_text = ''
    if title_el:
        title_text = title_el.get_text(' ', strip=True)
    else:
        # Try first line of content
        lines = text.split('\n')
        title_text = lines[0] if lines else ''

    # Parse dept code and course number
    m = re.match(r'^([A-Z]{2,6})\s+(\w+)\s+(.*)', title_text.strip())
    if m:
        dept_code = m.group(1)
        course_num = m.group(2)
        title = m.group(3)
    else:
        dept_code = ''
        course_num = ''
        title = title_text

    # Extract description (text after title block)
    desc = ''
    # Look for description paragraph
    paras = block.find_all('p')
    if paras:
        desc = ' '.join(p.get_text(' ', strip=True) for p in paras if len(p.get_text(strip=True)) > 20)
    if not desc:
        # Use all text after removing the title
        desc = text.replace(title_text, '', 1).strip()

    if not dept_code and not title:
        return None

    combined = f"{title} {desc}"

    return {
        'dept_code': dept_code,
        'course_number': course_num,
        'title': title,
        'description': desc,
        'broad_area': classify_broad_area(dept_code),
        'level': classify_level(course_num),
        'progressive_signal': 1 if check_progressive(combined) else 0,
        'western_canon_signal': 1 if check_western_canon(combined) else 0,
        'climate_narrow_signal': 1 if check_climate_narrow(combined) else 0,
        'climate_broad_signal': 1 if check_climate_broad(combined) else 0,
        'cross_listed': 0,
        'deduplicated': 0,
    }


def scrape_acalog_university(uni_key, config, sess, page, years_to_scrape=None):
    """Scrape all courses from an Acalog university."""
    base_url = config['base_url']
    name = config['name']
    short_name = config['short_name']

    log.info(f"\n{'='*60}")
    log.info(f"Scraping: {name}")
    log.info(f"URL: {base_url}")

    # Test connectivity first
    try:
        r = sess.get(base_url + '/', timeout=15)
        log.info(f"  Main page: HTTP {r.status_code}")
        if r.status_code not in (200, 202):
            log.error(f"  Cannot access {base_url}: HTTP {r.status_code}")
            return None, 'failed'
    except Exception as e:
        log.error(f"  Cannot access {base_url}: {e}")
        return None, 'blocked_by_network'

    # Get catalog years
    catalog_years = get_catalog_years(sess, base_url)
    log.info(f"  Found {len(catalog_years)} catalog years")
    for cy in catalog_years:
        log.info(f"    catoid={cy[0]}: {cy[1]}")

    if not catalog_years:
        # Try to discover catoid from main page
        catoid = discover_catoid(sess, base_url)
        if catoid:
            catalog_years = [(catoid, 'current')]
            log.info(f"  Using discovered catoid={catoid}")
        else:
            log.error(f"  No catalog years found")
            return None, 'failed'

    # Filter to years we want (2000 to present)
    if years_to_scrape:
        catalog_years = [(c, l) for c, l in catalog_years if c in years_to_scrape]
    else:
        # Take up to last 5 years for now (to avoid too many requests)
        catalog_years = catalog_years[-5:] if len(catalog_years) > 5 else catalog_years

    all_data_files = []

    for catoid, year_label in catalog_years:
        log.info(f"\n  Processing catoid={catoid} ({year_label})")

        # Get year from label
        year_m = re.search(r'(\d{4})', year_label)
        start_year = int(year_m.group(1)) if year_m else 2024

        # Skip if data file already exists
        filename = f"{short_name}_{start_year}_{start_year+1}.csv"
        filepath = DATA_DIR / filename
        if filepath.exists():
            log.info(f"  File already exists: {filename}, skipping")
            all_data_files.append(str(filepath))
            continue

        # Get course IDs from filter page
        log.info(f"  Getting course IDs from filter page...")
        coid_list, navoid = get_course_ids_from_filter(page, base_url, catoid)
        log.info(f"  Found {len(coid_list)} courses")

        if not coid_list:
            log.warning(f"  No courses found for catoid={catoid}")
            continue

        # Fetch course details
        log.info(f"  Fetching course details...")
        rows = []
        for i, (coid, title_hint) in enumerate(coid_list):
            if i % 100 == 0:
                log.info(f"    {i}/{len(coid_list)}")

            # Try with requests first (faster), fall back to playwright
            course = fetch_course_detail_requests(sess, base_url, catoid, coid)
            if not course or not course['dept_code']:
                course = fetch_course_detail_pw(page, base_url, catoid, coid)

            if course:
                # Determine year from label
                year_m2 = re.findall(r'\d{4}', year_label)
                if len(year_m2) >= 2:
                    academic_year = f"{year_m2[0]}-{year_m2[1]}"
                    acad_label = f"{year_m2[0]}-{year_m2[1]}"
                elif len(year_m2) == 1:
                    academic_year = f"{year_m2[0]}-{int(year_m2[0])+1}"
                    acad_label = academic_year
                else:
                    academic_year = f"{start_year}-{start_year+1}"
                    acad_label = academic_year

                row = {
                    'university': name,
                    'academic_year': academic_year.replace('-', '_'),
                    'academic_year_label': acad_label,
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
                    'cross_listed': course['cross_listed'],
                    'deduplicated': course['deduplicated'],
                }
                rows.append(row)

        if rows:
            log.info(f"  Writing {len(rows)} rows to {filename}")
            fields = ['university','academic_year','academic_year_label','department_code',
                     'course_number','title','description','broad_area','level',
                     'progressive_signal','western_canon_signal','climate_narrow_signal',
                     'climate_broad_signal','cross_listed','deduplicated']
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            all_data_files.append(str(filepath))
            log.info(f"  Saved: {filename}")

    return all_data_files, 'completed'


def update_progress(uni_key, status, data_files, notes='', name=None):
    """Update progress.json for a university."""
    with open(ROOT / 'progress.json') as f:
        p = json.load(f)

    if uni_key not in p['universities']:
        p['universities'][uni_key] = {}

    u = p['universities'][uni_key]
    u['status'] = status
    if data_files:
        u['data_files'] = data_files
        # Calculate progress stats
        total_rows = 0
        prog_count = 0
        canon_count = 0
        for fp in data_files:
            try:
                with open(fp) as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        total_rows += 1
                        if row.get('progressive_signal') == '1':
                            prog_count += 1
                        if row.get('western_canon_signal') == '1':
                            canon_count += 1
            except Exception:
                pass
        u['courses_count'] = total_rows
        u['progressive_pct'] = round(prog_count / total_rows * 100, 2) if total_rows else 0
        u['canon_pct'] = round(canon_count / total_rows * 100, 2) if total_rows else 0

    if notes:
        u['notes'] = notes
    if name:
        u['name'] = name

    # Update counters
    status_counts = {}
    for uid, udata in p['universities'].items():
        s = udata.get('status', 'unknown')
        status_counts[s] = status_counts.get(s, 0) + 1
    p['completed'] = status_counts.get('completed', 0)

    import datetime
    p['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'

    with open(ROOT / 'progress.json', 'w') as f:
        json.dump(p, f, indent=2)

    log.info(f"  Updated progress.json: {uni_key} -> {status}")


def main():
    sess = make_session()

    universities_to_scrape = list(ACALOG_UNIVERSITIES.keys())

    # Allow command-line override
    if len(sys.argv) > 1:
        universities_to_scrape = sys.argv[1:]

    log.info(f"Universities to scrape: {universities_to_scrape}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
            headless=True,
            args=[
                '--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                '--proxy-server=direct://',  # Chrome handles no network; routes handle it
            ],
        )
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(45000)
        page.route('**/*', make_route_handler(sess))

        for uni_key in universities_to_scrape:
            config = ACALOG_UNIVERSITIES.get(uni_key)
            if not config:
                log.warning(f"Unknown university: {uni_key}")
                continue

            try:
                data_files, status = scrape_acalog_university(
                    uni_key, config, sess, page
                )
                update_progress(
                    uni_key, status, data_files or [],
                    name=config['name']
                )
            except Exception as e:
                log.error(f"Error scraping {uni_key}: {e}", exc_info=True)
                update_progress(uni_key, 'failed', [], notes=str(e), name=config.get('name'))

        browser.close()

    log.info("\nDone!")


if __name__ == '__main__':
    main()
