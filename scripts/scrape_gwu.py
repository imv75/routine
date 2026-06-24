#!/usr/bin/env python3
"""
George Washington University course catalog scraper.
URL: bulletin.gwu.edu/courses/{dept}/
HTML: div.courseblock > p.courseblocktitle > strong "DEPT 1000. Title. N Credits."
      + p.courseblockdesc
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "gwu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://bulletin.gwu.edu"
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

STEM = {"apsc", "astr", "bioc", "bisc", "bme", "bios", "bst", "cet", "chem", "csci",
        "data", "dats", "dnsc", "ece", "econ", "ee", "envs", "epid", "gach", "gch",
        "geo", "hss", "mae", "math", "mech", "phys", "psyc", "stat", "sysc"}
HUMANITIES = {"aca", "amst", "arab", "arth", "chin", "clas", "cml", "engl", "fren",
              "germ", "grek", "hist", "ital", "jpns", "juda", "kore", "latn", "ling",
              "mist", "most", "musi", "musc", "phil", "port", "rels", "russ", "span",
              "trda", "wgss", "wrlg"}
SOCIAL = {"afst", "ais", "amst", "anth", "comm", "crim", "econ", "educ", "geog",
          "glbl", "honr", "ibus", "intl", "irsd", "lacs", "lhs", "pols", "pppa",
          "psyc", "socy", "ult", "univ", "ursp", "wgss"}
MEDICAL = {"anat", "biom", "bmsc", "canc", "clin", "emh", "gen", "gend", "gnur",
           "hlwl", "hsci", "hss", "medp", "neur", "nurs", "occ", "path", "phrm",
           "pss", "pt", "pubh", "rad", "rehs", "resc"}
PROFESSIONAL = {"acc", "acct", "accy", "badm", "bus", "cfu", "cohm", "dist", "fnce",
                "futr", "hosp", "ibus", "intb", "law", "lawg", "mba", "mgmt",
                "mktg", "nfps", "pmgt", "prpe", "smpa"}


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
        return "graduate" if n >= 6000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_dept_slugs(session):
    url = f"{BASE_URL}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        slugs = []
        for a in soup.find_all("a", href=True):
            m = re.match(r"^/courses/([a-z]+)/$", a["href"])
            if m:
                slugs.append(m.group(1))
        return list(dict.fromkeys(slugs))
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def parse_dept_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        title_p = block.find("p", class_="courseblocktitle")
        if not title_p:
            continue
        strong = title_p.find("strong")
        if not strong:
            continue
        title_text = strong.get_text(" ", strip=True)
        # Format: "ANTH 1000. Dean's Seminar. 3 Credits."
        m = re.match(r"([A-Z][A-Z0-9]*)\s+([\w]+)\.\s*(.+?)(?:\.\s*[\d\-]+\s+Credits?\.?.*|$)", title_text)
        if not m:
            m = re.match(r"([A-Z][A-Z0-9]*)\s+([\w]+)\.\s*(.+)", title_text)
            if not m:
                continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = m.group(3).strip()
        # Clean up trailing credit info from title
        title = re.sub(r"\.\s*[\d\-]+\s+Credits?\.?.*$", "", title).strip()
        title = re.sub(r"\.$", "", title).strip()

        desc_p = block.find("p", class_="courseblockdesc")
        desc = desc_p.get_text(" ", strip=True) if desc_p else ""

        courses.append((dept, num, title, desc))
    return courses


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== George Washington University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    slugs = get_dept_slugs(session)
    print(f"Scraping {len(slugs)} departments...")

    for slug in slugs:
        url = f"{BASE_URL}/courses/{slug}/"
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                failed.append(slug)
                continue
            parsed = parse_dept_page(r.text)
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
                print(f"  {slug.upper()}: {new} courses")
            elif not parsed:
                failed.append(slug)
        except Exception as e:
            print(f"  ERROR {slug}: {e}")
            failed.append(slug)
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
