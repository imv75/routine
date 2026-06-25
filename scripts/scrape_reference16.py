#!/usr/bin/env python3
"""Re-scrape 2026 catalogs for the technically-accessible reference-paper universities.

Targets (7 of 16): stanford (ExploreCourses XML), mit, northwestern, nyu, uiuc,
uiowa (CourseleafCMS variants), cornell (roster JSON API).

The other 9 reference universities (berkeley, harvard, yale, princeton, uchicago,
columbia, vanderbilt, utaustin, tamu) are dynamic-JS SPAs or blocked from the proxy
and are left with their published Marinovic (2026) values.
"""
import os, re, csv, json, time, requests
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

CA = os.environ.get('REQUESTS_CA_BUNDLE', '/root/.ccr/ca-bundle.crt')
YEAR = "2026"; YEAR_LABEL = "2026-2027"

# Canonical lists shared by the 84 already-scraped catalogs (and Tables 2-3 of the paper).
PROGRESSIVE_KEYWORDS = [
    "diversity", "diverse", "inclusion", "inclusive", "belonging", "dei",
    "race", "racial", "racism", "racist", "anti-racist", "antiracist",
    "racialized", "white supremacy", "white privilege", "whiteness",
    "bipoc", "people of color", "black lives", "critical race",
    "gender", "gendered", "feminist", "feminism", "sexism", "patriarchy",
    "misogyny", "queer", "lgbtq", "transgender", "nonbinary", "intersex",
    "sexuality", "heteronormativity",
    "equity", "equitable", "social justice", "injustice", "oppression",
    "oppressive", "liberation", "decolonize", "decolonial", "colonialism",
    "colonial", "postcolonial", "settler colonialism",
    "identity", "identities", "positionality", "intersectionality", "privilege",
    "marginalized", "marginalization", "underrepresented", "allyship",
    "indigenous", "native american", "latinx", "chicano", "chicana",
    "diaspora", "reparations", "microaggression", "implicit bias", "systemic racism",
]
WESTERN_CANON_KEYWORDS = [
    "western civilization", "western tradition", "western thought",
    "great books", "liberal arts tradition",
    "ancient greece", "ancient rome", "greek philosophy", "roman law",
    "classical antiquity", "greco-roman",
    "renaissance", "enlightenment", "medieval philosophy", "reformation",
    "shakespeare", "plato", "aristotle", "homer", "dante", "virgil",
    "milton", "cicero", "socrates", "augustine", "aquinas", "machiavelli",
    "hobbes", "descartes", "kant", "hegel", "locke", "tocqueville", "montesquieu",
    "bible", "biblical", "iliad", "odyssey", "aeneid", "divine comedy",
    "canterbury tales", "leviathan", "federalist", "classics", "classical",
]
CLIMATE_NARROW = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]
CLIMATE_BROAD = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]
BROAD_AREA_MAP = {
    "Social Sciences": ["sociology","psychology","political","economics","anthropology","geography","social work","criminal justice","criminology","public policy","communication"],
    "Humanities": ["english","literature","history","philosophy","religious","theology","art history","music","theater","theatre","linguistics","classics","french","spanish","german","chinese","japanese","arabic","latin","language"],
    "STEM": ["mathematics","statistics","physics","chemistry","biology","computer","engineering","geology","astronomy","neuroscience","data science"],
    "Medical Sciences": ["nursing","medicine","health science","pharmacy","dentistry","kinesiology","public health","nutrition","occupational therapy","physical therapy"],
    "Professional": ["business","accounting","finance","management","marketing","law","education","social work","architecture"],
}

def classify_area(dept, title, desc):
    text = (dept + " " + title + " " + desc).lower()
    for area, kws in BROAD_AREA_MAP.items():
        if any(kw in text for kw in kws):
            return area
    return "Other"

def has_kw(text, kws):
    tl = text.lower()
    return any(k in tl for k in kws)

def level_from_num(num):
    m = re.search(r'\d+', num or '')
    if not m: return "unknown"
    n = int(m.group())
    return "lower" if n < 100 else ("upper" if n < 500 else "graduate")

