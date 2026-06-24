#!/usr/bin/env python3
"""
University of Notre Dame course catalog scraper.
URL: catalog.nd.edu/undergraduate/courses/{dept}/
HTML: div.courseblock > div.cols > span.detail-code + span.detail-title + div.courseblockextra (desc)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "notredame"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.nd.edu"
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

STEM = {"acms", "bios", "cbmg", "ceg", "cheg", "chem", "cse", "ee", "ece",
        "envs", "esci", "esc", "geo", "geol", "math", "mbg", "me",
        "mi", "nano", "ndseg", "phys", "psyc", "qlth", "sci", "stat"}
HUMANITIES = {"amst", "anth", "arhi", "arst", "asia", "clar", "clas",
              "engl", "fre", "ger", "grek", "hist", "ital", "japn",
              "latn", "li", "ling", "lit", "mear", "mu", "musp",
              "muth", "mupe", "phil", "port", "rels", "russ", "span",
              "stth", "the", "thst", "wgst", "afst", "as"}
SOCIAL = {"anth", "comm", "econ", "educ", "geog", "glbl",
          "ias", "ir", "mdst", "pols", "polth", "ppol",
          "soc", "socl", "socw", "soth", "sph", "urbs"}
MEDICAL = {"bioc", "mbg", "mi", "ndseg", "nu", "nurs",
           "oto", "path", "phar", "phth", "psy", "psyc",
           "pubh", "rad", "surg"}
PROFESSIONAL = {"acct", "actg", "al", "alhn", "alsf", "arch",
                "as", "baal", "balw", "bus", "blaw", "fin",
                "glbl", "hrm", "itm", "law",
                "mgmt", "mba", "mgt", "mktg",
                "nd", "oper", "real", "soc"}


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
        n = int(re.sub(r"[^0-9]", "", str(num))[:5])
        return "graduate" if n >= 60000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_block(block):
    # ND structure: span.detail-code contains dept+num, span.detail-title contains title
    code_span = block.find("span", class_=lambda c: c and "detail-code" in c)
    title_span = block.find("span", class_=lambda c: c and "detail-title" in c)
    if not code_span or not title_span:
        return None

    code_text = code_span.get_text(strip=True)
    parts = code_text.split()
    if len(parts) < 2:
        return None
    dept = parts[0]
    num = parts[1]
    title = title_span.get_text(strip=True)

    # Description: in div.courseblockextra or a p following the header
    desc_div = block.find("div", class_=lambda c: c and "courseblockextra" in c)
    desc = desc_div.get_text(" ", strip=True) if desc_div else ""
    # Also try p
    if not desc:
        desc_p = block.find("p", class_=lambda c: c and "courseblock" in c)
        if desc_p:
            desc = desc_p.get_text(" ", strip=True)

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


def get_depts(session, level="undergraduate"):
    url = f"{BASE_URL}/{level}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select(f"a[href*='/{level}/courses/']")
        depts = []
        for l in links:
            href = l.get("href", "")
            m = re.search(rf"/{level}/courses/([^/]+)/", href)
            if m:
                depts.append(m.group(1))
        return list(dict.fromkeys(depts))
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def scrape_dept(session, dept, level):
    url = f"{BASE_URL}/{level}/courses/{dept}/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        return [c for c in (parse_block(b) for b in soup.find_all("div", class_="courseblock")) if c]
    except Exception as e:
        print(f"  ERROR {dept}: {e}")
        return []


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Notre Dame Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    for level in ["undergraduate", "graduate"]:
        depts = get_depts(session, level)
        print(f"Scraping {len(depts)} {level} departments...")
        for dept in depts:
            courses = scrape_dept(session, dept, level)
            new = 0
            for c in courses:
                key = f"{c['department_code']}_{c['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(c)
                    new += 1
            if not courses:
                failed.append(dept)
            elif new:
                print(f"  {dept.upper()}: {new} courses")
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
