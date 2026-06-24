#!/usr/bin/env python3
"""
Rice University course catalog scraper.
URL: courses.rice.edu/courses/courses/!SWKSCAT.cat?p_action=CATALIST&p_subj={SUBJ}
HTML: div.col-lg-12.course > h3 "DEPT NUM - SHORT TITLE"
      + div > b "Long Title:" + div > b "Description:"
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "rice"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://courses.rice.edu/courses/courses/!SWKSCAT.cat"
OUTPUT_DIR = f"/home/user/routine/data/{UNIVERSITY}"
OUTPUT_CSV = f"{OUTPUT_DIR}/{UNIVERSITY}_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/{UNIVERSITY}_summary.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

SUBJECTS = [
    'AAAS', 'AFSC', 'AMCI', 'ANTH', 'APPL', 'ARAB', 'ARCH', 'ARCR', 'ARTS', 'ASIA',
    'ASTR', 'BIOE', 'BIOS', 'BUSI', 'CEVE', 'CHBE', 'CHEM', 'CHIN', 'CLAS', 'CLIC',
    'CMOR', 'COLL', 'COMM', 'COMP', 'CRWR', 'CSCI', 'DSCI', 'DSRT', 'ECON', 'EDES',
    'EDUC', 'EEPS', 'ELEC', 'EMBA', 'EMSP', 'ENGI', 'ENGL', 'ENST', 'EURO', 'FILM',
    'FOTO', 'FREN', 'FWIS', 'GERM', 'GLBL', 'GLHT', 'GREE', 'HART', 'HEAL', 'HEBR',
    'HIST', 'HONS', 'HUMA', 'HURC', 'INDE', 'INDS', 'ITAL', 'JAPA', 'JWST', 'KINE',
    'KORE', 'LALX', 'LATI', 'LEAD', 'LING', 'LPAP', 'LPCR', 'MACC', 'MATH', 'MDEM',
    'MDHM', 'MDIA', 'MECH', 'MEOS', 'MGMP', 'MGMT', 'MGMW', 'MILI', 'MSNE', 'MUCH',
    'MUSI', 'NAVA', 'NEUR', 'NSCI', 'PHIL', 'PHYS', 'PJHC', 'PLST', 'POLI', 'PORT',
    'PSYC', 'RCEL', 'RELI', 'SMGT', 'SOCI', 'SOPA', 'SOPE', 'SOSC', 'SPAN', 'SSPB',
    'STAT', 'SWGS', 'THEA', 'TIBT', 'UNIV',
]

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

STEM = {"astr", "bioe", "bios", "ceve", "chbe", "chem", "clic", "cmor", "comp",
        "csci", "dsci", "dsrt", "eeps", "elec", "engi", "enst", "kine", "math",
        "mech", "msne", "neur", "nsci", "phys", "psyc", "stat"}
HUMANITIES = {"aaas", "amci", "arab", "arch", "arts", "chin", "clas", "comm",
              "crwr", "engl", "euro", "film", "foto", "fren", "germ", "glht",
              "gree", "hart", "hebr", "hist", "huma", "ital", "japa", "jwst",
              "kore", "lalx", "lati", "ling", "mdia", "meos", "musi", "phil",
              "port", "reli", "span", "swgs", "thea", "tibt"}
SOCIAL = {"aaas", "afsc", "anth", "comm", "econ", "educ", "glbl", "heal",
          "hons", "jwst", "poli", "psyc", "rcel", "soci", "sosc", "swgs"}
MEDICAL = {"bioe", "bios", "heal", "kine", "neur", "nsci"}
PROFESSIONAL = {"busi", "emba", "lead", "lpap", "lpcr", "macc", "mgmp", "mgmt",
                "mgmw", "smgt", "sopa", "sope", "sspb"}


def classify_area(dept):
    d = dept.lower()
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


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:4])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_subject_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_=lambda c: c and "course" in (c if isinstance(c, str) else " ".join(c))):
        h3 = block.find("h3")
        if not h3:
            continue
        header = h3.get_text(strip=True)
        # Format: "COMP 002 - DATA SCIENCE PROJ APPLICATION" or "COMP 140 - COMPUTATIONAL THINKING"
        m = re.match(r"([A-Z]{2,6})\s+(\w+)\s+-\s+(.+)", header)
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        short_title = m.group(3).strip()

        # Extract long title and description from inner divs
        long_title = ""
        desc = ""
        for div in block.find_all("div"):
            b = div.find("b")
            if not b:
                continue
            label = b.get_text(strip=True).rstrip(":")
            value = div.get_text(" ", strip=True)[len(b.get_text(strip=True)):].strip()
            if label == "Long Title":
                long_title = value
            elif label == "Description":
                desc = value

        title = long_title if long_title else short_title
        courses.append((dept, num, title, desc))
    return courses


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Rice University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")
    print(f"Scraping {len(SUBJECTS)} subjects...")

    for subj in SUBJECTS:
        url = f"{BASE_URL}?p_action=CATALIST&p_subj={subj}"
        try:
            r = session.get(url, timeout=30)
            if r.status_code != 200:
                print(f"  SKIP {subj}: HTTP {r.status_code}")
                failed.append(subj)
                continue
            parsed = parse_subject_page(r.text)
            new = 0
            for dept, num, title, desc in parsed:
                key = f"{dept}_{num}"
                if key not in seen:
                    seen.add(key)
                    full_text = f"{title} {desc}"
                    all_courses.append({
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
                    })
                    new += 1
            if new:
                print(f"  {subj}: {new} courses")
        except Exception as e:
            print(f"  ERROR {subj}: {e}")
            failed.append(subj)
        time.sleep(0.3)

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
