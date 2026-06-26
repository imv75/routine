#!/usr/bin/env python3
"""Purdue University Banner SIS Course Scraper.
Uses selfservice.mypurdue.purdue.edu/prod/bwckctlg.p_display_courses
Available terms: Spring 2008 - Fall 2026. Descriptions available.
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://selfservice.mypurdue.purdue.edu/prod/bwckctlg.p_display_courses"
SUBJECT_LIST_URL = "https://selfservice.mypurdue.purdue.edu/prod/bwckctlg.p_disp_cat_term_date"

# Fall terms from Fall 2008 to Fall 2026 (Fall YYYY → AY YYYY+1)
# Term code: YYYY10 for Fall, YYYY20 for Spring
FALL_TERMS = [
    ("200910", "Fall 2008", 2009),   # AY 2009
    ("201010", "Fall 2009", 2010),
    ("201110", "Fall 2010", 2011),
    ("201210", "Fall 2011", 2012),
    ("201310", "Fall 2012", 2013),
    ("201410", "Fall 2013", 2014),
    ("201510", "Fall 2014", 2015),
    ("201610", "Fall 2015", 2016),
    ("201710", "Fall 2016", 2017),
    ("201810", "Fall 2017", 2018),
    ("201910", "Fall 2018", 2019),
    ("202010", "Fall 2019", 2020),
    ("202110", "Fall 2020", 2021),
    ("202210", "Fall 2021", 2022),
    ("202310", "Fall 2022", 2023),
    ("202410", "Fall 2023", 2024),
    ("202510", "Fall 2024", 2025),
    ("202610", "Fall 2025", 2026),
    ("202710", "Fall 2026", 2027),
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

CLIMATE_NARROW_KEYWORDS = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]

CLIMATE_BROAD_KEYWORDS = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]

# Subject code → broad area mapping for Purdue
SUBJECT_AREA = {
    # Humanities
    "AMST": "Humanities", "ARAB": "Humanities", "ARCH": "Humanities",
    "ART": "Humanities", "ASAM": "Humanities", "ASIA": "Humanities",
    "ASL": "Humanities", "BAND": "Humanities", "CLAS": "Humanities",
    "CLCS": "Humanities", "CMPL": "Humanities", "COM": "Humanities",
    "DANC": "Humanities", "EALC": "Humanities", "ENG": "Humanities",
    "ENGL": "Humanities", "FILM": "Humanities", "FLL": "Humanities",
    "FLM": "Humanities", "FR": "Humanities", "FREN": "Humanities",
    "GER": "Humanities", "GRDM": "Humanities", "GREK": "Humanities",
    "GS": "Humanities", "HEBR": "Humanities", "HIST": "Humanities",
    "HUMA": "Humanities", "ILCS": "Humanities", "ITAL": "Humanities",
    "JPNS": "Humanities", "JWST": "Humanities", "KOR": "Humanities",
    "LALS": "Humanities", "LATN": "Humanities", "LING": "Humanities",
    "MUS": "Humanities", "NELC": "Humanities", "NEWM": "Humanities",
    "OVST": "Humanities", "PHIL": "Humanities", "PLSH": "Humanities",
    "PTGS": "Humanities", "REL": "Humanities", "RUSS": "Humanities",
    "SA": "Humanities", "SCLA": "Humanities", "THTR": "Humanities",
    "WGSS": "Humanities", "WRIT": "Humanities", "CHNS": "Humanities",
    # Social Sciences
    "AAS": "Social Sciences", "ANTH": "Social Sciences",
    "COMM": "Social Sciences", "CSR": "Social Sciences",
    "ECON": "Social Sciences", "EDCI": "Social Sciences",
    "EDPS": "Social Sciences", "EDST": "Social Sciences",
    "GEOG": "Social Sciences", "GNS": "Social Sciences",
    "GNST": "Social Sciences", "HHS": "Social Sciences",
    "HDFS": "Social Sciences", "HTM": "Social Sciences",
    "IDIS": "Social Sciences", "JOUR": "Social Sciences",
    "LC": "Social Sciences", "OLS": "Social Sciences",
    "POL": "Social Sciences", "POLS": "Social Sciences",
    "PPOL": "Social Sciences", "PSY": "Social Sciences",
    "PUBH": "Social Sciences", "QSCI": "Social Sciences",
    "SCOM": "Social Sciences", "SOC": "Social Sciences",
    "SOCI": "Social Sciences",
    # STEM
    "AAE": "STEM", "ABE": "STEM", "AGRY": "STEM",
    "ASTR": "STEM", "AT": "STEM", "BCHM": "STEM",
    "BIOC": "STEM", "BIOL": "STEM", "BME": "STEM",
    "BMS": "STEM", "BTNY": "STEM", "CE": "STEM",
    "CHE": "STEM", "CHEM": "STEM", "CIT": "STEM",
    "CNIT": "STEM", "CS": "STEM", "CSCI": "STEM",
    "DSCI": "STEM", "EAPS": "STEM", "EAS": "STEM",
    "ECE": "STEM", "ENE": "STEM", "ENGR": "STEM",
    "ENTM": "STEM", "FNR": "STEM", "GEOL": "STEM",
    "GEOS": "STEM", "IE": "STEM", "INFO": "STEM",
    "IT": "STEM", "MA": "STEM", "MARS": "STEM",
    "MATH": "STEM", "MATR": "STEM", "ME": "STEM",
    "MICR": "STEM", "MSE": "STEM", "NUCL": "STEM",
    "PHYS": "STEM", "QSCI": "STEM", "SE": "STEM",
    "STAT": "STEM", "BIOL": "STEM",
    # Medical
    "ANSC": "Medical Sciences", "BTNY": "Medical Sciences",
    "CDIS": "Medical Sciences", "CLPH": "Medical Sciences",
    "HLSC": "Medical Sciences", "HK": "Medical Sciences",
    "HSC": "Medical Sciences", "HSCI": "Medical Sciences",
    "HSOP": "Medical Sciences", "KINE": "Medical Sciences",
    "MCMP": "Medical Sciences", "NUR": "Medical Sciences",
    "NUTR": "Medical Sciences", "PBHL": "Medical Sciences",
    "PHRM": "Medical Sciences", "PHSL": "Medical Sciences",
    "PULM": "Medical Sciences", "RADI": "Medical Sciences",
    "RADX": "Medical Sciences", "RAON": "Medical Sciences",
    "NUPH": "Medical Sciences",
    # Professional
    "ACCT": "Professional", "AGEC": "Professional",
    "BUS": "Professional", "CCE": "Professional",
    "CEMT": "Professional", "CET": "Professional",
    "CGT": "Professional", "CM": "Professional",
    "CMGT": "Professional", "ECET": "Professional",
    "EDU": "Professional", "EEE": "Professional",
    "EEN": "Professional", "ENTR": "Professional",
    "FIN": "Professional", "FMGT": "Professional",
    "HSRV": "Professional", "IBE": "Professional",
    "IDE": "Professional", "IET": "Professional",
    "ILS": "Professional", "IM": "Professional",
    "MGMT": "Professional", "MIS": "Professional",
    "MKTG": "Professional", "OPP": "Professional",
    "REAL": "Professional", "RPMP": "Professional",
}


def classify_area(subj_code):
    return SUBJECT_AREA.get(subj_code.upper(), "Other")


def classify_level(course_num):
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
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    return s


def get_subjects(session, term_code):
    """Fetch subject list for a term via POST."""
    try:
        r = session.post(SUBJECT_LIST_URL,
                         data={"cat_term_in": term_code},
                         timeout=60)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        select = soup.find("select", {"name": "sel_subj"})
        if not select:
            return []
        return [opt["value"] for opt in select.find_all("option")
                if opt.get("value") and opt["value"] != "dummy"]
    except Exception as e:
        print(f"  Error getting subjects for {term_code}: {e}")
        return []


def fetch_subject_courses(session, term_code, subj_code):
    """Fetch all courses for one subject in one term."""
    params = {
        "term_in": term_code,
        "one_subj": subj_code,
        "sel_crse_strt": "",
        "sel_crse_end": "",
        "sel_subj": subj_code,
        "sel_levl": "",
        "sel_schd": "",
        "sel_coll": "",
        "sel_divs": "",
        "sel_dept": "",
        "sel_attr": "",
    }
    try:
        r = session.get(BASE_URL, params=params, timeout=60)
        if r.status_code != 200:
            return []
        return parse_course_page(r.text, subj_code)
    except Exception as e:
        return []


def parse_course_page(html, subj_code):
    """Parse Purdue Banner SIS course listing page."""
    soup = BeautifulSoup(html, "lxml")
    courses = []

    title_tds = soup.find_all("td", class_="nttitle")
    for td in title_tds:
        title_text = td.get_text(" ", strip=True)
        # Format: "CS 10000 - An Introduction To Computer Science"
        m = re.match(r"^([A-Z]+)\s+(\S+)\s+-\s+(.+)$", title_text)
        if not m:
            continue
        dept = m.group(1)
        course_num = m.group(2)
        title = m.group(3).strip()

        # Description in next row
        desc = ""
        parent_row = td.parent
        next_row = parent_row.find_next_sibling("tr")
        if next_row:
            desc_td = next_row.find("td")
            if desc_td:
                raw_desc = desc_td.get_text(" ", strip=True)
                # Remove "Credit Hours: X.XX." prefix
                raw_desc = re.sub(r"^Credit Hours:\s*[\d.]+\.\s*", "", raw_desc)
                desc = re.sub(r"\s+", " ", raw_desc).strip()

        courses.append({
            "dept_code": dept,
            "course_number": course_num,
            "title": title,
            "description": desc,
        })

    return courses


FIELDNAMES = [
    "university", "academic_year", "academic_year_label",
    "department_code", "course_number", "title", "description",
    "broad_area", "level",
    "progressive_signal", "western_canon_signal",
    "climate_narrow_signal", "climate_broad_signal",
    "cross_listed", "deduplicated",
]


def scrape_term(term_code, term_name, acad_year, subjects, session_factory):
    """Scrape all courses for one term. Returns list of course dicts."""
    print(f"\n=== {term_name} → AY {acad_year} ({len(subjects)} subjects) ===")
    label = f"{acad_year-1}-{str(acad_year)[-2:]}"

    all_courses = []
    seen = set()  # (dept, course_num) dedup per term

    def fetch_one(subj):
        s = session_factory()
        return subj, fetch_subject_courses(s, term_code, subj)

    # Use threading for parallel requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_one, subj): subj for subj in subjects}
        done = 0
        for future in as_completed(futures):
            subj, courses = future.result()
            done += 1
            if courses:
                for c in courses:
                    key = (c["dept_code"], c["course_number"])
                    if key in seen:
                        continue
                    seen.add(key)
                    text_for_kw = f"{c['title']} {c['description']}"
                    all_courses.append({
                        "university": "Purdue University",
                        "academic_year": acad_year,
                        "academic_year_label": label,
                        "department_code": c["dept_code"],
                        "course_number": c["course_number"],
                        "title": c["title"],
                        "description": c["description"],
                        "broad_area": classify_area(c["dept_code"]),
                        "level": classify_level(c["course_number"]),
                        "progressive_signal": 1 if check_kw(text_for_kw, PROGRESSIVE_KEYWORDS) else 0,
                        "western_canon_signal": 1 if check_kw(text_for_kw, WESTERN_CANON_KEYWORDS) else 0,
                        "climate_narrow_signal": 1 if check_kw(text_for_kw, CLIMATE_NARROW_KEYWORDS) else 0,
                        "climate_broad_signal": 1 if check_kw(text_for_kw, CLIMATE_BROAD_KEYWORDS) else 0,
                        "cross_listed": 0,
                        "deduplicated": 1,
                    })
            if done % 50 == 0:
                print(f"  {done}/{len(subjects)} subjects done, {len(all_courses)} courses so far")

    print(f"  {term_name}: {len(all_courses)} unique courses")
    return all_courses


def scrape_purdue():
    output_dir = "/home/user/routine/data/purdue"
    os.makedirs(output_dir, exist_ok=True)

    # Get subjects from most recent term
    main_session = make_session()
    print("Fetching subject list...")
    subjects = get_subjects(main_session, "202710")
    if not subjects:
        print("  Failed to get subject list via POST, using cached list")
        subjects_file = "/tmp/claude-0/-home-user-routine/5b7bb097-4b98-5896-968e-71c5c8b4faca/scratchpad/purdue_subjects.txt"
        if os.path.exists(subjects_file):
            with open(subjects_file) as f:
                subjects = [s.strip() for s in f if s.strip()]
        else:
            print("  ERROR: No subject list available")
            return {}

    print(f"Found {len(subjects)} subjects")

    # Filter out IU cross-listed and other special subjects
    skip_suffixes = ["-IU", "-NW", "-FT"]
    subjects_filtered = subjects  # Keep all for now

    def session_factory():
        return make_session()

    summary = {
        "university": "Purdue University",
        "short_name": "purdue",
        "source": "selfservice.mypurdue.purdue.edu/prod/bwckctlg.p_display_courses",
        "note": "Banner SIS catalog. Fall terms only. Descriptions available.",
        "years": {}
    }

    total_courses = 0

    for term_code, term_name, acad_year in reversed(FALL_TERMS):
        label = f"{acad_year-1}-{str(acad_year)[-2:]}"
        fname = f"purdue_{acad_year}.csv"
        fpath = os.path.join(output_dir, fname)

        # Skip if already done
        if os.path.exists(fpath):
            import csv as csv_mod
            with open(fpath) as f:
                n = sum(1 for _ in f) - 1
            print(f"  {term_name} (AY {acad_year}): already exists ({n} courses), skipping")
            if n > 0:
                with open(fpath) as f:
                    reader = csv_mod.DictReader(f)
                    courses_list = list(reader)
                prog = sum(1 for c in courses_list if c.get("progressive_signal") == "1") / n if n else 0
                canon = sum(1 for c in courses_list if c.get("western_canon_signal") == "1") / n if n else 0
                summary["years"][str(acad_year)] = {
                    "catalog_year": acad_year,
                    "label": label,
                    "courses": n,
                    "progressive_pct": round(prog * 100, 2),
                    "western_canon_pct": round(canon * 100, 2),
                    "file": fname,
                }
                total_courses += n
            continue

        courses = scrape_term(term_code, term_name, acad_year, subjects_filtered, session_factory)

        if not courses:
            print(f"  {term_name}: 0 courses, skipping file write")
            continue

        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(courses)

        n = len(courses)
        total_courses += n
        prog = sum(1 for c in courses if c["progressive_signal"]) / n if n else 0
        canon = sum(1 for c in courses if c["western_canon_signal"]) / n if n else 0

        summary["years"][str(acad_year)] = {
            "catalog_year": acad_year,
            "label": label,
            "courses": n,
            "progressive_pct": round(prog * 100, 2),
            "western_canon_pct": round(canon * 100, 2),
            "file": fname,
        }
        print(f"  Saved {fname}: {n} courses (prog={prog*100:.1f}%, canon={canon*100:.1f}%)")

    summary["total_courses"] = total_courses
    summary["catalog_years"] = len(summary["years"])

    with open(os.path.join(output_dir, "purdue_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Purdue complete: {total_courses} courses across {len(summary['years'])} years ===")
    return summary


if __name__ == "__main__":
    scrape_purdue()
