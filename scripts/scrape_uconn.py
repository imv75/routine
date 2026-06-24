#!/usr/bin/env python3
"""
University of Connecticut course catalog scraper.
Same HTML structure as UNC: div.courseblock > span.detail-code/title + p.courseblockextra
URL: catalog.uconn.edu/undergraduate/courses/{dept}/
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "uconn"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.uconn.edu"
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

AREA_MAP = {
    "Humanities": ["afri", "amst", "arab", "aris", "art", "arth", "cams", "chin",
                   "clcs", "cogs", "crlp", "dram", "engl", "es", "fren", "germ",
                   "hejs", "hind", "hist", "ilcs", "inds", "iris", "japn", "kore",
                   "ling", "mgrk", "musi", "nais", "pers", "phil", "plsh", "port",
                   "russ", "span", "trst", "viet", "wgss", "afra", "aaas", "llas"],
    "Social Sciences": ["anth", "comm", "econ", "evst", "geog", "gscu", "hrts",
                        "jour", "pols", "psyc", "pubh", "pp", "soci", "sowk"],
    "STEM": ["biol", "bme", "cheg", "chem", "ce", "cse", "dgs", "dsda", "eeb",
             "ece", "engr", "enve", "envs", "erth", "math", "mcb", "me", "mse",
             "marn", "mast", "phys", "pnb", "plsc", "stat"],
    "Medical Sciences": ["ah", "ansc", "diet", "hdfs", "hcmi", "kins", "land",
                         "mcb", "mlsc", "nre", "nurs", "nusc", "osh", "path",
                         "phar", "phrx", "plsc", "pubh", "slhs", "spth"],
    "Professional": ["acct", "are", "ahnr", "airf", "badm", "blaw", "busn", "cewp",
                     "dmd", "diet", "edci", "edlr", "edps", "epsy", "egeo",
                     "fnce", "fina", "gps", "id", "intd", "land", "mem", "ment",
                     "mktg", "misi", "nre", "opim", "saag", "sare", "saas",
                     "sanr", "sapl", "sapb", "univ", "hdfs"],
}

DEPARTMENTS = [
    "acct", "afri", "afra", "are", "sare", "saag", "ahnr", "airf", "ah",
    "asln", "amst", "ansc", "saas", "anth", "arab", "aris", "art", "arth",
    "aaas", "biol", "bme", "busn", "badm", "blaw", "cheg", "chem", "chin",
    "ce", "cams", "cogs", "comm", "clcs", "cse", "cewp", "crlp", "dgs",
    "diet", "dmd", "dram", "erth", "eeb", "econ", "egen", "edci", "edlr",
    "epsy", "ece", "engr", "engl", "enve", "envs", "evst", "es", "fnce",
    "fina", "fren", "gps", "gscu", "germ", "hcmi", "hejs", "hind", "hist",
    "hdfs", "hrts", "inds", "id", "intd", "iris", "ilcs", "japn", "jour",
    "kins", "kore", "land", "llas", "ling", "mem", "ment", "marn", "mast",
    "mktg", "mse", "math", "me", "mlsc", "misi", "mgrk", "mcb", "musi",
    "nais", "nre", "sanr", "nurs", "nusc", "osh", "opim", "path", "sapb",
    "pers", "phar", "phrx", "phil", "phys", "pnb", "plsc", "sapl", "plsh",
    "pols", "port", "psyc", "pubh", "pp", "russ", "sowk", "soci", "span",
    "slhs", "dsda", "stat", "trst", "univ", "viet", "wgss",
]


def classify_area(dept_code):
    dept = dept_code.lower()
    for area, codes in AREA_MAP.items():
        if dept in codes:
            return area
    return "Other"


def classify_level(course_num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[:4])
        return "graduate" if n >= 3000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_block(block):
    code_span = block.find("span", class_="detail-code")
    title_span = block.find("span", class_="detail-title")
    desc_p = block.find("p", class_="courseblockextra") or block.find("p", class_="courseblockdesc")

    if not code_span or not title_span:
        return None

    code_text = code_span.get_text(strip=True).rstrip(".")
    parts = code_text.split()
    if len(parts) < 2:
        return None
    dept = parts[0]
    num = parts[1]

    title = title_span.get_text(strip=True).rstrip(".")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""

    full_text = f"{title} {desc}"
    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept,
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


def scrape_dept(session, dept_slug, level="undergraduate"):
    url = f"{BASE_URL}/{level}/courses/{dept_slug}/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        return [c for c in (parse_block(b) for b in soup.find_all("div", class_="courseblock")) if c]
    except Exception as e:
        print(f"  ERROR {dept_slug}: {e}")
        return []


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Connecticut Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")
    print(f"Scraping {len(DEPARTMENTS)} departments...\n")

    for dept in DEPARTMENTS:
        # Try undergrad first, then grad
        courses = scrape_dept(session, dept, "undergraduate")
        if not courses:
            courses = scrape_dept(session, dept, "graduate")
        if not courses:
            failed.append(dept)
            continue
        new = 0
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
                new += 1
        if new:
            print(f"  {dept.upper()}: {new} courses")
        time.sleep(0.25)

    # Also try graduate catalog for additional courses
    print("\nScraping graduate departments...")
    for dept in DEPARTMENTS:
        courses = scrape_dept(session, dept, "graduate")
        new = 0
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
                new += 1
        if new:
            print(f"  {dept.upper()} (grad): {new} courses")
        time.sleep(0.2)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}")

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
        "university": UNIVERSITY, "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL, "total_courses": total,
        "progressive_count": prog, "progressive_pct": round(100*prog/total, 2) if total else 0,
        "canon_count": canon, "canon_pct": round(100*canon/total, 2) if total else 0,
        "climate_narrow_count": cn, "climate_narrow_pct": round(100*cn/total, 2) if total else 0,
        "climate_broad_count": cb, "climate_broad_pct": round(100*cb/total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {OUTPUT_CSV}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({100*cnt//total if total else 0}%)")


if __name__ == "__main__":
    main()