def make_session():
    s = requests.Session(); s.verify = CA
    s.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120'
    return s

def get(session, url, retries=3, timeout=30):
    for a in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.text
            return None
        except Exception as e:
            if a < retries-1:
                time.sleep(0.8*(a+1)); session = make_session()
    return None

def write_uni(uni, courses):
    """courses: list of (dept, num, title, desc). Writes CSV + summary, returns summary."""
    out = f"/home/user/routine/data/{uni}"
    os.makedirs(out, exist_ok=True)
    rows = []; seen = set()
    for dept, num, title, desc in courses:
        dept = (dept or '').strip(); num = (num or '').strip()
        title = (title or '').strip(); desc = (desc or '').strip()
        if not dept or not title:
            continue
        key = (dept, num, title)
        dedup = "yes" if key in seen else "no"
        seen.add(key)
        text = title + " " + desc
        rows.append({
            "university": uni, "academic_year": YEAR, "academic_year_label": YEAR_LABEL,
            "department_code": dept, "course_number": num, "title": title, "description": desc,
            "broad_area": classify_area(dept, title, desc), "level": level_from_num(num),
            "progressive_signal": "yes" if has_kw(text, PROGRESSIVE_KEYWORDS) else "no",
            "western_canon_signal": "yes" if has_kw(text, WESTERN_CANON_KEYWORDS) else "no",
            "climate_narrow_signal": "yes" if has_kw(text, CLIMATE_NARROW) else "no",
            "climate_broad_signal": "yes" if has_kw(text, CLIMATE_BROAD) else "no",
            "cross_listed": "no", "deduplicated": dedup,
        })
    fields = ["university","academic_year","academic_year_label","department_code","course_number",
              "title","description","broad_area","level","progressive_signal","western_canon_signal",
              "climate_narrow_signal","climate_broad_signal","cross_listed","deduplicated"]
    with open(f"{out}/{uni}_{YEAR}.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    uniq = [r for r in rows if r['deduplicated'] == 'no']
    tot = len(uniq)
    def pct(sig): return round(100*sum(1 for r in uniq if r[sig]=='yes')/tot, 2) if tot else 0
    by_area = {}
    for r in uniq: by_area[r['broad_area']] = by_area.get(r['broad_area'],0)+1
    summ = {
        "university": uni, "academic_year": YEAR, "academic_year_label": YEAR_LABEL,
        "total_courses": tot,
        "progressive_count": sum(1 for r in uniq if r['progressive_signal']=='yes'), "progressive_pct": pct('progressive_signal'),
        "canon_count": sum(1 for r in uniq if r['western_canon_signal']=='yes'), "canon_pct": pct('western_canon_signal'),
        "climate_narrow_count": sum(1 for r in uniq if r['climate_narrow_signal']=='yes'), "climate_narrow_pct": pct('climate_narrow_signal'),
        "climate_broad_count": sum(1 for r in uniq if r['climate_broad_signal']=='yes'), "climate_broad_pct": pct('climate_broad_signal'),
        "by_area": by_area, "source": "rescraped_2026",
    }
    with open(f"{out}/{uni}_summary.json", 'w') as f: json.dump(summ, f, indent=2)
    print(f"  -> {uni}: {tot} courses, prog {summ['progressive_pct']}%, canon {summ['canon_pct']}%")
    return summ

# ---------------- Stanford: ExploreCourses XML ----------------
def scrape_stanford():
    print("Stanford (ExploreCourses XML)...")
    s = make_session()
    root_xml = get(s, 'https://explorecourses.stanford.edu/?view=xml-20200810')
    depts = sorted(set(re.findall(r'<department[^>]*name="([^"]+)"', root_xml)))
    print(f"  {len(depts)} departments")
    courses = []
    for i, d in enumerate(depts):
        url = (f'https://explorecourses.stanford.edu/search?view=xml-20200810'
               f'&academicYear=20252026&q={d}&filter-coursestatus-Active=on&filter-departmentcode-{d}=on')
        xml = get(s, url, timeout=60)
        if not xml:
            time.sleep(0.3); continue
        try:
            r = ET.fromstring(xml)
        except Exception:
            time.sleep(0.3); continue
        added = 0
        for c in r.findall('.//course'):
            subj = (c.findtext('subject') or '').strip()
            code = (c.findtext('code') or '').strip()
            title = (c.findtext('title') or '').strip()
            desc = (c.findtext('description') or '').strip()
            if subj != d:  # keep only exact-subject rows to avoid cross-list inflation
                continue
            courses.append((subj, code, title, desc)); added += 1
        if (i+1) % 40 == 0: print(f"    {i+1}/{len(depts)} depts, {len(courses)} courses")
        time.sleep(0.2)
    return write_uni('stanford', courses)

# ---------------- Cornell: roster JSON API ----------------
def scrape_cornell():
    print("Cornell (roster API)...")
    s = make_session()
    # pick latest roster
    rosters = s.get('https://classes.cornell.edu/api/2.0/config/rosters.json', timeout=30).json()
    rlist = [r['slug'] for r in rosters['data']['rosters']]
    roster = [r for r in rlist if r.startswith('FA')][-1] if any(x.startswith('FA') for x in rlist) else rlist[-1]
    print(f"  roster {roster}")
    subs = s.get(f'https://classes.cornell.edu/api/2.0/config/subjects.json?roster={roster}', timeout=30).json()
    sub_codes = [x['value'] for x in subs['data']['subjects']]
    print(f"  {len(sub_codes)} subjects")
    courses = []
    for i, sub in enumerate(sub_codes):
        try:
            j = s.get(f'https://classes.cornell.edu/api/2.0/search/classes.json?roster={roster}&subject={sub}', timeout=30).json()
        except Exception:
            time.sleep(0.3); s = make_session(); continue
        for c in j.get('data', {}).get('classes', []):
            courses.append((c.get('subject',''), str(c.get('catalogNbr','')),
                            c.get('titleLong') or c.get('titleShort') or '',
                            c.get('description') or ''))
        if (i+1) % 50 == 0: print(f"    {i+1}/{len(sub_codes)} subjects, {len(courses)} courses")
        time.sleep(0.15)
    return write_uni('cornell', courses)

# ---------------- CourseleafCMS variants ----------------
def parse_courseleaf(html, mode):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for b in soup.find_all(class_="courseblock"):
        if mode == 'detail':  # nyu: span.detail-code + span.detail-title
            dc = b.find('span', class_='detail-code'); dt = b.find('span', class_='detail-title')
            if not dc: continue
            code_str = dc.get_text(' ', strip=True)
            m = re.match(r'([A-Z][A-Z0-9&-]*)[\s-]+(\d+[A-Z]?)', code_str)
            if not m: continue
            dept, num = m.group(1), m.group(2)
            title = dt.get_text(' ', strip=True) if dt else ''
            desc = ''
            d = b.find(class_='courseblockdesc') or b.find(class_='courseblockextra')
            if d: desc = d.get_text(' ', strip=True)
            out.append((dept, num, title, desc)); continue
        # title-block modes
        tp = b.find(class_='courseblocktitle')
        if not tp: continue
        for sp in tp.find_all('span'):
            cls = ' '.join(sp.get('class', [])).lower()
            if 'credit' in cls or 'hour' in cls or 'tccn' in cls:
                sp.decompose()
        txt = tp.get_text(' ', strip=True).replace('\xa0', ' ').replace(' ', ' ')
        txt = re.sub(r'\s+', ' ', txt)
        dept = num = title = ''
        if mode == 'mit':         # "6.1000 Introduction to Programming..."
            m = re.match(r'([A-Z0-9.]+?)\.(\d+[A-Z]*)\s+(.+)', txt) or re.match(r'(\S+)\s+(.+)', txt)
            if m and m.lastindex == 3:
                dept, num, title = m.group(1), m.group(2), m.group(3)
            elif m:
                code, title = m.group(1), m.group(2)
                pm = code.split('.')
                dept, num = pm[0], (pm[1] if len(pm) > 1 else '')
        elif mode == 'colon':     # uiowa "ACCT:1300 First-Year Seminar 1 s.h."
            m = re.match(r'([A-Z][A-Z0-9&]*):(\d+[A-Z]?)\s+(.+)', txt)
            if m: dept, num, title = m.group(1), m.group(2), m.group(3)
        else:                     # 'space': uiuc "ACCY 199 Title credit..", nw "AFST 101-7 Title"
            m = re.match(r'([A-Z][A-Z0-9&]*)\s+(\d+[A-Z]?(?:-\d+)?)\s+(.+)', txt)
            if m: dept, num, title = m.group(1), m.group(2), m.group(3)
        if not dept or not title: continue
        # strip trailing credit/hours noise from title
        title = re.split(r'\s+(?:credit:|\d+(?:\.\d+)?\s*(?:s\.h\.|Hours|Unit))', title)[0].strip(' .')
        desc = ''
        d = b.find(class_='courseblockdesc') or b.find(class_='courseblockextra')
        if d: desc = d.get_text(' ', strip=True)
        out.append((dept, num, title, desc))
    return out

def scrape_courseleaf(uni, index_url, slug_pattern, dept_url_fn, mode):
    print(f"{uni} (CourseleafCMS/{mode})...")
    s = make_session()
    idx = get(s, index_url)
    slugs = sorted(set(re.findall(slug_pattern, idx)))
    print(f"  {len(slugs)} departments")
    courses = []; failed = []
    for i, slug in enumerate(slugs):
        html = get(s, dept_url_fn(slug))
        if not html:
            failed.append(slug); time.sleep(0.4); continue
        courses += parse_courseleaf(html, mode)
        if (i+1) % 50 == 0: print(f"    {i+1}/{len(slugs)} depts, {len(courses)} courses")
        time.sleep(0.2)
    if failed: print(f"  failed depts: {len(failed)}")
    summ = write_uni(uni, courses)
    summ['failed_depts'] = failed
    with open(f"/home/user/routine/data/{uni}/{uni}_summary.json", 'w') as f:
        json.dump(summ, f, indent=2)
    return summ

if __name__ == "__main__":
    import sys
    targets = sys.argv[1:] or ['stanford','cornell','mit','northwestern','nyu','uiuc','uiowa']
    if 'stanford' in targets: scrape_stanford()
    if 'cornell' in targets: scrape_cornell()
    if 'mit' in targets:
        scrape_courseleaf('mit', 'https://catalog.mit.edu/subjects/',
            r'/subjects/([a-z0-9]+)/', lambda s: f'https://catalog.mit.edu/subjects/{s}/', 'mit')
    if 'northwestern' in targets:
        scrape_courseleaf('northwestern', 'https://catalogs.northwestern.edu/undergraduate/courses-az/',
            r'/undergraduate/courses-az/([a-z0-9_]+)/',
            lambda s: f'https://catalogs.northwestern.edu/undergraduate/courses-az/{s}/', 'space')
    if 'nyu' in targets:
        scrape_courseleaf('nyu', 'https://bulletins.nyu.edu/courses/',
            r'/courses/([a-z0-9_-]+)/', lambda s: f'https://bulletins.nyu.edu/courses/{s}/', 'detail')
    if 'uiuc' in targets:
        scrape_courseleaf('uiuc', 'https://catalog.illinois.edu/courses-of-instruction/',
            r'/courses-of-instruction/([a-z0-9]+)/',
            lambda s: f'https://catalog.illinois.edu/courses-of-instruction/{s}/', 'space')
    if 'uiowa' in targets:
        scrape_courseleaf('uiowa', 'https://catalog.registrar.uiowa.edu/courses/',
            r'/courses/([a-z0-9_-]+)/',
            lambda s: f'https://catalog.registrar.uiowa.edu/courses/{s}/', 'colon')
    print("DONE")
