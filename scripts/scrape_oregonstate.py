#!/usr/bin/env python3
"""
Oregon State University course catalog scraper.
URL: catalog.oregonstate.edu/courses/{dept}/
HTML: div.courseblock > h2.courseblocktitle <strong>"DEPT CODE, Title, N Credits"</strong>
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "oregonstate"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.oregonstate.edu"
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

STEM_DEPTS = {"aae", "as", "ai", "ats", "bb", "bhs", "bee", "bds", "bioe", "bi",
              "brr", "bot", "cbee", "ch", "cce", "ce", "clim", "cs", "crop", "css",
              "ds", "ece", "ent", "enve", "ensc", "ese", "engr", "fe", "fes", "fw",
              "fst", "gph", "geo", "gd", "hhs", "hest", "ib", "ie", "kin", "la",
              "ling", "mats", "mth", "mb", "me", "mime", "mfge", "mrm", "nse",
              "nutr", "oeas", "oc", "ph", "pbg", "rob", "sed", "sci", "esc", "se",
              "st", "soil", "sus", "snr", "tox", "wre", "wrp", "wrs", "wse", "z"}
HUMANITIES_DEPTS = {"art", "amt", "chn", "comm", "eah", "eng", "film", "fr", "ger",
                    "hst", "it", "jpn", "kor", "la", "ling", "mus", "mup", "mued",
                    "pax", "phl", "rel", "span", "ta", "wgss", "wlc", "wr", "qs"}
SOCIAL_DEPTS = {"aec", "aj", "ams", "anth", "comm", "econ", "es", "geog", "hdfs",
                "hhs", "ps", "psy", "rel", "soc", "ssci", "sw"}
MEDICAL_DEPTS = {"at", "bhs", "mb", "nutr", "phar", "pt", "vmb", "vmc", "h"}
PROFESSIONAL_DEPTS = {"actg", "ahe", "agcm", "aed", "agri", "ag", "asl", "ans",
                       "are", "ba", "bana", "bis", "cssa", "coun", "dsgn", "dsi",
                       "dast", "ed", "emgt", "fin", "fcsj", "for", "grad", "hc",
                       "hort", "hm", "intl", "ist", "lead", "ls", "mgmt", "mrkt",
                       "mnr", "ms", "nmc", "nr", "ns", "op", "pac", "ppol", "rng",
                       "sb", "sclm", "tral", "uexp", "core", "als", "aec",
                       "iepg", "iepa", "ieph"}


def classify_area(dept_code):
    d = dept_code.lower()
    if d in STEM_DEPTS:
        return "STEM"
    if d in HUMANITIES_DEPTS:
        return "Humanities"
    if d in SOCIAL_DEPTS:
        return "Social Sciences"
    if d in MEDICAL_DEPTS:
        return "Medical Sciences"
    if d in PROFESSIONAL_DEPTS:
        return "Professional"
    return "Other"


def classify_level(course_num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[:4])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_block(block):
    # OSU: h2.courseblocktitle > strong "DEPT CODE,  Title,  N Credits"
    h2 = block.find("h2", class_="courseblocktitle")
    if not h2:
        return None
    text = h2.get_text(" ", strip=True)
    # Format: "DEPT NUM,  Course Title,  N Credits" (comma-separated)
    # or: "DEPT NUM,  Course Title"
    parts = [p.strip() for p in text.split(",", 2)]
    if len(parts) < 2:
        return None
    code_part = parts[0]  # "DEPT NUM"
    title_part = parts[1] if len(parts) > 1 else ""
    # Credits part is parts[2] if present

    code_m = re.match(r"([A-Z]+)\s+([\w\-]+)", code_part)
    if not code_m:
        return None
    dept = code_m.group(1)
    num = code_m.group(2)
    title = title_part.strip()

    # Description
    desc_p = block.find("p", class_="courseblockdesc") or block.find("p", class_="courseblockextra")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""
    # Remove "Prereq:" or "Co-req:" sections
    desc = re.split(r"\s+(Prereq|Coreq|Crosslisted):", desc)[0].strip()

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
    "als", "actg", "ahe", "aae", "as", "agcm", "aed", "agri", "ag", "asl",
    "ams", "ans", "anth", "aec", "aj", "are", "art", "ai", "amt", "at",
    "ats", "bb", "bhs", "bee", "bds", "bioe", "bi", "brr", "bot", "ba",
    "bana", "bis", "che", "cbee", "ch", "chn", "cce", "ce", "clim", "cssa",
    "comm", "cs", "cem", "coun", "css", "crop", "ds", "dsgn", "dsi", "dast",
    "econ", "ed", "ece", "ese", "emgt", "engr", "eng", "ent", "eah", "enve",
    "ensc", "es", "film", "fin", "fw", "fcsj", "fst", "fes", "fe", "for",
    "fr", "geog", "gph", "geo", "ger", "grad", "gd", "hhs", "hst", "hc",
    "hort", "hm", "hdfs", "hest", "ie", "ib", "iepa", "iepg", "ieph",
    "ist", "intl", "it", "jpn", "kin", "kor", "lead", "la", "ls", "ling",
    "mgmt", "mfge", "mrm", "mast", "mrkt", "mnr", "mats", "mth", "me",
    "mime", "mb", "ms", "mus", "mup", "mued", "nr", "ns", "nmc", "nse",
    "nutr", "oeas", "oc", "op", "pax", "phar", "phl", "pac", "pt", "ph",
    "pbg", "ps", "psy", "h", "ppol", "qs", "rng", "rel", "rob", "sed",
    "sci", "esc", "ssci", "sw", "soc", "se", "soil", "span", "sb", "st",
    "sclm", "sus", "snr", "ta", "tral", "tox", "core", "uexp", "vmb", "vmc",
    "wre", "wrp", "wrs", "wgss", "wse", "wlc", "wr", "z",
]


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Oregon State University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")
    print(f"Scraping {len(DEPARTMENTS)} departments...\n")

    for dept in DEPARTMENTS:
        url = f"{BASE_URL}/courses/{dept}/"
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
        csv.DictWriter(f, fieldnames=fields).writerows(all_courses)
        f.seek(0)
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
