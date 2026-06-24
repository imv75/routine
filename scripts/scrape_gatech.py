#!/usr/bin/env python3
"""
Georgia Tech course catalog scraper for Marinovic (2026) curriculum dataset.
Scrapes catalog.gatech.edu for undergraduate and graduate courses.
HTML: div.courseblock > p.courseblocktitle + p.courseblockdesc
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://catalog.gatech.edu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
UNIVERSITY = "gatech"
OUTPUT_DIR = "/home/user/routine/data/gatech"
OUTPUT_CSV = f"{OUTPUT_DIR}/gatech_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/gatech_summary.json"

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
    "Humanities": ["engl", "hist", "hts", "phil", "lmc", "ling", "musi", "fren", "grmn", "span",
                   "russ", "chin", "japn", "kor", "arbc", "latn", "hebw", "hin", "pers", "swah",
                   "ml", "hum", "gmc"],
    "Social Sciences": ["econ", "pol", "psyc", "soc", "inta", "pubp", "ss"],
    "STEM": ["ae", "apph", "bios", "biol", "bmed", "bmej", "bmem", "chbe", "chem", "cee",
             "cse", "cs", "eas", "ece", "ecep", "isye", "math", "me", "mse", "mp", "nre",
             "phys", "ptfe", "sci", "neur", "cx"],
    "Professional": ["acct", "arch", "aect", "bc", "cp", "id", "mgt", "mot", "mldr",
                     "il", "imba", "hs", "pubp", "ase"],
    "Other": ["as", "apph", "cetl", "coe", "cll", "cos", "coop", "ucga", "fs", "free",
              "gt", "gtl", "ls", "msl", "ns", "sls", "pubj", "intn", "iac"],
}

UNDERGRAD_DEPTS = [
    "acct", "ae", "as", "apph", "arbc", "arch", "aect", "bios", "biol", "bmed",
    "bc", "cetl", "chbe", "chem", "chin", "cp", "cee", "coe", "cll", "cos",
    "cx", "cs", "coop", "ucga", "eas", "econ", "ece", "engl", "fs", "free",
    "fren", "gt", "gtl", "grmn", "hs", "hebw", "hin", "hist", "hts", "hum",
    "id", "isye", "inta", "intn", "iac", "japn", "kor", "latn", "ls", "ling",
    "lmc", "mgt", "mse", "math", "me", "mp", "msl", "ml", "musi", "ns",
    "neur", "nre", "pers", "phil", "phys", "pol", "psyc", "pubp", "russ",
    "sci", "sls", "ss", "soc", "span", "swah",
]

GRAD_DEPTS = [
    "ae", "apph", "ase", "arch", "biol", "bmej", "bmed", "bmem", "bc", "cetl",
    "chbe", "chem", "chin", "cp", "cee", "cll", "cse", "cs", "coop", "ucga",
    "eas", "econ", "ecep", "ece", "fs", "free", "fren", "gtl", "grmn", "gmc",
    "hs", "hts", "id", "isye", "inta", "il", "imba", "japn", "kor", "ling",
    "lmc", "mgt", "mot", "mldr", "mse", "math", "me", "mp", "ml", "musi",
    "nre", "phil", "phys", "ptfe", "psyc", "pubj", "pubp", "russ", "span",
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
        num = int(re.sub(r"[^0-9]", "", course_num)[:4])
        return "graduate" if num >= 5000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    for kw in keywords:
        if kw in t:
            return True
    return False


def parse_course_block(block, dept_code, level_prefix):
    title_tag = block.find("p", class_="courseblocktitle")
    desc_tag = block.find("p", class_="courseblockdesc")
    if not title_tag:
        return None
    title_text = title_tag.get_text(" ", strip=True)
    # Format: "DEPT XXXX. Title. N Credit Hours."
    m = re.match(r"([A-Z]+)\s+([\w]+)\.\s+(.+?)\.\s+\d+", title_text)
    if not m:
        # Try alternate: "DEPT XXXX. Title."
        m = re.match(r"([A-Z]+)\s+([\w]+)\.\s+(.+)", title_text)
    if not m:
        return None
    dept = m.group(1).strip()
    num = m.group(2).strip()
    title = m.group(3).strip()
    # Remove trailing credit info from title
    title = re.sub(r"\.\s*\d+[\-\d]* Credit Hours?\.?$", "", title).strip()
    desc = desc_tag.get_text(" ", strip=True) if desc_tag else ""
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


def scrape_dept(url_path, level_label):
    url = BASE_URL + url_path
    try:
        r = SESSION.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        dept_code = url_path.rstrip("/").split("/")[-1].upper()
        for b in blocks:
            c = parse_course_block(b, dept_code, level_label)
            if c:
                courses.append(c)
        return courses
    except Exception as e:
        print(f"  ERROR {url_path}: {e}")
        return []


def main():
    all_courses = []
    seen = set()

    print("=== Georgia Tech Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}\n")

    # Undergraduate departments
    print(f"Scraping {len(UNDERGRAD_DEPTS)} undergraduate departments...")
    for dept in UNDERGRAD_DEPTS:
        path = f"/courses-undergrad/{dept}/"
        courses = scrape_dept(path, "undergrad")
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
        if courses:
            print(f"  {dept.upper()}: {len(courses)} courses")
        time.sleep(0.3)

    # Graduate departments
    print(f"\nScraping {len(GRAD_DEPTS)} graduate departments...")
    for dept in GRAD_DEPTS:
        path = f"/courses-grad/{dept}/"
        courses = scrape_dept(path, "grad")
        new = 0
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
                new += 1
        if new:
            print(f"  {dept.upper()} (grad): {new} new courses")
        time.sleep(0.3)

    print(f"\nTotal unique courses: {len(all_courses)}")

    # Write CSV
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

    # Summary statistics
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
        print(f"  {area}: {cnt} ({100*cnt//total}%)")


if __name__ == "__main__":
    main()
