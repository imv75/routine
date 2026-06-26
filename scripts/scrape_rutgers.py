#!/usr/bin/env python3
"""Rutgers University Course Scraper.
Uses the SoC JSON API: classes.rutgers.edu/soc/api/courses.json
Available years: 2024-2026 (Fall and Spring). No descriptions available.
"""

import csv
import json
import os
import re
import time
import requests

API_URL = "https://classes.rutgers.edu/soc/api/courses.json"
CAMPUSES = ["NB", "NK", "CM"]

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

# School code → broad area (coarse; refined by subject description below)
SCHOOL_AREA = {
    "01": "Humanities",      # SAS (refined by subject)
    "03": "Professional",    # Camden liberal arts - varies
    "04": "Humanities",      # Newark arts - varies
    "05": "Professional",    # NB general
    "07": "Professional",    # Edward J. Bloustein (planning/policy)
    "08": "Medical Sciences",  # School of Health Professions
    "09": "STEM",            # Graduate School
    "10": "Professional",    # School of Management and Labor Relations
    "11": "Social Sciences", # School of Social Work / other
    "13": "Professional",    # Pharmacy
    "14": "STEM",            # School of Engineering
    "15": "Humanities",      # Mason Gross School of the Arts
    "16": "Professional",    # Rutgers Business School NB
    "17": "Humanities",      # SAS NB – cross-listed
    "18": "Humanities",      # Newark liberal arts
    "19": "Professional",    # NB School of Communication & Info
    "22": "Medical Sciences",  # RWJMS / medical
    "26": "Medical Sciences",  # Dental school
    "30": "Professional",    # NB interdisciplinary
    "31": "Professional",    # Camden business
    "33": "Professional",    # Rutgers Business School
    "34": "Professional",    # SEBS (Environmental and Biological Sciences)
    "37": "Professional",    # Graduate School-Newark
    "38": "Professional",    # Camden graduate
    "75": "Professional",    # Professional programs
    "77": "Professional",    # SAS Graduate Program
}

# Keywords in subject description → area (overrides school-level)
SUBJECT_KW_AREA = {
    # Humanities
    "literature": "Humanities", "language": "Humanities", "linguistics": "Humanities",
    "english": "Humanities", "french": "Humanities", "spanish": "Humanities",
    "italian": "Humanities", "german": "Humanities", "russian": "Humanities",
    "chinese": "Humanities", "japanese": "Humanities", "korean": "Humanities",
    "arabic": "Humanities", "hebrew": "Humanities", "hindi": "Humanities",
    "turkish": "Humanities", "persian": "Humanities", "swahili": "Humanities",
    "history": "Humanities", "philosophy": "Humanities", "religion": "Humanities",
    "art history": "Humanities", "music": "Humanities", "theater": "Humanities",
    "theatre": "Humanities", "dance": "Humanities", "cinema": "Humanities",
    "film": "Humanities", "classical": "Humanities", "classics": "Humanities",
    "medieval": "Humanities", "comparative literature": "Humanities",
    "journalism": "Humanities", "communication": "Humanities",
    # Social Sciences
    "economics": "Social Sciences", "political science": "Social Sciences",
    "political": "Social Sciences", "sociology": "Social Sciences",
    "psychology": "Social Sciences", "anthropology": "Social Sciences",
    "geography": "Social Sciences", "urban": "Social Sciences",
    "criminal justice": "Social Sciences", "social work": "Social Sciences",
    "public policy": "Social Sciences", "african american": "Social Sciences",
    "latino": "Social Sciences", "women's": "Social Sciences",
    "gender and sexuality": "Social Sciences", "labor": "Social Sciences",
    # STEM
    "computer": "STEM", "mathematics": "STEM", "statistics": "STEM",
    "physics": "STEM", "chemistry": "STEM", "biology": "STEM",
    "biochemistry": "STEM", "genetics": "STEM", "microbiology": "STEM",
    "neuroscience": "STEM", "engineering": "STEM", "astronomy": "STEM",
    "ecology": "STEM", "environmental science": "STEM", "geology": "STEM",
    # Medical
    "nursing": "Medical Sciences", "pharmacy": "Medical Sciences",
    "health": "Medical Sciences", "medicine": "Medical Sciences",
    "biomedical": "Medical Sciences", "public health": "Medical Sciences",
    "nutrition": "Medical Sciences", "physical therapy": "Medical Sciences",
    "occupational therapy": "Medical Sciences", "clinical": "Medical Sciences",
    "dental": "Medical Sciences", "kinesiology": "Medical Sciences",
    # Professional
    "business": "Professional", "accounting": "Professional",
    "finance": "Professional", "management": "Professional",
    "marketing": "Professional", "supply chain": "Professional",
    "information system": "Professional", "library": "Professional",
    "education": "Professional", "planning": "Professional",
}


def classify_area(school_code, subject_desc):
    """Classify course into broad area using school code and subject description."""
    desc_lower = subject_desc.lower() if subject_desc else ""
    for kw, area in SUBJECT_KW_AREA.items():
        if kw in desc_lower:
            return area
    return SCHOOL_AREA.get(school_code, "Other")


def classify_level(level_str, course_num):
    """Classify as undergraduate or graduate."""
    if level_str:
        lvl = str(level_str).lower()
        if "graduate" in lvl or "grad" in lvl:
            return "graduate"
        if "undergraduate" in lvl or "undergrad" in lvl:
            return "undergraduate"
    # Fall back to course number
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[:5])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def make_session():
    s = requests.Session()
    proxy = os.environ.get("HTTPS_PROXY", "")
    if proxy:
        s.proxies = {"https": proxy, "http": proxy}
    ca = "/root/.ccr/ca-bundle.crt"
    s.verify = ca if os.path.exists(ca) else True
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    return s


