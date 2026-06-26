#!/usr/bin/env python3
"""Carnegie Mellon University Schedule of Classes Scraper.
Uses the SOC Servlet at enr-apps.as.cmu.edu.
No course descriptions available; keyword signals based on title only.
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

SOC_URL = "https://enr-apps.as.cmu.edu/SOC/SOCServlet/search"

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

DEPT_AREA = {
    # Humanities
    "ARC": "Humanities",   # Architecture
    "ART": "Humanities",   # Art
    "BHA": "Humanities",   # Humanities and Arts
    "BXA": "Humanities",   # BXA Intercollege
    "DRA": "Humanities",   # Drama
    "ENG": "Humanities",   # English
    "HIS": "Humanities",   # History
    "LCL": "Humanities",   # Languages Cultures & Linguistics
    "MUS": "Humanities",   # Music
    "PHI": "Humanities",   # Philosophy
    # Social Sciences
    "ECO": "Social Sciences",  # Economics
    "PSY": "Social Sciences",  # Psychology
    "SDS": "Social Sciences",  # Social & Decision Sciences
    # STEM
    "BSC": "STEM",   # Biological Sciences
    "BMD": "STEM",   # Biomedical Engineering
    "CB":  "STEM",   # Computational Biology
    "CEE": "STEM",   # Civil & Environmental Engineering
    "CHE": "STEM",   # Chemical Engineering
    "CMY": "STEM",   # Chemistry
    "CS":  "STEM",   # Computer Science
    "ECE": "STEM",   # Electrical & Computer Engineering
    "EPP": "STEM",   # Engineering & Public Policy
    "HCI": "STEM",   # Human-Computer Interaction
    "LTI": "STEM",   # Language Technologies Institute
    "MCS": "STEM",   # MCS Interdisciplinary
    "MLG": "STEM",   # Machine Learning
    "MSC": "STEM",   # Mathematical Sciences
    "MEG": "STEM",   # Mechanical Engineering
    "MSE": "STEM",   # Materials Science
    "NSI": "STEM",   # Neuroscience Institute
    "PHY": "STEM",   # Physics
    "ROB": "STEM",   # Robotics
    "SCS": "STEM",   # SCS Interdisciplinary
    "S3D": "STEM",   # Software & Societal Systems
    "STA": "STEM",   # Statistics
    # Professional / Policy
    "AEM": "Professional",   # Arts & Entertainment Management
    "BUS": "Professional",   # Business Administration
    "BCA": "Professional",   # Computer Science and Arts
    "BEA": "Professional",   # Engineering Studies and Arts
    "BSA": "Professional",   # Science and Arts
    "CFA": "Professional",   # CFA Interdisciplinary
    "CIT": "Professional",   # CIT Interdisciplinary
    "CST": "Professional",   # Strategy and Tech
    "DES": "Professional",   # Design
    "ETC": "Professional",   # Entertainment Technology
    "H00": "Professional",   # Dietrich College
    "HC":  "Professional",   # Heinz College
    "ICT": "Professional",   # Information & Communication Tech
    "INI": "Professional",   # Information Networking
    "ISP": "Professional",   # Information Systems Program
    "ISM": "Professional",   # Information Systems Management
    "III": "Professional",   # Integrated Innovation
    "MED": "Professional",   # Medical Management
    "PMP": "Professional",   # Public Management
    "PPP": "Professional",   # Public Policy
    "CMQ": "Other",
    "CMU": "Other",
    "HSS": "Other",
    "NVS": "Other",
    "PE":  "Other",
    "STU": "Other",
}

# Semester code → (calendar year, term): F25 = Fall 2025
SEMESTER_INFO = {
    "F24": (2024, "Fall"),
    "S25": (2025, "Spring"),
    "F25": (2025, "Fall"),
    "S26": (2026, "Spring"),
    "F26": (2026, "Fall"),
}


def acad_year(sem_code):
    """Return academic year (ending year) for a semester code."""
    year, term = SEMESTER_INFO.get(sem_code, (None, None))
    if year is None:
        return None
    return year + 1 if term == "Fall" else year


def acad_label(sem_code):
    year, term = SEMESTER_INFO.get(sem_code, (None, None))
    if year is None:
        return sem_code
    ay = year + 1 if term == "Fall" else year
    return f"{ay-1}-{str(ay)[-2:]}"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def classify_level(course_num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[-3:])
        return "graduate" if n >= 600 else "undergraduate"
    except Exception:
        return "undergraduate"


def make_session():
    s = requests.Session()
    proxy = os.environ.get("HTTPS_PROXY", "")
    if proxy:
        s.proxies = {"https": proxy, "http": proxy}
    ca = "/root/.ccr/ca-bundle.crt"
    s.verify = ca if os.path.exists(ca) else True
    s.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
    return s


def fetch_semester(session, sem_code):
    """Fetch all Pittsburgh courses for a semester."""
    form_data = {
        "SEMESTER": sem_code,
        "GRAD_UNDER": "All",
        "PRG_LOCATION": "PIT",
        "DEPT": "All",
        "MINI": "NO",
        "KEYWORD": "",
        "TITLE_ONLY": "YES",
    }
    try:
        r = session.post(SOC_URL, data=form_data, timeout=60)
        if r.status_code == 200:
            return r.text
        print(f"  HTTP {r.status_code} for {sem_code}")
        return None
    except Exception as e:
        print(f"  Error {sem_code}: {e}")
        return None


def parse_soc_html(html, sem_code):
    """Parse the CMU SOC HTML response."""
    soup = BeautifulSoup(html, "lxml")
    courses = []

    # Find department sections by looking for section headers
    # and tables with course data
    current_dept = "CMU"

    # The SOC table rows: Course | Title | Units | Sec | Mini | Days | Begin | End | Location | Mode
    # Department headers appear as text in the first column with no number

    all_rows = soup.find_all("tr")
    dept_name_to_code = {}
    for dept_code, _ in DEPT_AREA.items():
        dept_name_to_code[dept_code] = dept_code

    # Look for headers and course rows
    # Headers appear as <tr><td colspan="X">DEPARTMENT NAME</td></tr> or similar
    # Course rows have a 5-digit course number in first column

    ay = acad_year(sem_code)
    label = acad_label(sem_code)

    # The section headers look like "ARTS & ENTERTAINMENT MANAGEMENT" (no table structure)
    # Let me use a different approach - look for all text patterns

    # Alternative: scan the parsed text to find sections
    course_num_pat = re.compile(r"^\d{5}$")
    seen = set()

    for row in all_rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        cell_texts = [c.get_text(strip=True) for c in cells]

        if len(cells) == 1:
            # Could be a department header
            dept_text = cell_texts[0].strip()
            if dept_text and dept_text.isupper() and len(dept_text) > 3:
                # This is likely a department header - try to map to code
                # We'll just track the current dept name
                current_dept = dept_text
            continue

        if len(cells) >= 2:
            # Check if first cell is a 5-digit course number
            course_col = cell_texts[0].strip()
            if course_num_pat.match(course_col):
                course_num = course_col
                title = cell_texts[1].strip() if len(cell_texts) > 1 else ""

                key = course_num
                if key in seen:
                    continue
                seen.add(key)

                # Infer dept from course prefix (first 2 digits)
                prefix = course_num[:2]
                # Map prefix to dept code
                dept_code = guess_dept_from_prefix(prefix)

                text_for_kw = title
                prog = 1 if check_kw(text_for_kw, PROGRESSIVE_KEYWORDS) else 0
                canon = 1 if check_kw(text_for_kw, WESTERN_CANON_KEYWORDS) else 0
                cn = 1 if check_kw(text_for_kw, CLIMATE_NARROW_KEYWORDS) else 0
                cb = 1 if check_kw(text_for_kw, CLIMATE_BROAD_KEYWORDS) else 0

                courses.append({
                    "university": "Carnegie Mellon University",
                    "academic_year": ay,
                    "academic_year_label": label,
                    "department_code": dept_code,
                    "course_number": course_num,
                    "title": title,
                    "description": "",
                    "broad_area": DEPT_AREA.get(dept_code, "Other"),
                    "level": classify_level(course_num),
                    "progressive_signal": prog,
                    "western_canon_signal": canon,
                    "climate_narrow_signal": cn,
                    "climate_broad_signal": cb,
                    "cross_listed": 0,
                    "deduplicated": 1,
                })

    return courses


# CMU course number prefix → dept code (first 2 digits of 5-digit course number)
PREFIX_TO_DEPT = {
    "02": "CB",   # Computational Biology
    "03": "BSC",  # Biological Sciences
    "04": "ICT",  # ICT
    "05": "HCI",  # HCI
    "06": "CHE",  # Chemical Engineering
    "07": "SCS",  # SCS
    "09": "CMY",  # Chemistry
    "10": "MLG",  # Machine Learning
    "11": "LTI",  # Language Technologies
    "12": "CEE",  # Civil Engineering
    "14": "INI",  # Information Networking
    "15": "CS",   # Computer Science
    "16": "ROB",  # Robotics
    "17": "S3D",  # Software & Societal
    "18": "ECE",  # ECE
    "19": "EPP",  # Engineering & Public Policy
    "21": "MSC",  # Math
    "24": "MEG",  # Mechanical Engineering
    "27": "MSE",  # Materials Science
    "33": "PHY",  # Physics
    "36": "STA",  # Statistics
    "38": "MCS",  # MCS
    "39": "CIT",  # CIT
    "42": "BMD",  # Biomedical Engineering
    "48": "ARC",  # Architecture
    "49": "III",  # Integrated Innovation
    "51": "DES",  # Design
    "52": "BXA",  # BXA
    "53": "ETC",  # Entertainment Tech
    "54": "DRA",  # Drama
    "57": "MUS",  # Music
    "60": "ART",  # Art
    "62": "CFA",  # CFA Interdisciplinary (also BCA, BEA, BHA, BSA)
    "65": "H00",  # Dietrich
    "66": "HSS",  # HSS
    "67": "ISP",  # ISP
    "69": "PE",   # PE
    "70": "BUS",  # Business
    "73": "ECO",  # Economics
    "76": "ENG",  # English
    "79": "HIS",  # History
    "80": "PHI",  # Philosophy
    "82": "LCL",  # Languages
    "84": "CST",  # Strategy and Tech
    "85": "PSY",  # Psychology
    "86": "NSI",  # Neuroscience
    "88": "SDS",  # Social Sciences
    "90": "PPP",  # Public Policy
    "91": "PMP",  # Public Management
    "92": "MED",  # Medical Management
    "93": "AEM",  # Arts & Entertainment Mgmt
    "94": "HC",   # Heinz College
    "95": "ISM",  # Info Systems Management
    "97": "CMQ",  # CMUQ
    "98": "STU",  # Student-Led
    "99": "CMU",  # University-Wide
}


def guess_dept_from_prefix(prefix):
    return PREFIX_TO_DEPT.get(prefix, "CMU")


FIELDNAMES = [
    "university", "academic_year", "academic_year_label",
    "department_code", "course_number", "title", "description",
    "broad_area", "level",
    "progressive_signal", "western_canon_signal",
    "climate_narrow_signal", "climate_broad_signal",
    "cross_listed", "deduplicated",
]

# Semesters to scrape: Fall and Spring (not Summer), most recent available
SEMESTERS = ["F24", "S25", "F25", "S26", "F26"]


def main():
    output_dir = "/home/user/routine/data/cmu"
    os.makedirs(output_dir, exist_ok=True)

    session = make_session()
    summary = {
        "university": "Carnegie Mellon University",
        "short_name": "cmu",
        "source": "enr-apps.as.cmu.edu/SOC",
        "note": "No course descriptions; keyword signals based on title only",
        "years": {}
    }

    # Group by academic year across semesters
    by_acad_year = {}

    for sem in SEMESTERS:
        print(f"\nFetching {sem}...")
        html = fetch_semester(session, sem)
        if not html:
            print(f"  Skipping {sem}: no data")
            continue

        courses = parse_soc_html(html, sem)
        print(f"  Parsed: {len(courses)} unique courses")

        ay = acad_year(sem)
        if ay not in by_acad_year:
            by_acad_year[ay] = {}
        for c in courses:
            key = c["course_number"]
            if key not in by_acad_year[ay]:
                by_acad_year[ay][key] = c
            # Merge: update label if needed
            by_acad_year[ay][key]["academic_year_label"] = acad_label(sem)

        time.sleep(1)

    # Write CSVs
    total = 0
    for ay_year in sorted(by_acad_year.keys()):
        courses = list(by_acad_year[ay_year].values())
        n = len(courses)
        total += n

        fname = f"cmu_{ay_year}.csv"
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(courses)

        prog = sum(1 for c in courses if c["progressive_signal"]) / n if n else 0
        canon = sum(1 for c in courses if c["western_canon_signal"]) / n if n else 0
        label = courses[0]["academic_year_label"] if courses else str(ay_year)

        summary["years"][str(ay_year)] = {
            "catalog_year": ay_year,
            "label": label,
            "courses": n,
            "progressive_pct": round(prog * 100, 2),
            "western_canon_pct": round(canon * 100, 2),
            "file": fname,
        }
        print(f"Saved {fname}: {n} courses (prog={prog*100:.1f}%, canon={canon*100:.1f}%)")

    summary["total_courses"] = total
    summary["catalog_years"] = len(summary["years"])

    with open(os.path.join(output_dir, "cmu_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== CMU complete: {total} courses across {len(summary['years'])} years ===")
    return summary


if __name__ == "__main__":
    main()
