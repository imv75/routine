#!/usr/bin/env python3
"""
University of Nebraska-Lincoln course catalog scraper.
URL: catalog.unl.edu/undergraduate/courses/{dept}/
HTML: div.courseblock > span.cb_subject_code + span.cb_course_number + span.title + div.cb_description
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "unl"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.unl.edu"
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

STEM = {"astr", "bioc", "bios", "bsen", "chme", "chem", "cive", "cone", "csce",
         "ecen", "engr", "ensc", "enve", "fdst", "geog", "geol", "geos", "gras",
         "life", "math", "matl", "mbio", "mech", "metr", "nres", "nree", "nutr",
         "phys", "plas", "plpt", "psyc", "rnge", "scil", "soci", "soil", "soft",
         "sped", "stat", "vbms"}
HUMANITIES = {"ahis", "arab", "artp", "arts", "cerm", "chin", "clas", "comm", "czec",
               "danc", "draw", "engl", "film", "fren", "germ", "gist", "glst", "grek",
               "grph", "hebr", "hist", "japn", "jomc", "jour", "jgen", "juds", "latn",
               "modl", "mrst", "musc", "muap", "mucp", "muen", "muop", "musr", "mued",
               "muco", "mudc", "munm", "pant", "phot", "phil", "prnt", "relg", "russ",
               "sclp", "slpa", "span", "thea", "watc", "wmns", "emar"}
SOCIAL = {"adpr", "anth", "brdc", "crim", "econ", "edps", "ethn", "hrha", "jomc",
           "jour", "jgen", "pols", "soci", "socw"}
MEDICAL = {"cyaf", "gero", "hmed", "nutr", "pvet", "slpa", "vbms"}
PROFESSIONAL = {"acct", "acts", "abus", "aecn", "agen", "alec", "agri", "agst", "aero",
                 "arch", "aren", "asci", "athc", "athp", "blaw", "bsad", "casc", "cehs",
                 "cfpa", "chin", "cnst", "comm", "crpl", "dsgn", "eaep", "econ", "edps",
                 "emar", "entb", "entr", "envr", "fdst", "fina", "fors", "geog", "hrtm",
                 "ides", "intf", "jgen", "jomc", "jour", "larc", "life", "mlsc", "mngt",
                 "mrkt", "navs", "nsst", "pgam", "raik", "scma", "scil", "spmc", "teac",
                 "tmfd", "uhon", "wmns", "ento"}


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
        return "graduate" if n >= 400 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_block(block):
    dept_span = block.find("span", class_="cb_subject_code")
    num_span = block.find("span", class_="cb_course_number")
    title_span = block.find("span", class_="title")
    desc_div = block.find("div", class_="cb_description")

    if not dept_span or not num_span or not title_span:
        return None

    dept = dept_span.get_text(strip=True)
    num = num_span.get_text(strip=True)
    title = title_span.get_text(strip=True)
    desc = ""
    if desc_div:
        p = desc_div.find("p")
        if p:
            # Remove "Description:" label
            for strong in p.find_all("strong"):
                strong.decompose()
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


DEPARTMENTS = [
    "acct", "acts", "adpr", "aero", "abus", "aecn", "agen", "alec", "agri",
    "agst", "asci", "anth", "arab", "aren", "arch", "ahis", "artp", "cerm",
    "draw", "grph", "pant", "phot", "prnt", "sclp", "arts", "watc", "astr",
    "athc", "athp", "bioc", "bios", "bsen", "brdc", "bsad", "blaw", "chme",
    "chem", "cyaf", "chin", "cive", "clas", "casc", "cfpa", "comm", "crpl",
    "csce", "cone", "cnst", "crim", "czec", "danc", "dsgn", "econ", "cehs",
    "edps", "ecen", "emar", "ensc", "engr", "engl", "ento", "entr", "enve",
    "envr", "film", "fina", "fdst", "fors", "fren", "geog", "geol", "geos",
    "gero", "gist", "glst", "gras", "grek", "hebr", "hist", "hrtm", "hrha",
    "hmed", "ides", "intf", "japn", "jomc", "jour", "jgen", "juds", "larc",
    "latn", "life", "mngt", "mrkt", "matl", "math", "mech", "mrst", "metr",
    "mbio", "mlsc", "modl", "musc", "muap", "mucp", "muen", "muop", "musr",
    "mued", "muco", "mudc", "munm", "nsst", "nres", "nree", "navs", "nutr",
    "phil", "phys", "plas", "plpt", "pols", "pvet", "pgam", "psyc", "raik",
    "rnge", "relg", "russ", "scil", "socw", "soci", "soft", "soil", "span",
    "sped", "slpa", "spmc", "stat", "scma", "teac", "tmfd", "thea", "uhon",
    "vbms", "wmns", "comb", "fitn", "indv", "mark", "oded", "racs",
]


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Nebraska-Lincoln Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")
    print(f"Scraping {len(DEPARTMENTS)} departments...\n")

    for dept in DEPARTMENTS:
        url = f"{BASE_URL}/undergraduate/courses/{dept}/"
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
        time.sleep(0.25)

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
