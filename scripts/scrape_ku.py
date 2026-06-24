#!/usr/bin/env python3
"""
University of Kansas course catalog scraper.
URL: catalog.ku.edu/{college}/
HTML: div.courseblock > div.cols > span.detail-code "DEPT 102." + span.detail-title "Title."
      + div.courseblockextra (description)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "ku"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.ku.edu"
OUTPUT_DIR = f"/home/user/routine/data/{UNIVERSITY}"
OUTPUT_CSV = f"{OUTPUT_DIR}/{UNIVERSITY}_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/{UNIVERSITY}_summary.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

COLLEGES = [
    "liberal-arts-sciences",
    "engineering",
    "business",
    "education",
    "pharmacy",
    "law",
    "nursing",
    "music",
    "architecture",
    "journalism-mass-communications",
    "health-professions",
    "social-welfare",
    "professional-studies",
    "public-affairs-administration",
    "schoolofmedicine",
    "graduate-studies",
    "flex",
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

STEM = {"aaae", "ae", "atro", "biol", "chem", "ces", "cis", "cmsc", "eecs", "entr",
        "envs", "geog", "geol", "math", "me", "naro", "nurs", "phsx", "psyc",
        "stat", "thea"}
HUMANITIES = {"aaas", "afam", "amer", "arab", "arth", "chin", "clas", "comm",
              "engl", "film", "fren", "germ", "grek", "hist", "ital", "japn",
              "jewi", "latn", "ling", "mll", "musc", "phil", "port", "relg",
              "russ", "slav", "span", "thea", "wgss"}
SOCIAL = {"aaas", "anth", "com", "crim", "econ", "educ", "geog", "glbl", "hss",
          "ints", "jour", "lacs", "law", "pa", "pols", "ppol", "psyc", "soc",
          "soci", "socw", "urb", "wgss"}
MEDICAL = {"ahp", "atht", "bhs", "clhs", "gen", "hlsc", "md", "nurs", "ot",
           "path", "phmd", "phth", "pt", "pubh", "shs", "soc"}
PROFESSIONAL = {"acct", "arch", "badm", "bus", "dnst", "fin", "fnce", "hpm",
                "law", "lawm", "mba", "mgmt", "mktg", "nfps", "pmgt", "real"}


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


def parse_college_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        # Find code span: span.text.detail-code
        code_span = block.find("span", class_=lambda c: c and "detail-code" in c)
        title_span = block.find("span", class_=lambda c: c and "detail-title" in " ".join(c if isinstance(c, list) else [c]) and "detail-title_with_icons" not in " ".join(c if isinstance(c, list) else [c]))
        if not code_span:
            continue
        code_text = code_span.get_text(strip=True)
        # Code format: "AAAS 102." or "AAAS 102"
        m = re.match(r"([A-Z][A-Z0-9&/]*)\s+([\w]+)\.?", code_text)
        if not m:
            continue
        dept = m.group(1).strip().split("/")[0].split("&")[0].strip()
        num = m.group(2).strip()

        if title_span:
            title = title_span.get_text(strip=True).rstrip(".")
        else:
            title = ""

        # Description: in div.courseblockextra.noindent
        desc_div = block.find("div", class_=lambda c: c and "courseblockextra" in c)
        desc = desc_div.get_text(" ", strip=True) if desc_div else ""
        # Clean up cross-listing notes from description
        desc = re.sub(r"\s*\(Same as.*?\)", "", desc).strip()

        if not title and not desc:
            continue
        courses.append((dept, num, title, desc))
    return courses


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Kansas Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    for college in COLLEGES:
        url = f"{BASE_URL}/{college}/"
        try:
            r = session.get(url, timeout=30)
            if r.status_code != 200:
                print(f"  SKIP {college}: HTTP {r.status_code}")
                failed.append(college)
                continue
            parsed = parse_college_page(r.text)
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
                print(f"  {college}: {new} courses")
            elif not parsed:
                failed.append(college)
        except Exception as e:
            print(f"  ERROR {college}: {e}")
            failed.append(college)
        time.sleep(0.5)

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
