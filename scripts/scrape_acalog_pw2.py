#!/usr/bin/env python3
"""
Acalog scraper: Playwright route interception for filter pages (WAF init),
Python requests with WAF cookies for fast parallel course detail fetching.

Discovered catoid/navoid pairs:
  usc:   catoid=22, navoid=9384
  pitt:  catoid=235, navoid=24840
  unlv:  catoid=53, navoid=17221
  ttu:   catoid=26, navoid=2326
  rpi:   catoid=33, navoid=891
  utk:   catoid=56, navoid=12117
  lsu:   catoid=34, navoid=3326 (also 35)
  udel:  catoid=97, navoid=35898
  uva:   catoid=72, navoid=6679 (Programs/Courses)
"""
import sys, re, csv, json, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
import requests as req_lib
from playwright.sync_api import sync_playwright, Route

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)

PROXY = 'http://127.0.0.1:43429'
CA_BUNDLE = '/root/.ccr/ca-bundle.crt'

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
        if n >= 1000:
            if n < 2000: return 'Lower'
            if n < 5000: return 'Upper'
            return 'Graduate'
        if n < 300: return 'Lower'
        if n < 500: return 'Upper'
        return 'Graduate'
    except: return 'Other'

# Hardcoded configs with discovered catoid/navoid
UNIS = {
    'usc':    {'name': 'University of Southern California',      'base': 'https://catalogue.usc.edu',         'catoid': 22,  'navoid': 9384},
    'pitt':   {'name': 'University of Pittsburgh',               'base': 'https://catalog.upp.pitt.edu',      'catoid': 235, 'navoid': 24840},
    'unlv':   {'name': 'University of Nevada Las Vegas',         'base': 'https://catalog.unlv.edu',          'catoid': 53,  'navoid': 17221},
    'ttu':    {'name': 'Texas Tech University',                  'base': 'https://catalog.ttu.edu',           'catoid': 26,  'navoid': 2326},
    'rpi':    {'name': 'Rensselaer Polytechnic Institute',       'base': 'https://catalog.rpi.edu',           'catoid': 33,  'navoid': 891},
    'utk':    {'name': 'University of Tennessee Knoxville',      'base': 'https://catalog.utk.edu',           'catoid': 56,  'navoid': 12117},
    'lsu':    {'name': 'Louisiana State University',             'base': 'https://catalog.lsu.edu',           'catoid': 34,  'navoid': 3326},
    'udel':   {'name': 'University of Delaware',                 'base': 'https://catalog.udel.edu',          'catoid': 97,  'navoid': 35898},
    'uva':    {'name': 'University of Virginia',                 'base': 'https://records.ureg.virginia.edu', 'catoid': 72,  'navoid': 6679},
    'stonybrook': {'name': 'Stony Brook University',            'base': 'https://catalog.stonybrook.edu',    'catoid': 11,  'navoid': 1135},
}

CSV_FIELDS = ['university','academic_year','academic_year_label','department_code',
              'course_number','title','description','broad_area','level',
              'progressive_signal','western_canon_signal','climate_narrow_signal',
              'climate_broad_signal','cross_listed','deduplicated']


def make_sess():
    s = req_lib.Session()
    s.proxies = {'https': PROXY, 'http': PROXY}
    s.verify = CA_BUNDLE
    s.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    return s


def route_handler(sess):
    def h(route: Route):
        rq = route.request
        headers = {k: v for k, v in rq.headers.items() if k.lower() != 'host'}
        try:
            r = sess.request(rq.method, rq.url, headers=headers,
                            data=rq.post_data.encode() if rq.post_data else None,
                            timeout=20, allow_redirects=True)
            hdrs = {k: v for k, v in r.headers.items()
                    if k.lower() not in ('content-encoding', 'transfer-encoding')}
            route.fulfill(status=r.status_code, headers=hdrs, body=r.content)
        except:
            route.abort()
    return h


def filter_url(base, catoid, navoid, page=1, limit=40):
    return (f"{base}/content.php?catoid={catoid}&navoid={navoid}"
            f"&filter%5Bitem_type%5D=3&filter%5Bonly_active%5D=1"
            f"&filter%5B3%5D=1&filter%5Bcpage%5D={page}&filter%5Blimit%5D={limit}")


