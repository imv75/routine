#!/usr/bin/env python3
"""
Penn State University course catalog scraper.
URL: bulletins.psu.edu/university-course-descriptions/undergraduate/{dept}/
HTML: div.courseblock > div.courseblocktitle_bubble (dept/num/title) + div.courseblockmeta > div.courseblockdesc
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "psu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://bulletins.psu.edu"
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

STEM = {"acs", "aersp", "agbm", "absm", "aee", "agcom", "agsc", "ag", "ageco", "agro",
        "ansc", "aba", "ae", "aet", "ce", "chem", "cmpen", "cmpsc", "coe", "cse",
        "econ", "ece", "egee", "emp", "eme", "emsc", "engl", "ent", "env", "envs",
        "fdsc", "for", "fs", "geosc", "hort", "ie", "kines", "math", "matse",
        "mbd", "me", "met", "micrb", "nuclear", "nuce", "nurs", "phys", "plsc",
        "psy", "psych", "scied", "slhs", "soda", "soil", "stat", "tox", "vbsc",
        "wildl", "wfs"}
HUMANITIES = {"afam", "afr", "amst", "anth", "aplng", "arab", "arch", "art", "aed", "arth",
              "cams", "chns", "clas", "cmlit", "comm", "engl", "film", "fren",
              "germ", "gk", "hebr", "hist", "hum", "ital", "japan", "jew",
              "kor", "lat", "ling", "ms", "musi", "pbpl", "phil", "port", "rel",
              "russ", "span", "ukr", "wgss", "wmnst", "cams"}
SOCIAL = {"adted", "comm", "crim", "econ", "edps", "educ", "geog", "hhd", "hss",
          "insc", "ist", "la", "llbs", "pa", "pols", "psych", "s-o", "soc",
          "sowk", "sp", "wf"}
MEDICAL = {"biol", "bme", "fshn", "hpa", "kines", "md", "nurs", "phth", "psy", "ptf",
           "rehab", "slhs", "vbsc"}
PROFESSIONAL = {"acctg", "agbm", "air", "army", "ba", "bdge", "blaw", "bus", "cmba",
                "ed", "edldr", "edpsy", "educ", "ent", "fnce", "hrm", "iam",
                "inf", "ins", "ist", "la", "llbs", "mba", "mngt", "mktg",
                "mrm", "nav", "olead", "pa", "psy", "ptf", "turf", "wled"}


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


def get_depts(session, level="undergraduate"):
    url = f"{BASE_URL}/university-course-descriptions/{level}/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select("ul.nav.leveltwo li a")
        depts = []
        for l in links:
            href = l.get("href", "")
            m = re.search(rf"/{level}/([^/]+)/", href)
            if m:
                depts.append(m.group(1))
        return depts
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def parse_block(block):
    bubble = block.find("div", class_="courseblocktitle_bubble")
    if not bubble:
        return None
    code_div = bubble.find("div", class_="course_code")
    if not code_div:
        return None
    spans = code_div.find_all("span")
    if len(spans) < 2:
        return None
    dept = spans[0].get_text(strip=True)
    num = spans[1].get_text(strip=True)
    title_div = bubble.find("div", class_="course_codetitle")
    title = title_div.get_text(strip=True) if title_div else ""

    meta = block.find("div", class_="courseblockmeta")
    desc = ""
    if meta:
        desc_div = meta.find("div", class_="courseblockdesc")
        if desc_div:
            p = desc_div.find("p")
            if p:
                desc = p.get_text(" ", strip=True)

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


def scrape_dept_page(session, dept_slug, level):
    url = f"{BASE_URL}/university-course-descriptions/{level}/{dept_slug}/"
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

    print(f"=== Penn State University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    for level in ["undergraduate", "graduate"]:
        depts = get_depts(session, level)
        print(f"Scraping {len(depts)} {level} departments...")
        for dept in depts:
            courses = scrape_dept_page(session, dept, level)
            new = 0
            for c in courses:
                key = f"{c['department_code']}_{c['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(c)
                    new += 1
            if not courses and dept not in failed:
                failed.append(dept)
            elif new:
                print(f"  {dept.upper()} ({level[:4]}): {new} courses")
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
