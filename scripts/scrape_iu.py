#!/usr/bin/env python3
"""
Indiana University Bloomington Course Catalog Scraper.
Source: bulletin.college.indiana.edu (College of Arts and Sciences)
AJAX endpoint: /ajax/bulletin_ajax.php
Action: BULLETIN-COURSES-RESULTS
Format: <strong>SUBJ-L NNN Title (N cr.)</strong> + description text
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

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

CLIMATE_NARROW_KEYWORDS = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]

CLIMATE_BROAD_KEYWORDS = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]

STEM_SUBJECTS = {
    "ABEH", "AST", "BIOL", "BIOT", "CHEM", "COGS", "CSCI", "CSGP",
    "EAS", "MATH", "MLS", "PHYS", "SLHS", "STAT",
}
HUMANITIES_SUBJECTS = {
    "CLAS", "CMLT", "EALC", "ENG", "FOLK", "FRIT", "GER", "HISP",
    "HPSC", "JSTU", "LING", "MELC", "MEST", "MSCH", "REEI", "REL",
    "SLAV", "SOAD", "THTR",
}
SOCIAL_SUBJECTS = {
    "AAAD", "AAST", "AFRI", "AMST", "ANTH", "ARTH", "CEUS", "CJUS",
    "ECON", "ENV", "EURO", "GEOG", "GNDR", "HIST", "INST", "INTL",
    "ISLM", "LATS", "LTAM", "NAIS", "PACE", "PHIL", "POLS", "PSY",
    "RMI", "SEAS", "SGIS", "SOC", "SOAD",
}


def classify_dept(subj):
    s = subj.split("-")[0].upper()
    if s in STEM_SUBJECTS:
        return "STEM"
    if s in HUMANITIES_SUBJECTS:
        return "Humanities"
    if s in SOCIAL_SUBJECTS:
        return "Social Sciences"
    return "Other"


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:5])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def parse_course_item(item):
    strong = item.find("strong")
    if not strong:
        return None
    title_text = strong.get_text(" ", strip=True)

    # Format: "SUBJ-L NNN Title (N cr.)" or "SUBJ NNN Title (N cr.)"
    m = re.match(
        r"^([A-Z]+(?:-[A-Z])?\s+(?:[A-Z]\s+)?)\s*([\d]+[A-Z]?)\s+(.+?)\s*\([\d\-]+(?:\s*cr\.?)?\)\s*$",
        title_text,
        re.IGNORECASE,
    )
    if not m:
        m = re.match(
            r"^([A-Z]+(?:-[A-Z])?)\s+([\d]+[A-Z]?)\s+(.+)$",
            title_text,
        )
    if not m:
        return None

    dept_code = m.group(1).strip()
    num = m.group(2).strip()
    title = m.group(3).strip()
    title = re.sub(r"\s*\([\d\-]+(?:\s*cr\.?)?\)\s*$", "", title, flags=re.IGNORECASE).strip()

    # Description is text after the strong tag
    full_text = item.get_text(" ", strip=True)
    strong_text = strong.get_text(" ", strip=True)
    desc = full_text[len(strong_text):].strip()

    full = f"{title} {desc}"
    area = classify_dept(dept_code)
    level = classify_level(num)

    return {
        "university": "iu",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "department_code": dept_code,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": area,
        "level": level,
        "progressive_signal": check_keywords(full, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_keywords(full, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_keywords(full, CLIMATE_NARROW_KEYWORDS),
        "climate_broad_signal": check_keywords(full, CLIMATE_BROAD_KEYWORDS),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_subject(subject):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    s.get("https://bulletin.college.indiana.edu/curriculum/course-descriptions.html?bulletin_term=4255",
          timeout=15)

    courses = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        data_str = f"course-filter-keyword=&course-filter-subject={subject}&bulletin-filter-start={page}&bulletin_term=4255"
        try:
            r = s.post(
                "https://bulletin.college.indiana.edu/ajax/bulletin_ajax.php",
                data={"action": "BULLETIN-COURSES-RESULTS", "data": data_str},
                timeout=20,
            )
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")

            if page == 1:
                header = soup.find("div", class_="rvt-border-bottom")
                if header:
                    m = re.search(r"([\d,]+)\s+courses?\s+found", header.get_text())
                    if m:
                        total = int(m.group(1).replace(",", ""))
                        total_pages = (total + 9) // 10

            items = soup.find_all("li")
            for item in items:
                c = parse_course_item(item)
                if c:
                    courses.append(c)

            page += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"    Error page {page}: {e}")
            break

    return subject, courses


def get_subjects():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    r = s.get("https://bulletin.college.indiana.edu/curriculum/course-descriptions.html?bulletin_term=4255", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    subject_select = soup.find("select", attrs={"name": "course-filter-subject"})
    if not subject_select:
        return []
    return [o.get("value", "") for o in subject_select.find_all("option") if o.get("value", "")]


def scrape_iu():
    output_dir = "/home/user/routine/data/iu"
    os.makedirs(output_dir, exist_ok=True)

    print("=== IU Bloomington Course Catalog Scraper ===")
    print("Fetching subject list...")
    subjects = get_subjects()
    print(f"Found {len(subjects)} subjects")

    all_courses = []
    seen = set()

    for subj in subjects:
        subj_code, courses = scrape_subject(subj)
        new = 0
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
                new += 1
        if new:
            print(f"  {subj_code}: {new} courses")
        time.sleep(0.2)

    total = len(all_courses)
    if total == 0:
        print("No courses collected!")
        return {}

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    print(f"\n=== IU Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({round(100*prog/total,2)}%) | Canon: {canon} ({round(100*canon/total,2)}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({round(100*cnt/total)}%)")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/iu_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    summary = {
        "university": "iu",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "bulletin.college.indiana.edu (College of Arts and Sciences)",
        "total_courses": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2),
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2),
        "climate_narrow_count": cn,
        "climate_narrow_pct": round(100 * cn / total, 2),
        "climate_broad_count": cb,
        "climate_broad_pct": round(100 * cb / total, 2),
        "by_area": area_counts,
    }
    summary_path = f"{output_dir}/iu_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_iu()
