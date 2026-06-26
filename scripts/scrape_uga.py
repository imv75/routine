#!/usr/bin/env python3
"""
University of Georgia Course Catalog Scraper.
Source: bulletin.uga.edu/Course/_ViewAllCourses (POST API)
Format: course-card divs with pagination (18 per page).
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

STEM_DEPTS = {
    "aeng", "aero", "afsc", "agcm", "agri", "agsc", "annu", "ansc",
    "bcmb", "biol", "bmsc", "biol", "chem", "cmbi", "csci", "ento",
    "engr", "envs", "fish", "fors", "geog", "geol", "hort", "idis",
    "math", "meam", "mche", "mibo", "nrrt", "nrsc", "phys", "plan",
    "plpa", "posc", "psyc", "soil", "stat", "vepi", "vmed", "wild",
    "wsfr", "xsnd", "zool",
}
HUMANITIES_DEPTS = {
    "afam", "arab", "chin", "cmlt", "comk", "dram", "engl", "fren",
    "germ", "grek", "hist", "ital", "japn", "jour", "kore", "latn",
    "ling", "musi", "phil", "port", "reli", "russ", "span", "thea",
    "writ",
}
SOCIAL_DEPTS = {
    "anth", "crju", "econ", "geog", "gsst", "intl", "msit", "pols",
    "psyc", "soci", "sowk", "wgst", "wmst",
}
MEDICAL_DEPTS = {
    "ahsc", "alhe", "anat", "bioc", "dent", "epid", "hlth", "hsci",
    "kine", "mhp", "nurs", "ntrn", "path", "phar", "phsl", "phyt",
    "pubh", "rcth", "radt", "rspy", "sacs", "sphe",
}
PROFESSIONAL_DEPTS = {
    "acct", "aded", "adpr", "busa", "busn", "calc", "coed", "coun",
    "educ", "efnd", "emat", "emba", "epsy", "ersc", "fhce", "fina",
    "hrmt", "idst", "indt", "insu", "legl", "llib", "llaw", "mgmt",
    "mist", "mktg", "msit", "nmba", "oadm", "reco", "real", "risk",
    "rems", "socw",
}


def classify_dept(dept):
    d = dept.lower()
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


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:5])
        return "graduate" if n >= 5000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    s.headers["X-Requested-With"] = "XMLHttpRequest"
    s.headers["Referer"] = "https://bulletin.uga.edu/Course/Index"
    return s


def get_subjects():
    s = make_session()
    r = s.get("https://bulletin.uga.edu/Course/Index", timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    selects = soup.find_all("select")
    for sel in selects:
        options = sel.find_all("option")
        if len(options) > 10:
            subjects = [opt.get("value", "") for opt in options if opt.get("value")]
            if subjects:
                return subjects
    return []


def parse_card(card):
    crn_li = card.find("li", class_="crn")
    if not crn_li:
        return None
    course_ref = crn_li.get_text(" ", strip=True)
    # Format: "DEPT NNNN" or "DEPT NNNN(DEPT2 NNNN)" for cross-listed
    m = re.match(r"([A-Z][A-Z0-9]+)\s+([\d]+[A-Z]?)", course_ref)
    if not m:
        return None
    dept = m.group(1).strip()
    num = m.group(2).strip()

    title_p = card.find("p", class_="large")
    title = title_p.get_text(" ", strip=True) if title_p else ""

    desc_p = card.find("div", class_="course-card--bottom")
    desc = ""
    if desc_p:
        desc_text_p = desc_p.find("p")
        desc = desc_text_p.get_text(" ", strip=True) if desc_text_p else ""

    full_text = f"{title} {desc}"
    area = classify_dept(dept)
    level = classify_level(num)

    return {
        "university": "uga",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": area,
        "level": level,
        "progressive_signal": check_keywords(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_keywords(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_keywords(full_text, CLIMATE_NARROW_KEYWORDS),
        "climate_broad_signal": check_keywords(full_text, CLIMATE_BROAD_KEYWORDS),
        "cross_listed": "(" in course_ref,
        "deduplicated": True,
    }


def scrape_subject(prefix):
    s = make_session()
    courses = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        try:
            r = s.post(
                "https://bulletin.uga.edu/Course/_ViewAllCourses",
                data={
                    "page": page,
                    "keyword": "",
                    "coursePrefix": prefix,
                    "courseType": [],
                    "genEdCore": [],
                    "ICs": [],
                    "enteredCoursePrefix": "",
                    "enteredCourseNumber": "",
                },
                timeout=20,
            )
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.find_all("div", class_="course-card")

            total_span = soup.find("li", class_="total")
            if total_span:
                try:
                    total_pages = int(total_span.get_text(strip=True))
                except:
                    pass

            for card in cards:
                c = parse_card(card)
                if c:
                    courses.append(c)

            page += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"  Error scraping {prefix} page {page}: {e}")
            break

    return prefix, courses


def scrape_uga():
    output_dir = "/home/user/routine/data/uga"
    os.makedirs(output_dir, exist_ok=True)

    print("=== University of Georgia Course Catalog Scraper ===")
    print("Fetching subject list...")
    subjects = get_subjects()
    print(f"Found {len(subjects)} subjects")

    all_courses = []
    seen = set()
    failed = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(scrape_subject, subj): subj for subj in subjects}
        for fut in as_completed(futures):
            prefix, courses = fut.result()
            new = 0
            for c in courses:
                key = f"{c['department_code']}_{c['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(c)
                    new += 1
            if new:
                print(f"  {prefix}: {new} courses")

    total = len(all_courses)
    if not total:
        print("No courses found!")
        return {}

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    print(f"\n=== UGA Summary ===")
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
    csv_path = f"{output_dir}/uga_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    summary = {
        "university": "uga",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "bulletin.uga.edu/Course/_ViewAllCourses",
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
    summary_path = f"{output_dir}/uga_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_uga()