def get_course_ids(pw_page, base, catoid, navoid):
    """Get all (coid, title) from Acalog filter pages using Playwright."""
    coids = []
    pg = 1
    seen = set()
    while True:
        url = filter_url(base, catoid, navoid, pg)
        if url in seen:
            break
        seen.add(url)
        try:
            pw_page.goto(url, wait_until='networkidle', timeout=60000)
            content = pw_page.content()
            soup = BeautifulSoup(content, 'html.parser')

            links = soup.find_all('a', href=re.compile(r'preview_course_nopop.*coid=\d+'))
            if not links:
                log.info(f"    p{pg}: 0 courses → done")
                break

            for a in links:
                m = re.search(r'coid=(\d+)', a['href'])
                if m:
                    coids.append((int(m.group(1)), a.get_text(strip=True)))

            log.info(f"    p{pg}: {len(links)} courses (total {len(coids)})")

            # Find next page link
            next_pg = None
            for a in soup.find_all('a', href=re.compile(r'cpage=\d+')):
                m = re.search(r'cpage=(\d+)', a['href'])
                if m and int(m.group(1)) > pg:
                    candidate = int(m.group(1))
                    if next_pg is None or candidate < next_pg:
                        next_pg = candidate

            if not next_pg:
                # Check for Next text link
                for a in soup.find_all('a'):
                    t = a.get_text(strip=True).lower().strip()
                    if t in ('next', '>', '>>', '›') or re.match(r'next\b', t):
                        m = re.search(r'cpage=(\d+)', a.get('href', ''))
                        if m:
                            next_pg = int(m.group(1))
                            break

            if next_pg:
                pg = next_pg
            else:
                log.info(f"    No next page after p{pg}")
                break
        except Exception as e:
            log.error(f"    Filter p{pg} error: {e}")
            break

    return coids


def parse_detail_html(html):
    """Parse Acalog course detail HTML → course dict."""
    soup = BeautifulSoup(html, 'html.parser')

    # Title from <title> tag: "DEPT 101 Course Title - University Name"
    page_title = soup.find('title')
    title_text = ''
    if page_title:
        pt = page_title.get_text(strip=True)
        if ' - ' in pt:
            title_text = pt.split(' - ')[0].strip()
        else:
            title_text = pt.strip()

    # Fallback: look in h1/h2/strong in body
    if not title_text:
        block = soup.find('td', class_=re.compile(r'block_content')) or \
                soup.find('div', class_=re.compile(r'block_content')) or \
                soup.find('body')
        if block:
            for el in block.find_all(['h1', 'h2', 'strong']):
                t = el.get_text(' ', strip=True)
                if re.match(r'[A-Z]', t) and len(t) > 3:
                    title_text = t
                    break

    # Parse "DEPT 101 Title"
    m = re.match(r'^([A-Z][A-Z ]{0,7})\s+(\w+)\s+(.*)', title_text.strip())
    if m:
        dept = m.group(1).strip()
        num = m.group(2)
        title = m.group(3).strip()
    else:
        dept, num = '', ''
        title = title_text

    # Description: look for paragraphs in the main content block
    block = soup.find('td', class_=re.compile(r'block_content')) or \
            soup.find('div', class_=re.compile(r'block_content')) or \
            soup.find('div', id=re.compile(r'course', re.I)) or \
            soup.find('body')

    desc = ''
    if block:
        paras = block.find_all('p')
        desc_parts = [p.get_text(' ', strip=True) for p in paras if len(p.get_text(strip=True)) > 15]
        desc = ' '.join(desc_parts)
        if not desc:
            full = block.get_text(' ', strip=True)
            desc = full.replace(title_text, '', 1).strip()[:2000]

    if not title and not dept:
        return None

    combined = f"{title} {desc}"
    return {
        'dept_code': dept,
        'course_number': num,
        'title': title,
        'description': desc[:2000],
        'broad_area': broad_area(dept),
        'level': course_level(num),
        'progressive_signal': sig(combined, PROGRESSIVE_KEYWORDS),
        'western_canon_signal': sig(combined, WESTERN_CANON_KEYWORDS),
        'climate_narrow_signal': sig(combined, CLIMATE_NARROW_KEYWORDS),
        'climate_broad_signal': sig(combined, CLIMATE_BROAD_KEYWORDS),
        'cross_listed': 0,
        'deduplicated': 0,
    }


