#!/usr/bin/env python3
"""
University of Oregon course catalog scraper.
URL pattern: catalog.uoregon.edu/courses/crs-{dept}/
HTML: div.courseblock > p.courseblocktitle (strong: "CODE NUM. Title. N Credits.") + p.courseblockdesc
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://catalog.uoregon.edu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
UNIVERSITY = "uoregon"
OUTPUT_DIR = "/home/user/routine/data/uoregon"
OUTPUT_CSV = f"{OUTPUT_DIR}/uoregon_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/uoregon_summary.json"

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
    "Humanities": ["anth", "art", "artd", "arts", "chin", "clas", "clat", "clgk",
                   "colt", "danc", "engl", "fren", "germ", "glbl", "grk", "hist",
                   "hum", "ital", "japn", "jdst", "kor", "larc", "latn", "ling",
                   "musc", "perf", "phil", "port", "russ", "scan", "span", "swed",
                   "thtr", "writ", "chn", "arb", "hebr", "pers", "turk", "swah",
                   "ptug", "indn", "nati", "ital"],
    "Social Sciences": ["aad", "afst", "amst", "anth", "apl", "blst", "comm",
                        "cis", "econ", "edst", "envs", "erth", "geog", "intl",
                        "j", "las", "lc", "lacs", "mdia", "pols", "psy", "soc",
                        "ws", "wgs"],
    "STEM": ["bi", "bioc", "chem", "cem", "cs", "dsci", "esc", "erth", "expl",
             "hphy", "math", "natl", "neusc", "phys", "scie", "stat", "sts"],
    "Medical Sciences": ["hphy", "phr", "spsy"],
    "Professional": ["actg", "arch", "ba", "coa", "educ", "fin", "fin", "law",
                     "mba", "mktg", "mgmt", "pppm", "rec", "sped", "sp",
                     "lp", "cpe"],
}

# UOregon departments (from /courses/ index, URL pattern crs-{dept})
DEPARTMENTS = [
    "aad", "actg", "afst", "amst", "anth", "apl", "arb", "arch", "art",
    "artd", "arts", "ba", "bi", "bioc", "blst", "chem", "chin", "cis",
    "clas", "clat", "clgk", "clt", "coa", "comm", "colt", "cs", "danc",
    "dsci", "econ", "edst", "educ", "engl", "envs", "erth", "esc", "expl",
    "fin", "fren", "geog", "germ", "glbl", "grk", "hebr", "hist", "hphy",
    "hum", "indn", "intl", "ital", "j", "japn", "jdst", "kor", "larc",
    "latn", "las", "lacs", "law", "lc", "ling", "lp", "math", "mba",
    "mdia", "mgmt", "mktg", "musc", "nati", "natl", "neusc", "perf", "pers",
    "phil", "phys", "phr", "pols", "pppm", "port", "psy", "ptug", "rec",
    "russ", "scan", "scie", "soc", "sp", "sped", "span", "spsy", "stat",
    "sts", "swah", "swed", "thtr", "turk", "wgs", "writ", "ws",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})


def get_departments_from_index():
    """Fetch the actual department list from the catalog index."""
    url = f"{BASE_URL}/courses/"
    try:
        r = SESSION.get(url, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        depts = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.match(r"/courses/crs-([a-z]+)/?$", href)
            if m:
                depts.add(m.group(1))
        return sorted(depts)
    except Exception as e:
        print(f"Could not fetch index: {e}")
        return DEPARTMENTS


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
    return any(kw in t for kw in keywords)


def parse_course_block(block):
    # UOregon: p.courseblocktitle with <strong>CODE NUM. Title. N Credits.</strong>
    # then p.courseblockdesc
    title_p = block.find("p", class_="courseblocktitle")
    desc_p = block.find("p", class_="courseblockdesc")

    if not title_p:
        return None

    title_text = title_p.get_text(" ", strip=True)
    # Format: "DEPT NUM. Course Title. N Credits." or "DEPT NUM Course Title N Credits"
    m = re.match(r"([A-Z]+)\s+([\w]+)[.\s]+(.+?)\.?\s+\d+\s+Credits?\.?", title_text, re.IGNORECASE)
    if not m:
        m = re.match(r"([A-Z]+)\s+([\w]+)[.\s]+(.+)", title_text)
    if not m:
        return None

    dept = m.group(1).strip()
    num = m.group(2).strip()
    title = m.group(3).strip()
    title = re.sub(r"\.\s*\d+\s*Credits?\.?$", "", title).strip()

    desc = desc_p.get_text(" ", strip=True) if desc_p else ""
    # Remove "Additional Information:" sections from desc
    desc = re.split(r"Additional Information:", desc)[0].strip()

    full_text = f"{title} {desc}"

    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept.lower()),
        "level": classify_level(num),
        "progressive_signal": check_keywords(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_keywords(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_keywords(full_text, CLIMATE_NARROW_KEYWORDS),
        "climate_broad_signal": check_keywords(full_text, CLIMATE_BROAD_KEYWORDS),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_dept(dept_slug):
    url = f"{BASE_URL}/courses/crs-{dept_slug}/"
    try:
        r = SESSION.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for b in blocks:
            c = parse_course_block(b)
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

    print("=== University of Oregon Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}\n")

    depts = get_departments_from_index()
    print(f"Found {len(depts)} departments from index")

    for dept in depts:
        courses = scrape_dept(dept)
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

    print(f"\nTotal unique courses: {len(all_courses)}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}")

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

    prog_count = sum(1 for c in all_courses if c["progressive_signal"])
    canon_count = sum(1 for c in all_courses if c["western_canon_signal"])
    cn_count = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb_count = sum(1 for c in all_courses if c["climate_broad_signal"])
    total = len(all_courses)
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": UNIVERSITY, "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL, "total_courses": total,
        "progressive_count": prog_count,
        "progressive_pct": round(100 * prog_count / total, 2) if total else 0,
        "canon_count": canon_count,
        "canon_pct": round(100 * canon_count / total, 2) if total else 0,
        "climate_narrow_count": cn_count,
        "climate_narrow_pct": round(100 * cn_count / total, 2) if total else 0,
        "climate_broad_count": cb_count,
        "climate_broad_pct": round(100 * cb_count / total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {OUTPUT_CSV}\nWrote {SUMMARY_FILE}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog_count} ({summary['progressive_pct']}%) | Canon: {canon_count} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({100*cnt//total if total else 0}%)")


if __name__ == "__main__":
    main()
