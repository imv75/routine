#!/usr/bin/env python3
"""
UNC Chapel Hill course catalog scraper for Marinovic (2026) curriculum dataset.
Scrapes catalog.unc.edu/courses/{dept}/ for all departments.
HTML: div.courseblock with spans for code, title, hours; p.courseblockextra for desc.
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://catalog.unc.edu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
UNIVERSITY = "unc"
OUTPUT_DIR = "/home/user/routine/data/unc"
OUTPUT_CSV = f"{OUTPUT_DIR}/unc_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/unc_summary.json"

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
    "diaspora", "reparations", "microaggression", "implicit bias",
    "systemic racism",
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
    "canterbury tales", "leviathan", "federalist",
    "classics", "classical",
]

CLIMATE_NARROW_KEYWORDS = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]

CLIMATE_BROAD_KEYWORDS = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]

AREA_MAP = {
    "Humanities": ["engl", "hist", "phil", "ling", "cmpl", "roml", "fren", "span",
                   "germ", "gsll", "ital", "port", "russ", "latn", "grek", "clas",
                   "clar", "musc", "arts", "dram", "folk", "reli", "jwst", "arab",
                   "chin", "japn", "kor", "hebr", "hnur", "prsn", "turk", "slav",
                   "ydsh", "czch", "hung", "macd", "plsh", "ukrn", "viet", "dtch",
                   "bcs", "cata", "lgla", "wolo", "yoru", "swah"],
    "Social Sciences": ["econ", "poli", "soci", "psyc", "anth", "geog", "comm",
                        "mejo", "glbl", "amst", "aaad", "asia", "ltam", "euro",
                        "pwad", "mngt", "idst", "data"],
    "STEM": ["biol", "chem", "phys", "math", "comp", "astr", "bioc", "emes",
             "geol", "masc", "mcro", "nbio", "nsci", "neur", "bcb", "gnet",
             "envr", "enec", "bios", "stor", "appl", "bmme", "mtsc", "stat"],
    "Medical Sciences": ["nurs", "nutr", "phco", "phrs", "phcy", "path", "epid",
                         "hbeh", "hpm", "mhch", "cbmc", "cbph", "pasc", "ocsc",
                         "occt", "radi", "clsc", "sphs", "hmsc", "exss", "chip",
                         "toxc", "dpmp", "dpop", "dpet", "mphr", "sphg", "pace",
                         "ndss", "expr", "deng", "dhyg", "dhed", "endo", "oper",
                         "ocbm", "orpa", "orad", "orth", "path", "pedo", "peri",
                         "pros", "bbsp", "crmh"],
    "Professional": ["busi", "law", "educ", "plan", "sowo", "puba", "plcy",
                     "pubh", "govt", "inls", "recr", "lfit", "aero", "army",
                     "navs", "grad", "spcl", "ures", "icmu"],
}

# All departments from catalog.unc.edu/courses/
DEPARTMENTS = [
    "aero", "aaad", "amst", "anth", "appl", "arab", "arch", "army", "arth",
    "asia", "astr", "bioc", "bcb", "bbsp", "biol", "bmme", "bios", "bcs",
    "busi", "chip", "cata", "cbph", "cbmc", "chem", "chwa", "chin", "plan",
    "clar", "clas", "clsc", "crmh", "comm", "cmpl", "comp", "euro", "czch",
    "data", "deng", "dhyg", "dhed", "dram", "dtch", "emes", "econ", "educ",
    "endo", "engl", "enec", "envr", "epid", "exss", "edmx", "spcl", "expr",
    "dpet", "folk", "fren", "gnet", "geog", "geol", "germ", "gsll", "glbl",
    "govt", "grad", "grek", "hbeh", "hpm", "hebr", "hnur", "hist", "hmsc",
    "hung", "inls", "idst", "icmu", "ital", "japn", "jwst", "swah", "kor",
    "latn", "law", "ltam", "lfit", "lgla", "ling", "macd", "mngt", "masc",
    "hpm", "math", "mejo", "mcro", "musc", "navs", "ndss", "nbio", "nsci",
    "nurs", "nutr", "ocsc", "occt", "oper", "ocbm", "orpa", "orad", "orth",
    "path", "pwad", "pedo", "peri", "prsn", "phrs", "dpmp", "phco", "phcy",
    "dpop", "phil", "phya", "pasc", "phys", "poli", "port", "pace", "pros",
    "psyc", "puba", "pubh", "plcy", "radi", "recr", "reli", "roml", "russ",
    "scll", "sphg", "slav", "sowo", "soci", "span", "sphs", "stor", "arts",
    "toxc", "turk", "ukrn", "ures", "viet", "wgst", "wolo", "ydsh", "yoru",
    "mtsc", "mhch", "mphr",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})


def classify_area(dept_code):
    dept = dept_code.lower()
    for area, codes in AREA_MAP.items():
        if dept in codes:
            return area
    return "Other"


def classify_level(course_num):
    try:
        num = int(re.sub(r"[^0-9]", "", str(course_num))[:4])
        return "graduate" if num >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    for kw in keywords:
        if kw in t:
            return True
    return False


def parse_course_block(block, dept_code):
    # UNC structure: span.detail-code, span.detail-title, p.courseblockextra
    code_span = block.find("span", class_="detail-code")
    title_span = block.find("span", class_="detail-title")
    desc_p = block.find("p", class_="courseblockextra")

    if not code_span or not title_span:
        return None

    code_text = code_span.get_text(strip=True).rstrip(".")
    # code_text like "ENGL 50" or "COMP 110"
    parts = code_text.split()
    if len(parts) < 2:
        return None
    dept = parts[0]
    num = parts[1]

    title = title_span.get_text(strip=True).rstrip(".")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""

    full_text = f"{title} {desc}"
    level = classify_level(num)
    area = classify_area(dept)
    prog = check_keywords(full_text, PROGRESSIVE_KEYWORDS)
    canon = check_keywords(full_text, WESTERN_CANON_KEYWORDS)
    clim_narrow = check_keywords(full_text, CLIMATE_NARROW_KEYWORDS)
    clim_broad = check_keywords(full_text, CLIMATE_BROAD_KEYWORDS)

    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": area,
        "level": level,
        "progressive_signal": prog,
        "western_canon_signal": canon,
        "climate_narrow_signal": clim_narrow,
        "climate_broad_signal": clim_broad,
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_dept(dept_slug):
    url = f"{BASE_URL}/courses/{dept_slug}/"
    try:
        r = SESSION.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for b in blocks:
            c = parse_course_block(b, dept_slug.upper())
            if c:
                courses.append(c)
        return courses
    except Exception as e:
        print(f"  ERROR {dept_slug}: {e}")
        return []


def main():
    all_courses = []
    seen = set()
    failed = []

    print("=== UNC Chapel Hill Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}\n")

    depts = list(dict.fromkeys(DEPARTMENTS))  # deduplicate
    print(f"Scraping {len(depts)} departments...")

    for dept in depts:
        courses = scrape_dept(dept)
        if not courses:
            failed.append(dept)
            continue
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
        print(f"  {dept.upper()}: {len(courses)} courses")
        time.sleep(0.3)

    print(f"\nTotal unique courses: {len(all_courses)}")
    if failed:
        print(f"Failed departments ({len(failed)}): {', '.join(failed)}")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)
    print(f"Wrote {OUTPUT_CSV}")

    prog_count = sum(1 for c in all_courses if c["progressive_signal"])
    canon_count = sum(1 for c in all_courses if c["western_canon_signal"])
    cn_count = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb_count = sum(1 for c in all_courses if c["climate_broad_signal"])
    total = len(all_courses)

    area_counts = {}
    for c in all_courses:
        area = c["broad_area"]
        area_counts[area] = area_counts.get(area, 0) + 1

    summary = {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "total_courses": total,
        "progressive_count": prog_count,
        "progressive_pct": round(100 * prog_count / total, 2) if total else 0,
        "canon_count": canon_count,
        "canon_pct": round(100 * canon_count / total, 2) if total else 0,
        "climate_narrow_count": cn_count,
        "climate_narrow_pct": round(100 * cn_count / total, 2) if total else 0,
        "climate_broad_count": cb_count,
        "climate_broad_pct": round(100 * cb_count / total, 2) if total else 0,
        "by_area": area_counts,
        "failed_depts": failed,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {SUMMARY_FILE}")

    print("\n=== Summary ===")
    print(f"Total courses: {total}")
    print(f"Progressive: {prog_count} ({summary['progressive_pct']}%)")
    print(f"Canon: {canon_count} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn_count} ({summary['climate_narrow_pct']}%)")
    print(f"Climate broad: {cb_count} ({summary['climate_broad_pct']}%)")
    print("\nBy area:")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        pct = round(100 * cnt / total) if total else 0
        print(f"  {area}: {cnt} ({pct}%)")


if __name__ == "__main__":
    main()
