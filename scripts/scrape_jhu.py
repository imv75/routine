#!/usr/bin/env python3
"""
JHU e-catalogue scraper for Marinovic (2026) curriculum dataset.
Scrapes e-catalogue.jhu.edu for all departments, 2020-21 through 2025-26.
HTML structure: div.courseblock > span.detail-code + span.detail-title + p.courseblockextra...
Available years: 2020-21 to 2025-26 (HTML archives); prior years are PDFs only.
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://e-catalogue.jhu.edu"
OUTPUT_DIR = "/home/user/routine/data/jhu"
PROGRESS_FILE = "/home/user/routine/data/jhu/scrape_progress.json"

# Years to scrape: (start_year_int, label, url_prefix)
CATALOG_YEARS = [
    ("2020", "2020-2021", "/archive/2020-21"),
    ("2021", "2021-2022", "/archive/2021-22"),
    ("2022", "2022-2023", "/archive/2022-23"),
    ("2023", "2023-2024", "/archive/2023-24"),
    ("2024", "2024-2025", "/archive/2024-25"),
    ("2025", "2025-2026", ""),  # current catalog, no archive prefix
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
    "diaspora", "reparations", "microaggression", "implicit bias",
    "systemic racism",
]

WESTERN_CANON_KEYWORDS = [
    "western civilization", "western tradition", "western thought",
    "great books", "liberal arts tradition",
    "ancient greece", "ancient rome", "greek philosophy", "roman law",
    "classical antiquity", "greco-roman",
    "renaissance", "enlightenment", "medieval philosophy", "reformation",
    "shakespeare", "plato", "aristotle", "homer", "dante", "virgil",
    "milton", "cicero", "socrates", "augustine", "aquinas", "machiavelli",
    "hobbes", "descartes", "kant", "hegel", "locke", "tocqueville",
    "montesquieu",
    "bible", "biblical", "iliad", "odyssey", "aeneid", "divine comedy",
    "canterbury tales", "leviathan", "federalist",
    "classics", "classical",
]

CLIMATE_NARROW_KEYWORDS = [
    "climate change", "global warming", "greenhouse gas", "carbon emissions",
    "decarbonization", "net zero", "climate policy", "climate science",
    "climate adaptation", "climate mitigation", "climate justice",
]

CLIMATE_BROAD_KEYWORDS = CLIMATE_NARROW_KEYWORDS + [
    "sustainability", "sustainable", "sustainable development",
    "renewable energy", "clean energy",
]

# Area map keyed by (school, dept_num) where dept_num is an int range
# School prefixes: AS, BU, ED, EN, ME, NR, PH, PY, SA
# Within AS, area depends on department number
AS_DEPT_AREA = {
    1: "Other",         # AS.001 First Year Seminars
    4: "Humanities",    # AS.004 Writing Program
    10: "Humanities",   # AS.010 History of Art
    20: "STEM",         # AS.020 Biology
    30: "STEM",         # AS.030 Chemistry
    40: "Humanities",   # AS.040 Classics
    50: "Social Sciences",  # AS.050 Cognitive Science
    60: "Humanities",   # AS.060 English
    61: "Humanities",   # AS.061 Film and Media Studies
    70: "Social Sciences",  # AS.070 Anthropology
    80: "STEM",         # AS.080 Neuroscience
    100: "Humanities",  # AS.100 History
    110: "STEM",        # AS.110 Mathematics
    130: "Humanities",  # AS.130-134 Near Eastern Studies
    131: "Humanities",
    132: "Humanities",
    133: "Humanities",
    134: "Humanities",
    136: "Humanities",  # AS.136 Archaeology
    140: "Humanities",  # AS.140 History of Science
    145: "Humanities",  # AS.145 Medicine, Science & Humanities
    150: "Humanities",  # AS.150 Philosophy
    171: "STEM",        # AS.171-173 Physics & Astronomy
    172: "STEM",
    173: "STEM",
    180: "Social Sciences",  # AS.180 Economics
    190: "Social Sciences",  # AS.190-191 Political Science
    191: "Social Sciences",
    192: "Social Sciences",  # AS.192 International Studies
    194: "Humanities",       # AS.194 Islamic Studies
    196: "Social Sciences",  # AS.196 Agora Institute
    197: "Social Sciences",  # AS.197 Economy and Society
    200: "Social Sciences",  # AS.200 Psychological & Brain Sciences
    210: "Humanities",  # AS.210-217 Modern Languages
    211: "Humanities",
    212: "Humanities",
    213: "Humanities",
    214: "Humanities",
    215: "Humanities",
    216: "Humanities",
    217: "Humanities",
    220: "Humanities",  # AS.220 Writing Seminars
    225: "Humanities",  # AS.225 Theatre Arts
    230: "Social Sciences",  # AS.230 Sociology
    250: "STEM",        # AS.250 Biophysics
    270: "STEM",        # AS.270-271 Earth & Planetary Sciences
    271: "STEM",
    280: "Medical Sciences",  # AS.280 Public Health Studies
    290: "STEM",        # AS.290 Behavioral Biology
    300: "Humanities",  # AS.300 Comparative Thought & Literature
    305: "Social Sciences",  # AS.305 Critical Study of Racism
    310: "Humanities",  # AS.310 East Asian Studies
    360: "Other",       # AS.360 Interdepartmental
    361: "Social Sciences",  # AS.361 Latin American Studies
    362: "Social Sciences",  # AS.362 Africana Studies
    363: "Humanities",  # AS.363 Women, Gender & Sexuality
    370: "Humanities",  # AS.370-381 Language Education
    371: "Humanities",  # AS.371 Art
    372: "Humanities",
    373: "Humanities",
    374: "Social Sciences",  # AS.374 Military Science
    375: "Humanities",
    376: "Humanities",  # AS.376 Music
    377: "Humanities",
    378: "Humanities",
    379: "Humanities",
    380: "Humanities",
    381: "Humanities",
    389: "Humanities",  # AS.389 Museums and Society
    410: "STEM",        # AS.410 Biotechnology
    420: "STEM",        # AS.420 Environmental Sciences
    425: "Social Sciences",  # AS.425 Energy Policy and Climate
    430: "STEM",        # AS.430 GIS
    440: "Social Sciences",  # AS.440 Applied Economics
    450: "Other",       # AS.450 Liberal Arts
    455: "Humanities",  # AS.455 Film and Media
    460: "Humanities",  # AS.460 Museum Studies
    465: "Humanities",  # AS.465 Cultural Heritage Management
    470: "Social Sciences",  # AS.470 Government
    472: "Social Sciences",  # AS.472 Geospatial Intelligence
    475: "Other",       # AS.475 Research Administration
    480: "Social Sciences",  # AS.480 Communication
    485: "Professional",     # AS.485 Organizational Leadership
    490: "Humanities",  # AS.490 Writing
    491: "Humanities",  # AS.491 Science Writing
    492: "Humanities",  # AS.492 Teaching Writing / Non-Dept
    999: "Other",       # AS.999 AAP
}

EN_DEPT_AREA = {
    500: "STEM",    # General Engineering
    501: "Other",   # First Year Seminars
    510: "STEM",    # Materials Science
    515: "STEM",
    520: "STEM",    # ECE
    525: "STEM",
    530: "STEM",    # Mechanical Engineering
    535: "STEM",
    540: "STEM",    # Chemical & Biomolecular
    545: "STEM",
    553: "STEM",    # Applied Math & Stats
    555: "STEM",    # Financial Math
    560: "STEM",    # Civil Engineering
    565: "STEM",
    570: "STEM",    # Environmental Health & Engineering
    575: "STEM",
    580: "STEM",    # Biomedical Engineering
    585: "STEM",
    595: "Professional",  # Engineering Management
    601: "STEM",    # Computer Science
    620: "STEM",    # Robotics
    625: "STEM",    # Applied & Computational Math
    635: "STEM",    # Information Systems Engineering
    645: "STEM",    # Systems Engineering
    650: "STEM",    # Information Security
    655: "STEM",    # Healthcare Systems Engineering
    660: "Professional",  # Center for Leadership Education
    661: "Professional",
    662: "Professional",
    663: "Professional",
    665: "STEM",    # Robotics and Autonomous Systems
    670: "STEM",    # NanoBio Technology
    675: "STEM",    # Space Systems Engineering
    685: "STEM",    # Data Science
    695: "STEM",    # Cybersecurity
    700: "STEM",    # Doctor of Engineering
    705: "STEM",    # Artificial Intelligence
}

SCHOOL_DEFAULT_AREA = {
    "BU": "Professional",    # Carey Business School
    "ED": "Professional",    # School of Education
    "ME": "Medical Sciences", # School of Medicine
    "NR": "Medical Sciences", # School of Nursing
    "PH": "Medical Sciences", # Bloomberg School of Public Health
    "PY": "Humanities",      # Peabody Institute (Music)
    "SA": "Social Sciences", # SAIS
}


def get_dept_area(dept_code: str) -> str:
    """Map department code like 'AS.100', 'EN.601' to broad area."""
    parts = dept_code.split(".")
    if len(parts) < 2:
        return "Other"
    school = parts[0].upper()
    try:
        dept_num = int(parts[1])
    except ValueError:
        dept_num = 0

    if school == "AS":
        return AS_DEPT_AREA.get(dept_num, "Other")
    elif school == "EN":
        return EN_DEPT_AREA.get(dept_num, "STEM")
    else:
        return SCHOOL_DEFAULT_AREA.get(school, "Other")


def keyword_match(text: str, keywords: list) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if " " in kw:
            if kw in text_lower:
                return True
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                return True
    return False


def classify_level(course_num: str) -> str:
    digits = re.sub(r"[^0-9]", "", course_num)
    if digits:
        n = int(digits)
        return "undergraduate" if n < 500 else "graduate"
    return "unknown"


def parse_courses_from_html(html: str, catalog_year: str, year_label: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    courses = []
    blocks = soup.find_all("div", class_="courseblock")

    for block in blocks:
        # Extract course code
        code_span = block.find("span", class_="detail-code")
        title_span = block.find("span", class_="detail-title")
        if not code_span or not title_span:
            continue

        raw_code = code_span.get_text(strip=True).rstrip(".")  # e.g. "AS.100.102"
        raw_title = title_span.get_text(strip=True).rstrip(".")

        # Parse code: SCHOOL.DEPT_NUM.COURSE_NUM
        code_parts = raw_code.split(".")
        if len(code_parts) < 3:
            continue
        school = code_parts[0].upper()
        dept_num = code_parts[1]
        course_num = code_parts[2]
        dept_code = f"{school}.{dept_num}"

        # Collect description from extra paragraphs
        extra_paras = block.find_all("p", class_="courseblockextra")
        description = ""
        for p in extra_paras:
            txt = p.get_text(" ", strip=True)
            # Skip distribution area, foundational abilities, prerequisites labels
            if re.match(r"(Distribution Area:|AS Foundational|EN Foundational|Writing Intensive|Prerequisite|Credit)", txt):
                continue
            if not description and len(txt) > 20:
                description = txt

        combined = f"{raw_title} {description}".strip()
        area = get_dept_area(dept_code)

        courses.append({
            "university": "jhu",
            "academic_year": catalog_year,
            "academic_year_label": year_label,
            "department_code": dept_code,
            "course_number": course_num,
            "title": raw_title,
            "description": description,
            "broad_area": area,
            "level": classify_level(course_num),
            "progressive_signal": keyword_match(combined, PROGRESSIVE_KEYWORDS),
            "western_canon_signal": keyword_match(combined, WESTERN_CANON_KEYWORDS),
            "climate_narrow_signal": keyword_match(combined, CLIMATE_NARROW_KEYWORDS),
            "climate_broad_signal": keyword_match(combined, CLIMATE_BROAD_KEYWORDS),
            "cross_listed_with": "",
            "cross_listed": False,
            "deduplicated": False,
        })

    return courses


def get_dept_links(session, year_prefix: str) -> list:
    """Get all department URLs for a given catalog year."""
    index_url = f"{BASE_URL}{year_prefix}/course-descriptions/"
    try:
        resp = session.get(index_url, timeout=30)
        if resp.status_code != 200:
            print(f"  Index {index_url}: HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"  Index {index_url}: Error {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen = set()
    links = []
    for l in soup.find_all("a", href=True):
        href = l["href"]
        # Match department links: /course-descriptions/... or /archive/.../course-descriptions/...
        if ("/course-descriptions/" in href
                and href != f"{year_prefix}/course-descriptions/"
                and href != "/course-descriptions/"
                and not href.endswith(".pdf")
                and "e-nextcatalogue" not in href
                and href not in seen):
            seen.add(href)
            links.append(href)

    return links


def fetch_dept_courses(session, dept_path: str, catalog_year: str, year_label: str) -> list:
    url = f"{BASE_URL}{dept_path}"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            print(f"  [{dept_path}] HTTP {resp.status_code}")
            return None  # None = error, [] = empty but ok
        return parse_courses_from_html(resp.text, catalog_year, year_label)
    except Exception as e:
        print(f"  [{dept_path}] Error: {e}")
        return None


def deduplicate(rows: list) -> list:
    """Deduplicate by (title, course_number) within a year."""
    seen = {}
    for row in rows:
        key = (row["title"].lower().strip(), row["course_number"])
        if key not in seen:
            seen[key] = row
            row["deduplicated"] = True
        else:
            row["deduplicated"] = False
    return rows


def compute_summary(rows: list, catalog_year: str, year_label: str) -> dict:
    deduped = [r for r in rows if r["deduplicated"]]
    total = len(deduped)
    if total == 0:
        return {}

    prog = sum(1 for r in deduped if r["progressive_signal"])
    canon = sum(1 for r in deduped if r["western_canon_signal"])
    clim_n = sum(1 for r in deduped if r["climate_narrow_signal"])
    clim_b = sum(1 for r in deduped if r["climate_broad_signal"])

    return {
        "university": "jhu",
        "academic_year": catalog_year,
        "academic_year_label": year_label,
        "total_raw_courses": len(rows),
        "total_deduplicated": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2),
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2),
        "climate_narrow_count": clim_n,
        "climate_narrow_pct": round(100 * clim_n / total, 2),
        "climate_broad_count": clim_b,
        "climate_broad_pct": round(100 * clim_b / total, 2),
    }


def write_csv(rows: list, path: str):
    if not rows:
        return
    fieldnames = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated", "cross_listed_with",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_years": {}, "last_updated": None}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def scrape_year(session, catalog_year: str, year_label: str, year_prefix: str,
                progress: dict) -> dict:
    year_key = catalog_year
    if year_key in progress.get("completed_years", {}) and progress["completed_years"][year_key].get("done"):
        print(f"  Year {year_label}: already completed, skipping.")
        return progress["completed_years"][year_key]

    print(f"\n=== Scraping {year_label} ===")
    dept_links = get_dept_links(session, year_prefix)
    print(f"  Found {len(dept_links)} department links")
    if not dept_links:
        return {"done": False, "error": "no_depts"}

    completed_depts = set(progress.get("completed_years", {}).get(year_key, {}).get("completed_depts", []))
    failed_depts = set(progress.get("completed_years", {}).get(year_key, {}).get("failed_depts", []))

    all_rows = []
    # Load previously saved rows if resuming
    raw_csv = f"{OUTPUT_DIR}/jhu_{catalog_year}_raw.csv"
    if completed_depts and os.path.exists(raw_csv):
        with open(raw_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
        print(f"  Resuming: {len(all_rows)} rows already scraped")

    start = time.time()
    for i, dept_path in enumerate(dept_links):
        if dept_path in completed_depts or dept_path in failed_depts:
            continue

        courses = fetch_dept_courses(session, dept_path, catalog_year, year_label)

        if courses is None:
            failed_depts.add(dept_path)
            print(f"  [{i+1}/{len(dept_links)}] {dept_path}: error")
        elif len(courses) == 0:
            completed_depts.add(dept_path)  # empty but valid
        else:
            all_rows.extend(courses)
            completed_depts.add(dept_path)
            elapsed = time.time() - start
            print(f"  [{i+1}/{len(dept_links)}] {dept_path}: {len(courses)} courses (total {len(all_rows)}, {elapsed:.0f}s)")

        # Save progress every 20 depts
        if (i + 1) % 20 == 0:
            write_csv(all_rows, raw_csv)
            year_state = {
                "done": False,
                "completed_depts": list(completed_depts),
                "failed_depts": list(failed_depts),
                "raw_count": len(all_rows),
            }
            progress["completed_years"][year_key] = year_state
            progress["last_updated"] = datetime.now().isoformat()
            save_progress(progress)

        time.sleep(0.3)

    # Final write
    write_csv(all_rows, raw_csv)
    print(f"  Raw: {len(all_rows)} courses from {len(completed_depts)} depts ({len(failed_depts)} failed)")

    # Deduplication
    all_rows = deduplicate(all_rows)
    deduped = [r for r in all_rows if r["deduplicated"]]
    dupes = len(all_rows) - len(deduped)
    print(f"  Dedup: {len(all_rows)} -> {len(deduped)} unique ({dupes} removed)")

    # Write clean CSV
    clean_csv = f"{OUTPUT_DIR}/jhu_{catalog_year}.csv"
    write_csv(all_rows, clean_csv)

    # Compute summary
    summary = compute_summary(all_rows, catalog_year, year_label)
    print(f"  Progressive: {summary.get('progressive_count',0)} ({summary.get('progressive_pct',0):.1f}%)")
    print(f"  Canon: {summary.get('canon_count',0)} ({summary.get('canon_pct',0):.1f}%)")
    print(f"  Climate narrow: {summary.get('climate_narrow_count',0)} ({summary.get('climate_narrow_pct',0):.1f}%)")

    year_result = {
        "done": True,
        "completed_depts": list(completed_depts),
        "failed_depts": list(failed_depts),
        "raw_count": len(all_rows),
        "dedup_count": len(deduped),
        "summary": summary,
    }
    progress["completed_years"][year_key] = year_result
    progress["last_updated"] = datetime.now().isoformat()
    save_progress(progress)

    return year_result


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    progress = load_progress()
    if "completed_years" not in progress:
        progress["completed_years"] = {}

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (research; curriculum-dataset; contact: imvial@gmail.com)",
        "Accept": "text/html,application/xhtml+xml",
    })

    all_summaries = []

    for catalog_year, year_label, year_prefix in CATALOG_YEARS:
        result = scrape_year(session, catalog_year, year_label, year_prefix, progress)
        if result.get("summary"):
            all_summaries.append(result["summary"])

    # Write combined summary JSON
    summary_file = f"{OUTPUT_DIR}/jhu_summary.json"
    with open(summary_file, "w") as f:
        json.dump(all_summaries, f, indent=2)

    print("\n=== FINAL SUMMARY (all years, deduplicated) ===")
    total_courses = sum(s.get("total_deduplicated", 0) for s in all_summaries)
    print(f"Total course-years collected: {total_courses}")
    for s in all_summaries:
        print(f"  {s['academic_year_label']}: {s.get('total_deduplicated',0)} courses "
              f"(prog={s.get('progressive_pct',0):.1f}%, canon={s.get('canon_pct',0):.1f}%)")

    return all_summaries


if __name__ == "__main__":
    main()
