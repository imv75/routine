#!/usr/bin/env python3
"""
University of Texas at Dallas course catalog scraper.
URL: catalog.utdallas.edu/2026/{grad|undergrad}/courses/{dept}
HTML: p#{dept}{num} > span.course_address "DEPT NUM" + span.course_title "Title"
      + span.course_hours "(N semester credit hours)" + remaining text = description
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "utd"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.utdallas.edu"
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

STEM = {"biol", "chem", "cs", "ce", "ece", "geog", "geosci", "math", "me", "mse",
        "phys", "se", "stat", "sysbio"}
HUMANITIES = {"ahst", "ahtc", "arab", "arts", "chin", "comm", "crwt", "engl",
              "fren", "germ", "hist", "hons", "japn", "lat", "ling", "musi",
              "phil", "port", "russ", "span", "thea", "film"}
SOCIAL = {"anth", "comm", "crim", "econ", "educ", "geog", "govt", "pa",
          "pols", "psyc", "soci", "socw", "urb"}
MEDICAL = {"biol", "bmen", "hcs", "nsc", "nurs", "pt"}
PROFESSIONAL = {"acct", "ba", "fin", "hmgt", "itss", "law", "mba", "mgmt", "mkt",
                "om", "real"}


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


def get_dept_slugs(session, level):
    url = f"{BASE_URL}/2026/{level}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        slugs = []
        pattern = rf"^/2026/{level}/courses/([a-z][a-z0-9]*)/?$"
        for a in soup.find_all("a", href=True):
            m = re.match(pattern, a["href"])
            if m:
                slugs.append(m.group(1))
        return list(dict.fromkeys(slugs))
    except Exception as e:
        print(f"  ERROR fetching {level} dept list: {e}")
        return []


def parse_dept_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for p in soup.find_all("p", id=True):
        pid = p.get("id", "")
        addr_span = p.find("span", class_="course_address")
        title_span = p.find("span", class_="course_title")
        hours_span = p.find("span", class_="course_hours")

        if not addr_span or not title_span:
            continue

        addr_text = addr_span.get_text(strip=True)
        m = re.match(r"([A-Z][A-Z0-9]*)\s+(\w+)", addr_text)
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = title_span.get_text(strip=True)

        # Description = full text minus addr, title, hours spans
        full = p.get_text(" ", strip=True)
        # Strip leading "DEPT NUM Title (N hours)" to get description
        prefix = addr_text
        if title:
            prefix = prefix + " " + title
        if hours_span:
            prefix = prefix + " " + hours_span.get_text(strip=True)
        desc = full[len(prefix):].strip() if full.startswith(prefix) else ""
        if not desc:
            # Try stripping by position
            for span in [addr_span, title_span, hours_span]:
                if span:
                    span.extract()
            desc = p.get_text(" ", strip=True)

        if not title:
            continue
        courses.append((dept, num, title, desc))
    return courses


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Texas at Dallas Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    grad_slugs = get_dept_slugs(session, "graduate")
    undergrad_slugs = get_dept_slugs(session, "undergraduate")
    print(f"Graduate depts: {len(grad_slugs)}, Undergraduate depts: {len(undergrad_slugs)}")

    # Combine: (level, slug, url)
    dept_list = [(f"{BASE_URL}/2026/graduate/courses/{s}/", s) for s in grad_slugs]
    dept_list += [(f"{BASE_URL}/2026/undergraduate/courses/{s}/", s) for s in undergrad_slugs]
    print(f"Total pages to scrape: {len(dept_list)}")

    for url, slug in dept_list:
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