def fetch_detail(sess, base, catoid, coid):
    """Fetch one course detail page with requests."""
    url = f"{base}/preview_course_nopop.php?catoid={catoid}&coid={coid}"
    try:
        r = sess.get(url, timeout=15)
        if r.status_code == 200 and len(r.content) > 100:
            return parse_detail_html(r.text)
    except Exception as e:
        log.debug(f"detail {coid}: {e}")
    return None


def scrape_uni(key, cfg, sess, pw_page):
    base, name = cfg['base'], cfg['name']
    catoid, navoid = cfg['catoid'], cfg['navoid']
    log.info(f"\n{'='*60}\nScraping {key}: {name}")

    # Test connectivity
    try:
        r = sess.get(base + '/', timeout=15)
        if r.status_code not in (200, 202):
            log.error(f"  HTTP {r.status_code}")
            return [], 'blocked_by_network'
    except Exception as e:
        err = str(e)
        log.error(f"  Connectivity failed: {err[:100]}")
        if any(x in err.lower() for x in ('502', 'proxy', 'refused', 'tunnel')):
            return [], 'blocked_by_network'
        return [], 'failed'

    # Output filename — use key-named subdirectory matching other scrapers' pattern
    ay = '2024_2025'
    ay_label = '2024-2025'
    uni_dir = DATA_DIR / key
    uni_dir.mkdir(exist_ok=True)
    outfile = uni_dir / f"{key}_{ay}.csv"

    if outfile.exists():
        log.info(f"  Already exists: {outfile}")
        return [str(outfile)], 'completed'

    # Init Playwright for WAF cookie — use domcontentloaded + wait_for_selector
    # WAF returns HTTP 202 + JS challenge; page reloads after JS completes.
    # networkidle fires too early (before WAF JS finishes), so we wait for actual course links.
    log.info(f"  Loading filter page (WAF init)...")
    init_url = filter_url(base, catoid, navoid, 1, 40)
    try:
        pw_page.goto(init_url, wait_until='domcontentloaded', timeout=60000)
        pw_page.wait_for_selector('a[href*="preview_course"]', timeout=90000)
    except Exception as e:
        log.error(f"  Playwright init failed: {e}")
        return [], 'failed'

    # Extract WAF cookies → requests session
    cookies = pw_page.context.cookies()
    domain = base.replace('https://', '').replace('http://', '').split('/')[0]
    added = 0
    for c in cookies:
        cd = c.get('domain', '').lstrip('.')
        if cd in domain or domain in cd:
            sess.cookies.set(c['name'], c['value'], domain=cd)
            added += 1
    log.info(f"  Added {added}/{len(cookies)} cookies to requests session")

    # Parse course IDs from first filter page (already rendered by Playwright)
    first_content = pw_page.content()
    soup = BeautifulSoup(first_content, 'html.parser')
    first_links = soup.find_all('a', href=re.compile(r'preview_course_nopop.*coid=\d+'))
    log.info(f"  First page: {len(first_links)} course links")

    if not first_links:
        log.error(f"  No course links found on first page!")
        log.info(f"  Title: {pw_page.title()}")
        return [], 'failed'

    coids = []
    for a in first_links:
        m = re.search(r'coid=(\d+)', a['href'])
        if m:
            coids.append((int(m.group(1)), a.get_text(strip=True)))

    # Paginate via requests (WAF cookies already in sess) — Acalog pagination is JS-driven,
    # so don't look for cpage links in HTML. Instead iterate pages until 0 results.
    pg = 2
    consecutive_empty = 0
    while consecutive_empty < 2:
        url = filter_url(base, catoid, navoid, pg, 40)
        try:
            r = sess.get(url, timeout=20)
            if r.status_code == 202:
                # WAF challenge re-triggered — use Playwright for this page
                log.info(f"    p{pg}: WAF re-triggered (202), using Playwright...")
                pw_page.goto(url, wait_until='domcontentloaded', timeout=60000)
                try:
                    pw_page.wait_for_selector('a[href*="preview_course"]', timeout=30000)
                except Exception:
                    pass
                page_soup = BeautifulSoup(pw_page.content(), 'html.parser')
                # Refresh cookies
                for c in pw_page.context.cookies():
                    cd = c.get('domain', '').lstrip('.')
                    if cd in domain or domain in cd:
                        sess.cookies.set(c['name'], c['value'], domain=cd)
            else:
                page_soup = BeautifulSoup(r.text, 'html.parser')

            links = page_soup.find_all('a', href=re.compile(r'preview_course_nopop.*coid=\d+'))
            if not links:
                consecutive_empty += 1
                log.info(f"    p{pg}: 0 courses (empty #{consecutive_empty})")
            else:
                consecutive_empty = 0
                for a in links:
                    m = re.search(r'coid=(\d+)', a['href'])
                    if m:
                        coids.append((int(m.group(1)), a.get_text(strip=True)))
                log.info(f"    p{pg}: {len(links)} courses (total {len(coids)})")
        except Exception as e:
            log.error(f"    p{pg} error: {e}")
            consecutive_empty += 1

        pg += 1
        if pg > 500:  # Safety cap
            break

    log.info(f"  Total course IDs: {len(coids)}")

    # Fetch details in parallel with requests
    log.info(f"  Fetching course details (10 workers)...")
    rows = []
    done = 0

    def fetch_one(item):
        coid, hint = item
        return coid, hint, fetch_detail(sess, base, catoid, coid)

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(fetch_one, c): c for c in coids}
        for fut in as_completed(futs):
            done += 1
            if done % 500 == 0:
                log.info(f"    {done}/{len(coids)} done, {len(rows)} parsed")
            try:
                coid, hint, course = fut.result()
                if course and (course['dept_code'] or course['title']):
                    rows.append({
                        'university': name,
                        'academic_year': ay,
                        'academic_year_label': ay_label,
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
            except Exception as e:
                log.debug(f"  future err: {e}")

    log.info(f"  Parsed {len(rows)} / {len(coids)}")

    if rows:
        with open(outfile, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        log.info(f"  Saved: {outfile}")
        return [str(outfile)], 'completed'
    else:
        log.warning(f"  No rows saved!")
        return [], 'failed'


def update_progress(key, status, data_files, notes='', name=None):
    pfile = ROOT / 'progress.json'
    with open(pfile) as f:
        p = json.load(f)
    if key not in p['universities']:
        p['universities'][key] = {}
    u = p['universities'][key]
    u['status'] = status
    if name: u['name'] = name
    if data_files:
        u['data_files'] = data_files
        total, prog, canon = 0, 0, 0
        for fp in data_files:
            try:
                with open(fp) as f:
                    for row in csv.DictReader(f):
                        total += 1
                        if row.get('progressive_signal') == '1': prog += 1
                        if row.get('western_canon_signal') == '1': canon += 1
            except: pass
        u['courses_count'] = total
        u['progressive_pct'] = round(prog/total*100,2) if total else 0
        u['canon_pct'] = round(canon/total*100,2) if total else 0

    # Clean from dynamic_js_only if now completed/failed
    if key in p.get('dynamic_js_only', []) and status != 'dynamic_js_only':
        p['dynamic_js_only'].remove(key)
    if status == 'blocked_by_network' and key not in p.get('blocked_by_network', []):
        p.setdefault('blocked_by_network', []).append(key)
        if key in p.get('dynamic_js_only', []):
            p['dynamic_js_only'].remove(key)

    if notes: u['notes'] = notes
    p['completed'] = sum(1 for v in p['universities'].values() if v.get('status') == 'completed')

    import datetime
    p['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    with open(pfile, 'w') as f:
        json.dump(p, f, indent=2)
    log.info(f"  progress.json: {key} → {status} ({p['completed']} total completed)")


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(UNIS.keys())
    log.info(f"Targets: {targets}")
    sess = make_sess()  # noqa: F811 (duplicate removed below)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path='/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu',
                  '--proxy-server=direct://'],
        )
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(60000)
        page.route('**/*', route_handler(sess))

        for key in targets:
            cfg = UNIS.get(key)
            if not cfg:
                log.warning(f"Unknown: {key}")
                continue
            try:
                files, status = scrape_uni(key, cfg, sess, page)
                update_progress(key, status, files, name=cfg['name'])
            except Exception as e:
                log.error(f"{key} failed: {e}", exc_info=True)
                update_progress(key, 'failed', [], notes=str(e)[:200], name=cfg.get('name',''))

        browser.close()
    log.info("All done!")


if __name__ == '__main__':
    main()
