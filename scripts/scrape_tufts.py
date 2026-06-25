#!/usr/bin/env python3
"""
Tufts University course catalog scraper.
URL: as.tufts.edu/{dept}/academics/courses  (and various subdomains)
HTML: <p> paragraphs with format "DEPT NUM Title. Description."
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "tufts"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
OUTPUT_DIR = f"/home/user/routine/data/{UNIVERSITY}"
OUTPUT_CSV = f"{OUTPUT_DIR}/{UNIVERSITY}_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/{UNIVERSITY}_summary.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

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
CLIMATE_NARROW = ["climate change", "global warming", "greenhouse gas", "carbon emission",
                   "fossil fuel", "sea level rise", "climate crisis"]
CLIMATE_BROAD = ["climate", "sustainability", "sustainable", "renewable energy",
                  "environmental justice", "carbon", "decarbonization", "net zero",
                  "clean energy", "green energy", "ecological", "ecosystem", "biodiversity"]

STEM = {
    "bio", "biol", "chem", "cs", "ce", "ece", "ee", "es", "eas", "env", "engs",
    "math", "me", "mse", "neur", "phys", "stat", "engr", "eng",
    "bme", "chbe", "civl", "data", "ds", "geol", "geo", "sci",
}
HUMANITIES = {
    "anth", "art", "arth", "chin", "clas", "coml", "cult", "drama", "eng",
    "engl", "fren", "germ", "grek", "hist", "ilvs", "ilcs", "ital", "jap",
    "jst", "judaic", "latn", "ling", "lit", "medieval", "mid", "mus",
    "phil", "port", "rcd", "reli", "rel", "rom", "russ", "span", "tdps",
    "theater", "thtr", "wgss",
}
SOCIAL = {
    "anth", "comm", "econ", "educ", "fms", "geog", "gov", "ir",
    "pols", "polsci", "ps", "psych", "soc", "sociol", "sts",
}
MEDICAL = {
    "comm", "ot", "pt", "pub", "pub-hlth", "nurs", "dent", "vet",
    "biomed", "pharm", "anat", "path",
}
PROFESSIONAL = {
    "arch", "bus", "law", "mba", "educ", "plan", "policy", "pub",
    "ldst", "museum", "ms",
}


def classify_area(dept):
    d = dept.lower().rstrip("0123456789")
    if d in STEM:
        return "STEM"
    if d in HUMANITIES:
        return "Humanities"
    if d in SOCIAL:
        return "Social Sciences"
    if d in MEDICAL:
        return "Medical Sciences"
    if d in PROFESSIONAL:
        return "Professional"
    return "Other"


def classify_level(num_str):
    digits = re.sub(r"[^0-9]", "", str(num_str))
    if not digits:
        return "undergraduate"
    n = int(digits[:4].lstrip("0") or "0")
    return "graduate" if n >= 200 else "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


# Department URL list
# Format: (dept_code, url)
DEPT_URLS = [
    # School of Arts & Sciences — main pattern
    ("ANTH", "https://as.tufts.edu/anthropology/academics/courses"),
    ("BIO",  "https://as.tufts.edu/biology/academics/courses"),
    ("CLAS", "https://as.tufts.edu/classicalstudies/academics/courses"),
    ("EPCSHD","https://as.tufts.edu/epcshd/academics/courses"),
    ("ECS",  "https://as.tufts.edu/ecs/academics/courses"),
    ("ECON", "https://as.tufts.edu/economics/academics/courses"),
    ("EDUC", "https://as.tufts.edu/education/academics/courses"),
    ("ENG",  "https://as.tufts.edu/english/academics/courses"),
    ("ARTH", "https://as.tufts.edu/art-architecture/academics/courses"),
    ("ILCS", "https://as.tufts.edu/ilcs/academics/courses"),
    ("MUS",  "https://as.tufts.edu/music/academics/courses"),
    ("OT",   "https://as.tufts.edu/occupationaltherapy/academics/courses"),
    ("PHIL", "https://as.tufts.edu/philosophy/academics/courses"),
    ("PHYS", "https://as.tufts.edu/physics/academics/courses"),
    ("PS",   "https://as.tufts.edu/politicalscience/academics/courses"),
    ("PSYC", "https://as.tufts.edu/psychology/academics/courses"),
    ("REL",  "https://as.tufts.edu/religion/academics/courses"),
    ("ROM",  "https://as.tufts.edu/romancestudies/academics/courses"),
    ("RCD",  "https://as.tufts.edu/rcd/academics/courses"),
    ("SOC",  "https://as.tufts.edu/sociology/academics/courses"),
    ("WGSS", "https://as.tufts.edu/wgss/academics/courses"),
    ("DATA", "https://as.tufts.edu/dataanalytics/academics/courses"),
    ("FMS",  "https://as.tufts.edu/fms/academics/courses"),
    ("JST",  "https://as.tufts.edu/judaic-studies/courses"),
    ("LAST", "https://as.tufts.edu/latin-american-studies/courses"),
    ("LDST", "https://as.tufts.edu/leadershipprogram/academics/courses"),
    ("MED",  "https://as.tufts.edu/medieval-studies/academics/courses"),
    ("MES",  "https://as.tufts.edu/middle-eastern-studies/academics/courses"),
    ("STS",  "https://as.tufts.edu/science-technology-and-society/courses"),
    ("ILVS", "https://as.tufts.edu/international-literary-and-visual-studies/courses"),
    ("ENV",  "https://as.tufts.edu/environmentalstudies/academics/courses"),
    # Special subdomains — same /academics/courses pattern
    ("CHEM", "https://chem.tufts.edu/academics/courses"),
    ("MATH", "https://math.tufts.edu/academics/courses"),
    ("TDPS", "https://tdps.tufts.edu/academics/courses"),
    ("COGSCI","https://cogsci.tufts.edu/academics/courses"),
    ("MUSEUM","https://museumstudies.tufts.edu/academics/courses"),
]

# Paragraph course pattern: DEPT NUM Title. Description.
# Format 1 (standard): "DEPT NUM Title. Description." — everything in one <p>
COURSE_RE_STD = re.compile(
    r'^([A-Za-z]{2,8})\s+'                # dept code (may be mixed case: "Bio", "ANTH")
    r'([\d][^\s.]*|[A-Z]{2,3})\s+'       # course number or special (AP, IB)
    r'(.+?)\.\s*'                          # title (up to first period)
    r'(.+)$',                              # description (must be non-empty)
    re.DOTALL
)

# Format 2 (number-only): "0001 Title. Description." — dept implicit from page
COURSE_RE_NUM = re.compile(
    r'^(0\d{3}|\d{2,3})\s+'             # 4-digit zero-padded or 2-3 digit number
    r'(.+?)\.\s*'                         # title
    r'(.+)$',                             # description
    re.DOTALL
)

# Format 3 (split): title in one <p>, description in next <p>
# "DEPT NUM Title" then separate paragraph with description
COURSE_RE_HEAD = re.compile(
    r'^([A-Za-z]{2,8})\s+'
    r'([\d][^\s]*)\s+'
    r'(.+)$'
)

# Format 4 (dash-dept): "FMS- 0001 Title . CrossRef Description"
# Dept code has a trailing dash; cross-list codes appear before description
COURSE_RE_DASH = re.compile(
    r'^([A-Za-z]{2,8})-\s+'
    r'(\d[\d\w]*)\s+'
    r'(.+?)\s*\.\s*'
    r'(.+)$',
    re.DOTALL
)
# Strip leading cross-list codes (e.g. "ILVS-0051, TPS-0020 ") from a string
_CROSSLIST_PREFIX_RE = re.compile(
    r'^(?:[A-Z]{2,8}-\d+(?:\s*/\s*[A-Z]{2,8}-\d+)*(?:\s*,\s*[A-Z]{2,8}-\d+)*\s+)+'
)


def make_record(dept, num, title, desc):
    """Build a course record dict."""
    dept_upper = dept.upper()
    # Remove cross-list refs from title
    title = re.sub(r'\s*(?:Cross-listed as|cross-listed as)[^.]*', '', title).strip()
    title = re.sub(r'\s*\([A-Z]{2,6}\s+[\d/\s]+[A-Z]*\s*/*\s*[A-Z]*\s*[\d]*\)\s*$', '', title).strip()
    if len(title) < 3:
        return None
    full_text = f"{title} {desc}"
    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept_upper,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept_upper),
        "level": classify_level(num),
        "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
        "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
        "cross_listed": False,
        "deduplicated": True,
    }


def parse_paras(paras, fallback_dept):
    """Parse all paragraphs from a department page into course records."""
    courses = []
    i = 0
    while i < len(paras):
        text = paras[i].get_text(" ", strip=True)
        if not text or len(text) < 5:
            i += 1
            continue

        # Try format 4: dash-dept (e.g. "FMS- 0001 Title . CrossRef Description")
        m4 = COURSE_RE_DASH.match(text)
        if m4:
            raw_desc = m4.group(4).strip()
            desc = _CROSSLIST_PREFIX_RE.sub('', raw_desc).strip()
            if re.search(r'[a-z]', desc):
                c = make_record(m4.group(1), m4.group(2), m4.group(3).strip(), desc)
                if c:
                    courses.append(c)
                i += 1
                continue

        # Try format 1: standard all-in-one
        m = COURSE_RE_STD.match(text)
        if m and re.search(r'[a-z]', m.group(4)):  # desc must have lowercase
            c = make_record(m.group(1), m.group(2), m.group(3).strip(), m.group(4).strip())
            if c:
                courses.append(c)
            i += 1
            continue

        # Try format 2: number-only (no dept prefix)
        m2 = COURSE_RE_NUM.match(text)
        if m2 and fallback_dept and re.search(r'[a-z]', m2.group(3)):
            c = make_record(fallback_dept, m2.group(1), m2.group(2).strip(), m2.group(3).strip())
            if c:
                courses.append(c)
            i += 1
            continue

        # Try format 3: title-only heading, description in next para
        m3 = COURSE_RE_HEAD.match(text)
        if m3 and i + 1 < len(paras):
            next_text = paras[i + 1].get_text(" ", strip=True)
            # Check that next para looks like a description (has lowercase, > 30 chars)
            if next_text and len(next_text) > 30 and re.search(r'[a-z]{5}', next_text):
                title = m3.group(3).strip().rstrip('.')
                c = make_record(m3.group(1), m3.group(2), title, next_text)
                if c:
                    courses.append(c)
                    i += 2
                    continue

        i += 1
    return courses


def scrape_dept(session, dept_code, url):
    """Fetch and parse a department's course page."""
    try:
        r = session.get(url, timeout=25, allow_redirects=True)
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.content, "html.parser")
        main = soup.find("main") or soup.find("div", class_="layout-container") or soup
        paras = list(main.find_all("p"))
        courses = parse_paras(paras, fallback_dept=dept_code)
        return courses, None
    except Exception as e:
        return [], str(e)[:80]


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; academic research crawler)"
    })

    print(f"=== Tufts University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    all_courses = []
    seen = set()
    failed = []
    dept_stats = {}

    for dept_code, url in DEPT_URLS:
        print(f"  Scraping {dept_code} from {url.split('//')[1][:50]}...", end=" ", flush=True)
        courses, err = scrape_dept(session, dept_code, url)
        if err:
            print(f"FAILED ({err})")
            failed.append(f"{dept_code}: {err}")
            continue

        new = 0
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
                new += 1

        dept_stats[dept_code] = new
        print(f"{new} courses")
        time.sleep(0.3)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(f[:60] for f in failed)}")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal", "cross_listed", "deduplicated",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_courses)

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "total_courses": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2) if total else 0,
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2) if total else 0,
        "climate_narrow_count": cn,
        "climate_narrow_pct": round(100 * cn / total, 2) if total else 0,
        "climate_broad_count": cb,
        "climate_broad_pct": round(100 * cb / total, 2) if total else 0,
        "by_area": area_counts,
        "failed_depts": failed,
        "dept_stats": dept_stats,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote {OUTPUT_CSV}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | "
          f"Canon: {canon} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn} ({summary['climate_narrow_pct']}%) | "
          f"Climate broad: {cb} ({summary['climate_broad_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        pct = round(100 * cnt / total) if total else 0
        print(f"  {area}: {cnt} ({pct}%)")


if __name__ == "__main__":
    main()
