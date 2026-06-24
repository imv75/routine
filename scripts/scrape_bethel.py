#!/usr/bin/env python3
"""
Bethel University (Indiana) course catalog scraper.
URL: betheluniversity.smartcatalogiq.com/en/2026-2027/catalog/{undergraduate|graduate}-courses/{dept-slug}/{level}/{course}
HTML: div#main > h1 (span=code + title) + div.desc > p (desc)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSITY = "bethel"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://betheluniversity.smartcatalogiq.com"
CATALOG_PATH = "/en/2026-2027/catalog"
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

STEM = {"biol", "chem", "csc", "cysc", "envs", "math", "nurs", "phys", "stat", "capp"}
HUMANITIES = {"art", "asl", "bibl", "chi", "col", "comm", "engl", "fren", "ger", "grek",
              "hist", "hum", "jpn", "lat", "lit", "musi", "phil", "span", "theo", "thea"}
SOCIAL = {"crmj", "econ", "educ", "eced", "eled", "pols", "psy", "soci", "socw", "sw",
          "adc", "bss", "psyc"}
MEDICAL = {"hlth", "kin", "nurs", "nutr", "mhc", "mfct"}
PROFESSIONAL = {"acct", "badm", "fin", "mgmt", "mktg", "mbad"}


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


def classify_level(section):
    return "graduate" if "graduate" in section else "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_dept_paths(session, section):
    url = f"{BASE_URL}{CATALOG_PATH}/{section}"
    r = session.get(url, timeout=25)
    soup = BeautifulSoup(r.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True)]
    pattern = re.compile(rf"^{CATALOG_PATH}/{section}/[a-z][a-z0-9\-]+$")
    return list(dict.fromkeys(h for h in links if pattern.match(h)))


def get_course_urls(session, dept_path):
    url = f"{BASE_URL}{dept_path}/"
    r = session.get(url, timeout=25)
    soup = BeautifulSoup(r.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True)]
    # Individual course: /en/.../courses/{dept}/{level}/{course}
    pattern = re.compile(rf"^{CATALOG_PATH}/[a-z\-]+-courses/[a-z][a-z0-9\-]+/\d+/[a-z][a-z0-9\-]+$")
    return list(dict.fromkeys(h for h in links if pattern.match(h)))


def fetch_course(session, path, section):
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

    m = re.match(r"([A-Z][A-Z0-9]*)\s+(\w+)", code_text)
    if not m:
        return None
    dept = m.group(1)
    num = m.group(2)

    desc_div = main.find("div", class_="desc")
    desc = desc_div.get_text(" ", strip=True) if desc_div else ""

    return dept, num, title, desc, section


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()

    print(f"=== Bethel University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    sections = ["undergraduate-courses", "graduate-courses"]
    all_dept_paths = []
    for section in sections:
        depts = get_dept_paths(session, section)
        all_dept_paths.extend([(dp, section) for dp in depts])
        print(f"  {section}: {len(depts)} depts")
        time.sleep(0.1)

    # Collect all course URLs
    all_course_items = []
    for dp, section in all_dept_paths:
        urls = get_course_urls(session, dp)
        all_course_items.extend([(u, section) for u in urls])
        time.sleep(0.1)

    all_course_items = list({u: s for u, s in all_course_items}.items())
    print(f"Found {len(all_course_items)} course pages to fetch")

    def fetch_one(args):
        path, section = args
        return fetch_course(session, path, section)

    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = {exe.submit(fetch_one, item): item for item in all_course_items}
        for fut in as_completed(futures):
            result = fut.result()
            if not result:
                continue
            dept, num, title, desc, section = result
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
                "level": classify_level(section),
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
