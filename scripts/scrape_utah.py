#!/usr/bin/env python3
"""
University of Utah Course Catalog Scraper.
catalog.utah.edu uses Coursedog (Nuxt 3 SSR).
Course data is in the large NUXT state array embedded in each course page.
Course URLs discovered via sitemap.xml.
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

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
    "BIOL", "BIOMED", "BME", "CHEM", "CE", "CHE", "CS", "CSE", "ECE", "ECS",
    "ENGR", "ENVST", "GEOL", "MATH", "ME", "MENG", "MINE", "MSE", "NEURO",
    "PHYS", "STAT", "CVEEN", "ELEC", "MEEN", "MATE", "GENE",
}
HUM_SUBJECTS = {
    "ART", "ARTH", "CHIN", "CLSS", "ENGL", "FREN", "GER", "GNDR", "GREK",
    "HEBR", "HIST", "ITAL", "JAPAN", "KORE", "LATN", "LING", "MUS", "PHIL",
    "PORT", "RUSS", "SPA", "THEA", "WRIT", "ARAB", "COMM",
}
SOC_SUBJECTS = {
    "ANTH", "ECON", "EDU", "GEOG", "MDSA", "POL", "PSY", "SOC", "SW",
    "POLS", "PSYC", "SOCY", "JWST", "ASAM", "NAIS",
}
MED_SUBJECTS = {
    "DENT", "MED", "NURS", "PHARM", "PT", "OT", "PA", "MPH", "HLTH",
    "HEALT", "MDCN", "SURG", "ANES",
}
PROF_SUBJECTS = {
    "ACCTG", "BA", "BUS", "FIN", "MGMT", "MKT", "LAW", "LEAP", "MBA",
    "ENTP", "IS", "BCOR",
}


def classify_area(subject):
    s = subject.upper()
    if s in STEM_SUBJECTS:
        return "STEM"
    if s in HUM_SUBJECTS:
        return "Humanities"
    if s in SOC_SUBJECTS:
        return "Social Sciences"
    if s in MED_SUBJECTS:
        return "Medical Sciences"
    if s in PROF_SUBJECTS:
        return "Professional"
    return "Other"


def classify_level(course_number):
    nums = re.findall(r'\d+', str(course_number))
    if nums:
        try:
            n = int(nums[0])
            return "graduate" if n >= 5000 else "undergraduate"
        except Exception:
            pass
    return "undergraduate"


def check_keywords(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def resolve_field(data, course_raw, field_name):
    idx = course_raw.get(field_name)
    if idx is None:
        return None
    if isinstance(idx, int) and 0 <= idx < len(data):
        val = data[idx]
        if isinstance(val, list) and val and isinstance(val[0], int):
            return [data[i] if isinstance(i, int) and 0 <= i < len(data) else i for i in val[:20]]
        return val
    return idx


def parse_nuxt_course(page_html, university, year, label):
    soup = BeautifulSoup(page_html, "html.parser")
    # Find the large NUXT state script
    nuxt_script = None
    for s in soup.find_all("script", src=False):
        text = s.get_text()
        if len(text) > 50000 and "ShallowReactive" in text:
            nuxt_script = text
            break
    if not nuxt_script:
        return None

    try:
        data = json.loads(nuxt_script)
    except json.JSONDecodeError:
        return None

    # Course data is at data[4]['course'] → data[course_idx]
    if len(data) < 5:
        return None
    top = data[4]
    if not isinstance(top, dict) or "course" not in top:
        return None
    course_idx = top["course"]
    if not isinstance(course_idx, int) or course_idx >= len(data):
        return None
    course_raw = data[course_idx]
    if not isinstance(course_raw, dict):
        return None

    code = resolve_field(data, course_raw, "code")
    subject = resolve_field(data, course_raw, "subjectCode")
    number = resolve_field(data, course_raw, "courseNumber")
    long_name = resolve_field(data, course_raw, "longName")
    name = resolve_field(data, course_raw, "name")
    description = resolve_field(data, course_raw, "description")

    if not code or not (long_name or name):
        return None

    title = long_name or name
    desc = str(description) if description else ""
    desc = re.sub(r"^(Pre-?requisite|Prerequisite)[^.]*\.\s*", "", desc, flags=re.IGNORECASE)

    dept = str(subject) if subject else code.split()[0] if code else "UNKNOWN"
    num = str(number) if number else ""
    if not num and code:
        parts = code.split()
        if len(parts) >= 2:
            num = parts[-1]

    full = f"{title} {desc}"
    return {
        "university": university,
        "academic_year": year,
        "academic_year_label": label,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept),
        "level": classify_level(num),
        "progressive_signal": int(check_keywords(full, PROGRESSIVE_KEYWORDS)),
        "western_canon_signal": int(check_keywords(full, WESTERN_CANON_KEYWORDS)),
        "climate_narrow_signal": int(check_keywords(full, CLIMATE_NARROW_KEYWORDS)),
        "climate_broad_signal": int(check_keywords(full, CLIMATE_BROAD_KEYWORDS)),
        "cross_listed": False,
        "deduplicated": True,
    }


def fetch_course(session, url, university, year, label):
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return None, url
        course = parse_nuxt_course(r.text, university, year, label)
        return course, None
    except Exception:
        return None, url


def get_course_urls(session):
    r = session.get("https://catalog.utah.edu/sitemap.xml", timeout=15)
    soup = BeautifulSoup(r.text, "xml")
    all_urls = [loc.text for loc in soup.find_all("loc")]
    return [u for u in all_urls if "/courses/" in u]


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    return s


def scrape_utah():
    university = "utah"
    year = "2025"
    label = "2025-2026"
    output_dir = "/home/user/routine/data/utah"
    os.makedirs(output_dir, exist_ok=True)

    init_session = make_session()
    print("=== University of Utah Course Catalog Scraper ===")
    print("Collecting course URLs from sitemap...")

    course_urls = get_course_urls(init_session)
    init_session.close()
    print(f"Found {len(course_urls)} course URLs")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/utah_2025.csv"
    csvfile = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csvfile, fieldnames=fields)
    writer.writeheader()

    all_courses = []
    seen = set()
    failed = []

    SESSION_ROTATE_EVERY = 200
    session = make_session()
    completed = 0
    consecutive_fails = 0

    for i, url in enumerate(course_urls, 1):
        if i % SESSION_ROTATE_EVERY == 0:
            session.close()
            session = make_session()
            time.sleep(2.0)

        course, err = fetch_course(session, url, university, year, label)
        if err:
            failed.append(url)
            consecutive_fails += 1
        elif course:
            key = f"{course['department_code']}_{course['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(course)
                writer.writerow(course)
                completed += 1
            consecutive_fails = 0
        else:
            consecutive_fails = 0

        if consecutive_fails >= 15:
            session.close()
            session = make_session()
            time.sleep(5.0)
            consecutive_fails = 0

        if i % 500 == 0:
            csvfile.flush()
            print(f"  [{i}/{len(course_urls)}] {completed} courses, {len(failed)} failed", flush=True)
        time.sleep(0.15)

    session.close()
    csvfile.flush()

    # Retry failures with session rotation
    if failed:
        print(f"\nRetrying {len(failed)} failed URLs...")
        retry_urls = failed[:]
        failed = []
        session = make_session()
        for i, url in enumerate(retry_urls, 1):
            if i % 150 == 0:
                session.close()
                session = make_session()
                time.sleep(3.0)
            course, err = fetch_course(session, url, university, year, label)
            if err:
                failed.append(url)
            elif course:
                key = f"{course['department_code']}_{course['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(course)
                    writer.writerow(course)
                    completed += 1
            if i % 500 == 0:
                csvfile.flush()
                print(f"  Retry [{i}/{len(retry_urls)}] {completed} total, {len(failed)} still failed", flush=True)
            time.sleep(0.2)
        session.close()
        csvfile.flush()

    csvfile.close()

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:5]}")

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": university,
        "academic_year": year,
        "academic_year_label": label,
        "source": "catalog.utah.edu (Coursedog/Nuxt SSR, sitemap discovery)",
        "total_courses": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2) if total else 0,
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2) if total else 0,
        "climate_narrow_count": cn,
        "climate_narrow_pct": round(100 * cn / total, 2) if total else 0,
        "climate_broad_count": cb,
        "climate_broad_pct": round(100 * cb / total, 2) if total else 0,
        "by_area": area_counts,
        "failed_count": len(failed),
    }
    with open(f"{output_dir}/utah_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn} ({summary['climate_narrow_pct']}%) | Climate broad: {cb} ({summary['climate_broad_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")
    return summary


if __name__ == "__main__":
    scrape_utah()
