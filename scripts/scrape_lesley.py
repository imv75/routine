#!/usr/bin/env python3
"""
Lesley University course catalog scraper.
URL: lesley.smartcatalogiq.com/en/2025-2026-ac-catalog_student-handbook/2025-2026-academic-catalog/courses/
HTML: div#main > h1 (span=code + title) + div.desc (desc)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSITY = "lesley"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2025-2026"
BASE_URL = "https://lesley.smartcatalogiq.com"
CATALOG_PATH = "/en/2025-2026-ac-catalog_student-handbook/2025-2026-academic-catalog"
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

STEM = {"biol", "chem", "csci", "math", "phys", "stat", "envs", "nurs", "data", "sci"}
HUMANITIES = {"art", "comm", "engl", "fren", "ger", "hist", "hum", "musi", "phil",
              "reli", "span", "thea", "wgst", "lang", "cre", "wr", "lit"}
SOCIAL = {"anth", "cjus", "econ", "educ", "pols", "psyc", "soci", "socw", "cou", "psy"}
MEDICAL = {"hlth", "kine", "nurs", "nutr", "athl", "otr"}
PROFESSIONAL = {"acct", "buad", "fin", "mgmt", "mktg", "bus", "mba"}


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


def classify_level(num_str):
    try:
        n = int(re.sub(r"[^0-9]", "", num_str)[:4])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_dept_paths(session):
    url = f"{BASE_URL}{CATALOG_PATH}/courses"
    r = session.get(url, timeout=25)
    soup = BeautifulSoup(r.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True)]
    pattern = re.compile(rf"^{re.escape(CATALOG_PATH)}/courses/[a-z][a-z0-9\-]+$")
    return list(dict.fromkeys(h for h in links if pattern.match(h)))


def get_course_urls(session, dept_path):
    url = f"{BASE_URL}{dept_path}/"
    r = session.get(url, timeout=25)
    soup = BeautifulSoup(r.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True)]
    pattern = re.compile(rf"^{re.escape(CATALOG_PATH)}/courses/[a-z][a-z0-9\-]+/\d+/[a-z][a-z0-9\-]+$")
    return list(dict.fromkeys(h for h in links if pattern.match(h)))


def fetch_course(session, path):
    url = f"{BASE_URL}{path}"
    r = session.get(url, timeout=25)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.find("div", id="main")
    if not main:
        return None
    h1 = main.find("h1")
    if not h1:
        return None
    code_span = h1.find("span")
    code_text = code_span.get_text(strip=True).replace("\xa0", " ") if code_span else ""
    title = h1.get_text(" ", strip=True).replace(code_text, "").strip()
    m = re.match(r"([A-Z][A-Z0-9]*)[\s-]+(\w+)", code_text)
    if not m:
        return None
    dept = m.group(1)
    num = m.group(2)
    desc_div = main.find("div", class_="desc")
    desc = desc_div.get_text(" ", strip=True) if desc_div else ""
    return dept, num, title, desc


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()

    print(f"=== Lesley University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    dept_paths = get_dept_paths(session)
    print(f"Found {len(dept_paths)} departments")

    all_course_urls = []
    for dp in dept_paths:
        urls = get_course_urls(session, dp)
        all_course_urls.extend(urls)
        time.sleep(0.1)

    all_course_urls = list(dict.fromkeys(all_course_urls))
    print(f"Found {len(all_course_urls)} course pages to fetch")

    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = {exe.submit(fetch_course, session, p): p for p in all_course_urls}
        for fut in as_completed(futures):
            result = fut.result()
            if not result:
                continue
            dept, num, title, desc = result
            key = f"{dept}_{num}"
            if key in seen:
                continue
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

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")

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
        "by_area": area_counts, "failed_depts": [],
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