def fetch_semester(session, year, term, campus):
    """Fetch courses for a specific year/term/campus."""
    params = {"year": year, "term": term, "campus": campus}
    try:
        r = session.get(API_URL, params=params, timeout=60)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        print(f"  HTTP {r.status_code} for {year} term={term} campus={campus}")
        return []
    except Exception as e:
        print(f"  Error {year} term={term} campus={campus}: {e}")
        return []


FIELDNAMES = [
    "university", "academic_year", "academic_year_label",
    "department_code", "course_number", "title", "description",
    "broad_area", "level",
    "progressive_signal", "western_canon_signal",
    "climate_narrow_signal", "climate_broad_signal",
    "cross_listed", "deduplicated",
]

# term → academic year offset
# Fall 2023 → academic year 2024 (2023-24)
# Spring 2024 → academic year 2024 (2023-24)
TERM_NAMES = {0: "Winter", 1: "Spring", 7: "Summer", 9: "Fall"}


def get_acad_year(year, term):
    """Return academic year (ending year). Fall 2023 → 2024, Spring 2024 → 2024."""
    if term == 9:  # Fall
        return year + 1
    return year  # Spring/Winter/Summer → same year (end of prior acad year)


def get_acad_label(year, term):
    acad_year = get_acad_year(year, term)
    return f"{acad_year-1}-{str(acad_year)[-2:]}"


def scrape_rutgers():
    output_dir = "/home/user/routine/data/rutgers"
    os.makedirs(output_dir, exist_ok=True)

    session = make_session()

    summary = {
        "university": "Rutgers University New Brunswick",
        "short_name": "rutgers",
        "source": "classes.rutgers.edu/soc/api/courses.json",
        "note": "No course descriptions available; keyword signals based on title only",
        "years": {}
    }

    # Collect all terms: Fall and Spring for 2024, 2025, 2026
    terms_to_scrape = []
    for year in [2024, 2025, 2026]:
        terms_to_scrape.append((year, 9))  # Fall
        terms_to_scrape.append((year, 1))  # Spring

    # Group by academic year
    by_acad_year = {}  # acad_year → {courseString: course_dict}

    for year, term in terms_to_scrape:
        acad_year = get_acad_year(year, term)
        label = get_acad_label(year, term)
        term_name = TERM_NAMES.get(term, str(term))
        print(f"\n{term_name} {year} → AY {label}")

        # All campuses
        all_raw = []
        for campus in CAMPUSES:
            raw = fetch_semester(session, year, term, campus)
            print(f"  {campus}: {len(raw)} courses")
            all_raw.extend(raw)

        # Build course map for this term (deduplicate by courseString)
        term_courses = {}
        for c in all_raw:
            cs = c.get("courseString", "")
            if not cs or cs in term_courses:
                continue

            school_code = c.get("offeringUnitCode", "")
            subject_desc = c.get("subjectDescription", "")
            title = (c.get("expandedTitle") or c.get("title") or "").strip()
            course_num = c.get("courseNumber", "")

            # Department code: construct from school:subject format
            # Rutgers doesn't have traditional dept codes, use school+subject
            dept_code = f"{school_code}:{c.get('subject','')}"

            text_for_kw = title  # No description available

            term_courses[cs] = {
                "university": "Rutgers University New Brunswick",
                "academic_year": acad_year,
                "academic_year_label": label,
                "department_code": dept_code,
                "course_number": course_num,
                "title": title,
                "description": "",  # Not available via API
                "broad_area": classify_area(school_code, subject_desc),
                "level": classify_level(c.get("level", ""), course_num),
                "progressive_signal": 1 if check_kw(text_for_kw, PROGRESSIVE_KEYWORDS) else 0,
                "western_canon_signal": 1 if check_kw(text_for_kw, WESTERN_CANON_KEYWORDS) else 0,
                "climate_narrow_signal": 1 if check_kw(text_for_kw, CLIMATE_NARROW_KEYWORDS) else 0,
                "climate_broad_signal": 1 if check_kw(text_for_kw, CLIMATE_BROAD_KEYWORDS) else 0,
                "cross_listed": 0,
                "deduplicated": 1,
            }

        # Merge into by_acad_year (take latest term per course string per acad year)
        if acad_year not in by_acad_year:
            by_acad_year[acad_year] = {}
        by_acad_year[acad_year].update(term_courses)
        print(f"  → AY {label}: {len(by_acad_year[acad_year])} unique courses so far")

    # Write CSVs per academic year
    total = 0
    for acad_year in sorted(by_acad_year.keys()):
        courses = list(by_acad_year[acad_year].values())
        n = len(courses)
        total += n

        fname = f"rutgers_{acad_year}.csv"
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(courses)

        prog = sum(1 for c in courses if c["progressive_signal"]) / n if n else 0
        canon = sum(1 for c in courses if c["western_canon_signal"]) / n if n else 0
        label = courses[0]["academic_year_label"] if courses else str(acad_year)

        summary["years"][str(acad_year)] = {
            "catalog_year": acad_year,
            "label": label,
            "courses": n,
            "progressive_pct": round(prog * 100, 2),
            "western_canon_pct": round(canon * 100, 2),
            "file": fname,
        }
        print(f"\nSaved {fname}: {n} courses (prog={prog*100:.1f}%, canon={canon*100:.1f}%)")

    summary["total_courses"] = total
    summary["catalog_years"] = len(summary["years"])

    with open(os.path.join(output_dir, "rutgers_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Rutgers complete: {total} courses across {len(summary['years'])} years ===")
    return summary


if __name__ == "__main__":
    scrape_rutgers()
