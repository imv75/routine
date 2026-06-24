#!/usr/bin/env python3
"""
Northeastern University course catalog scraper.
URL: catalog.northeastern.edu/course-descriptions/{dept}/
HTML: div.courseblock > p.courseblocktitle > strong "DEPT NUM. Title. (Credits)"
      + p.cb_desc (description)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "northeastern"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.northeastern.edu"
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

STEM = {"aly", "bioc", "bioe", "binf", "biol", "bio", "biot", "chem", "ce", "chm",
        "cive", "cs", "csy", "ds", "eece", "ece", "ensc", "envr", "env",
        "exsc", "gen", "geo", "geol", "hinf", "ie", "ise", "math", "me",
        "mie", "mse", "msci", "neur", "nusc", "phth", "phys", "phc",
        "psyc", "psy", "pub", "rsch", "sci", "stat"}
HUMANITIES = {"afrs", "afcs", "amsl", "anth", "ant", "arab", "art", "artg",
              "artf", "arte", "arth", "artd", "arts", "asns", "chin",
              "clas", "cltr", "comu", "cult", "engl", "engw",
              "fren", "germ", "grek", "hist", "hst", "ital", "japn",
              "lang", "latn", "ling", "litr", "mhis", "musc",
              "phil", "port", "relg", "russ", "span", "thtr", "wgss"}
SOCIAL = {"afcs", "anth", "comm", "crim", "econ", "educ",
          "geog", "gwst", "intl", "jour", "pols", "ppua",
          "soc", "socl", "soci", "sowk", "urbs"}
MEDICAL = {"ahth", "audi", "bioc", "clin", "den", "dent",
           "exsc", "hinf", "nphm", "nurs", "nutr", "ot",
           "pa", "phmd", "phth", "pmr", "pt", "pub",
           "surg", "slhs", "spth"}
PROFESSIONAL = {"acct", "acc", "avm", "arch", "army", "aace",
                "bnsc", "busn", "bus", "cj", "cjus",
                "comm", "cmn", "cosm", "dsgn",
                "entr", "fnce", "fin", "gscm", "hrm",
                "inno", "intb", "jrmc", "law", "lgls",
                "mgmt", "mgt", "mktg", "mkt", "mba",
                "mgsc", "mism", "mme", "nlp", "nres",
                "opim", "orgb", "pol", "ppa",
                "pscj", "real", "schm", "scm", "scml",
                "smgt", "sprt", "strt", "tax", "techp", "usaf"}


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
        return "graduate" if n >= 5000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_block(block):
    title_p = block.find("p", class_="courseblocktitle")
    if not title_p:
        return None
    strong = title_p.find("strong")
    if not strong:
        return None
    title_text = strong.get_text(" ", strip=True)
    # Format: "ENGL 1000. English at Northeastern. (1 Hour)"
    # or "CS 5001. Intensive Foundations of Computer Science. (4 Hours)"
    m = re.match(r"([A-Z][A-Z0-9]*)\s+([\d\w]+)\.\s+(.+?)(?:\.\s*\(|$)", title_text)
    if not m:
        # Try alternate: dept and num may be separated differently
        m2 = re.match(r"([A-Z][A-Z0-9]*)\s+([\d]+[\w]*)", title_text)
        if not m2:
            return None
        dept = m2.group(1)
        num = m2.group(2)
        title = title_text[m2.end():].lstrip(".").strip()
    else:
        dept = m.group(1)
        num = m.group(2)
        title = m.group(3).strip()

    desc_p = block.find("p", class_="cb_desc") or block.find("p", class_="courseblockdesc")
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


def get_depts(session):
    url = f"{BASE_URL}/course-descriptions/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select("a[href*='/course-descriptions/']")
        depts = []
        for l in links:
            href = l.get("href", "")
            m = re.search(r"/course-descriptions/([^/]+)/", href)
            if m:
                depts.append(m.group(1))
        return list(dict.fromkeys(depts))
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Northeastern University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    depts = get_depts(session)
    print(f"Scraping {len(depts)} departments...")

    for dept in depts:
        url = f"{BASE_URL}/course-descriptions/{dept}/"
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                failed.append(dept)
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            blocks = soup.find_all("div", class_="courseblock")
            new = 0
            for b in blocks:
                c = parse_block(b)
                if c:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
            if new:
                print(f"  {dept.upper()}: {new} courses")
        except Exception as e:
            print(f"  ERROR {dept}: {e}")
            failed.append(dept)
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
