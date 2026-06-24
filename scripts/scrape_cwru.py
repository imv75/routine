#!/usr/bin/env python3
"""
Case Western Reserve University course catalog scraper.
URL: https://bulletin.case.edu/course-descriptions/{dept_code}/
Format: div.courseblock > p.courseblocktitle strong: 'DEPT NUM.  Title.  N Units.'
        p.courseblockdesc: description text
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSITY = "cwru"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://bulletin.case.edu"
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
CLIMATE_NARROW = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]
CLIMATE_BROAD = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]

AREA_MAP = {
    "Humanities": [
        "engl", "arth", "arts", "danc", "thtr", "wlit", "humn", "htec",
        "muhi", "muli", "muth", "muar", "mucp", "mude", "mued", "muen",
        "mugn", "mupd", "murp", "musp", "muap",
        "chin", "arab", "frch", "grmn", "ital", "japn", "kore", "latn",
        "grek", "hbrw", "rusn", "span", "port", "akkd", "hier",
        "hist", "hpsc", "phil", "rlgn", "ling", "clsc",
        "asia", "afst", "jwst", "intl", "sjus", "wgst",
        "writ", "aiae",
    ],
    "Social Sciences": [
        "anth", "econ", "posc", "pscl", "soci", "cosi", "gero",
        "chst", "eths", "cogs", "comm", "geog",
    ],
    "STEM": [
        "astr", "biol", "bioc", "chem", "csds", "dsci", "eeps",
        "eciv", "eche", "ebme", "ecse", "emae", "emac", "emse",
        "engr", "estd", "gene", "math", "phys", "phol", "stat",
        "sybb", "ibis",
    ],
    "Medical Sciences": [
        "anat", "anes", "beth", "bstp", "clby", "cmed", "crsp",
        "dent", "dphc", "dndo", "dorl", "dped", "dper", "drth",
        "dspr", "dsre", "efda", "hewb", "hwdp", "hsmc", "ibms",
        "ihsc", "inth", "iqbp", "mahe", "mbio", "mmed", "mphp",
        "mstp", "mvir", "neur", "ntrn", "nund", "nuan", "nued",
        "nunp", "numn", "nurs", "omfs", "past", "path", "phrm",
        "pqhs", "rehe", "rema", "rgme", "comp",
    ],
    "Professional": [
        "acct", "bafi", "blaw", "btec", "buai", "dbap", "desn",
        "edmp", "emba", "entp", "fnce", "ftec", "ldrs", "leoc",
        "leap", "mgte", "mgmt", "mids", "mkmr", "mpod", "opmt",
        "opre", "orbh", "plcy", "sass", "scmg", "sowk",
        "laws", "lfin", "lsab", "mbac", "mbap",
        "educ", "veal",
    ],
}

# All department codes from bulletin.case.edu/course-descriptions/
DEPARTMENTS = [
    "aiae", "aiqs", "acct", "afst", "akkd", "anat", "anee", "anes", "anth",
    "dsci", "muap", "arab", "arth", "arts", "asia", "astr", "bafi", "bioc",
    "beth", "biol", "ebme", "bstp", "buai", "blaw", "btec", "cncr", "clby",
    "eche", "chem", "chst", "chin", "eciv", "clsc", "cmed", "crsp", "cogs",
    "cosi", "csds", "coop", "danc", "dphc", "dent", "desn", "dsre", "dspr",
    "dbap", "nund", "eeps", "econ", "educ", "edab", "hier", "ecse", "dndo",
    "engr", "engl", "entp", "estd", "eths", "exam", "edmp", "emba", "efda",
    "fnce", "ftec", "frch", "gene", "grmn", "gero", "rsch", "grek", "hewb",
    "hwdp", "hsmc", "hbrw", "hpsc", "hsty", "humn", "htec", "mids", "inqu",
    "ibis", "ibms", "ihsc", "exch", "inth", "intl", "iqbp", "ital", "japn",
    "jwst", "kore", "latn", "laws", "lfin", "lsab", "ldrs", "leoc", "leap",
    "ling", "emac", "mahe", "mgte", "mgmt", "plcy", "mkmr", "numn", "emse",
    "math", "mbac", "mbap", "emae", "mstp", "mbio", "mmed", "mvir", "muhi",
    "muli", "muth", "muar", "mucp", "mude", "mued", "muen", "mugn", "mupd",
    "murp", "musp", "neur", "nunp", "nurs", "nuan", "nued", "ntrn", "opmt",
    "opre", "omfs", "dorl", "orbh", "orig", "drth", "path", "comp", "dped",
    "dper", "phrm", "phil", "phed", "past", "phys", "phol", "posc", "pqhs",
    "port", "mpod", "epom", "prac", "pscl", "mphp", "rgme", "rlgn", "rema",
    "rehe", "rusn", "ucap", "sass", "mgrd", "smab", "srab", "syps", "sjus",
    "soci", "span", "stat", "scmg", "sybb", "thtr", "univ", "veal", "wash",
    "wgst", "wlit", "writ", "hsty",
]
# De-duplicate
DEPARTMENTS = list(dict.fromkeys(DEPARTMENTS))


def classify_area(dept_code):
    d = dept_code.lower()
    for area, codes in AREA_MAP.items():
        if d in codes:
            return area
    return "Other"


def classify_level(course_num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[:4])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_title_strong(strong_text):
    """Parse 'DEPT NUM.  Title.  N Units.' format (double-space separated)."""
    text = strong_text.strip().rstrip(".")
    # Split on period + 2+ spaces
    parts = re.split(r"\.\s{2,}", text, maxsplit=2)
    if len(parts) < 2:
        # Fallback: split on period + single space
        parts = re.split(r"\.\s+", text, maxsplit=2)
    if len(parts) < 2:
        return None, None, None
    code_part = parts[0].strip()
    title = parts[1].strip().rstrip(".") if len(parts) > 1 else ""
    code_tokens = code_part.split()
    if len(code_tokens) < 2:
        return None, None, None
    dept = code_tokens[0]
    num = code_tokens[1]
    return dept, num, title


def parse_block(block):
    title_p = block.find("p", class_="courseblocktitle")
    if not title_p:
        return None
    strong = title_p.find("strong")
    if not strong:
        return None
    strong_text = strong.get_text(" ", strip=True)
    dept, num, title = parse_title_strong(strong_text)
    if not dept or not num:
        return None

    desc_p = block.find("p", class_="courseblockdesc")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""

    full_text = f"{title} {desc}"
    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept.upper(),
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept),
        "level": classify_level(num),
        "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
        "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_dept(session, dept_code):
    url = f"{BASE_URL}/course-descriptions/{dept_code}/"
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return dept_code, []
        soup = BeautifulSoup(r.text, "html.parser")
        courses = [c for c in (parse_block(b) for b in soup.find_all("div", class_="courseblock")) if c]
        return dept_code, courses
    except Exception as e:
        print(f"  ERROR {dept_code}: {e}")
        return dept_code, []


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research)"})

    all_courses = []
    seen = set()
    failed = []

    print(f"=== Case Western Reserve University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")
    print(f"Departments to scrape: {len(DEPARTMENTS)}\n")

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(scrape_dept, session, d): d for d in DEPARTMENTS}
        for fut in as_completed(futures):
            dept_code, courses = fut.result()
            if not courses:
                failed.append(dept_code)
                continue
            new = 0
            for c in courses:
                key = f"{c['department_code']}_{c['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(c)
                    new += 1
            if new:
                print(f"  {dept_code.upper()}: {new} unique courses")

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed/empty ({len(failed)}): {', '.join(sorted(failed)[:30])}")

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
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote {OUTPUT_CSV}")
    print(f"=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")


if __name__ == "__main__":
    main()
