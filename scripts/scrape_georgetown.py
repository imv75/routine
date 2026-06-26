#!/usr/bin/env python3
"""Georgetown University Course Archive Scraper.
Scrapes sitearchives.georgetown.edu/courses/ (2004-2017).
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://sitearchives.georgetown.edu/courses/"

# Year → index HTML filename mapping (from the archives index page)
YEAR_INDEX_FILES = {
    2016: "index5837.html",
    2015: "index35a3.html",
    2014: "indexe354.html",
    2013: "indexc449.html",
    2012: "index0955.html",
    2011: "index3422.html",
    2010: "index1834.html",
    2009: "index6d64.html",
    2008: "index98c9.html",
    2007: "index6147.html",
    2006: "index6a2b.html",
    2005: "index7cca.html",
    2004: "indexb3e2.html",
}

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
    "ACLS": "Humanities", "AFLS": "Humanities", "AMST": "Humanities",
    "ARAB": "Humanities", "ARBC": "Humanities", "ART":  "Humanities",
    "ARTH": "Humanities", "BLS":  "Humanities", "CHIN": "Humanities",
    "CLAS": "Humanities", "CLIT": "Humanities", "CPLT": "Humanities",
    "DANC": "Humanities", "ENGL": "Humanities", "FILM": "Humanities",
    "FREN": "Humanities", "GERM": "Humanities", "GRCO": "Humanities",
    "GREK": "Humanities", "HEBR": "Humanities", "HIST": "Humanities",
    "ITAL": "Humanities", "JAPN": "Humanities", "KORE": "Humanities",
    "LATN": "Humanities", "LING": "Humanities", "MDVL": "Humanities",
    "MSVL": "Humanities", "MUSC": "Humanities", "PERS": "Humanities",
    "PHIL": "Humanities", "POLS": "Humanities", "PORT": "Humanities",
    "RELI": "Humanities", "RUSS": "Humanities", "SPAN": "Humanities",
    "THEO": "Humanities", "THTR": "Humanities", "TURK": "Humanities",
    "UKRN": "Humanities", "WGST": "Humanities", "WRIT": "Humanities",
    # Social Sciences
    "AFAM": "Social Sciences", "ANTH": "Social Sciences",
    "COMM": "Social Sciences", "CULT": "Social Sciences",
    "ECON": "Social Sciences", "GOVT": "Social Sciences",
    "GEOG": "Social Sciences", "GLBL": "Social Sciences",
    "INTL": "Social Sciences", "JOUR": "Social Sciences",
    "JUPS": "Social Sciences", "LACS": "Social Sciences",
    "NACS": "Social Sciences", "PSYC": "Social Sciences",
    "PUBS": "Social Sciences", "RECS": "Social Sciences",
    "REUS": "Social Sciences", "SEST": "Social Sciences",
    "SCST": "Social Sciences", "SOCI": "Social Sciences",
    "SOCY": "Social Sciences", "SOCL": "Social Sciences",
    # STEM
    "BCHB": "STEM", "BIOL": "STEM", "BIPH": "STEM",
    "BIST": "STEM", "BIOT": "STEM", "BSCH": "STEM",
    "CHEM": "STEM", "COSC": "STEM", "CSCI": "STEM",
    "ENST": "STEM", "MATH": "STEM", "MICB": "STEM",
    "NEUR": "STEM", "NEUR": "STEM", "PHYS": "STEM",
    "PHRM": "STEM", "STIA": "STEM",
    # Medical / Health Sciences
    "CHMS": "Medical Sciences", "CLTR": "Medical Sciences",
    "GLOH": "Medical Sciences", "HEST": "Medical Sciences",
    "HPSC": "Medical Sciences", "HSAD": "Medical Sciences",
    "HSCI": "Medical Sciences", "HPHY": "Medical Sciences",
    "INTB": "Medical Sciences", "MDCL": "Medical Sciences",
    "MEDS": "Medical Sciences", "NURS": "Medical Sciences",
    "PHAR": "Medical Sciences", "PHMD": "Medical Sciences",
    "SYMD": "Medical Sciences", "TUBI": "Medical Sciences",
    # Professional
    "ACCT": "Professional", "AAPL": "Professional",
    "ANLT": "Professional", "BADM": "Professional",
    "BUSA": "Professional", "DPOL": "Professional",
    "EDIJ": "Professional", "EMPS": "Professional",
    "EXMS": "Professional", "EXHS": "Professional",
    "FINA": "Professional", "FINC": "Professional",
    "GBAD": "Professional", "GBUS": "Professional",
    "GLSC": "Professional", "GSCM": "Professional",
    "HMGT": "Professional", "HRES": "Professional",
    "IECO": "Professional", "ILAW": "Professional",
    "ILAD": "Professional", "IMCO": "Professional",
    "INAF": "Professional", "IUPG": "Professional",
    "LAW":  "Professional", "LEAD": "Professional",
    "MGMT": "Professional", "MKTG": "Professional",
    "MKTM": "Professional", "MPS":  "Professional",
    "OPIM": "Professional", "PETA": "Professional",
    "PPDE": "Professional", "PPOL": "Professional",
    "PRJM": "Professional", "PRGM": "Professional",
    "PUBR": "Professional", "PUBP": "Professional",
    "REAL": "Professional", "SECU": "Professional",
    "SPMG": "Professional", "STEM": "Professional",
    "STRG": "Professional", "SYSM": "Professional",
    "TECM": "Professional", "UNAF": "Professional",
    "UPRP": "Professional", "URPL": "Professional",
}


def classify_area(dept_code):
    code = dept_code.upper().strip()
    return DEPT_AREA.get(code, "Other")


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:5])
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


def fetch(session, url, retries=3, delay=1.0):
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200:
                return r.text
            print(f"  HTTP {r.status_code}: {url}")
            return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print(f"  Error fetching {url}: {e}")
                return None


def get_dept_links(session, year, index_file):
    """Fetch the year's index page and extract department links."""
    url = f"{BASE_URL}{index_file}?Action=HomePage&AcademicYear={year}&AcademicTerm=FallSpring"
    html = fetch(session, url)
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    links = []
    # Look for all links containing Action=List
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "Action=List" in href and "ProgramID" in href:
            dept_name = a.get_text(strip=True)
            links.append((dept_name, href))

    return links


def parse_dept_page(html):
    """Parse a Georgetown archive department page using span.CourseCode elements."""
    soup = BeautifulSoup(html, "lxml")
    courses = []

    for code_span in soup.find_all("span", class_="CourseCode"):
        code = code_span.get_text(strip=True)  # e.g. 'ACCT-001'
        if not code:
            continue

        # Title is in the parent <strong> tag
        strong_tag = code_span.parent
        if not strong_tag:
            continue
        full_title = strong_tag.get_text(" ", strip=True)
        title = full_title.replace(code, "").strip()

        # Parse dept code and course number
        parts = re.split(r"[-\s]", code, maxsplit=1)
        dept_code = parts[0].upper()
        course_num = parts[1] if len(parts) > 1 else ""

        # Description: first sibling div with id="courseDescription"
        heading_div = strong_tag.parent  # div.ParagraphText
        description = ""
        if heading_div:
            for sib in heading_div.next_siblings:
                if not hasattr(sib, "attrs"):
                    continue
                if sib.get("id") == "courseDescription":
                    description = sib.get_text(" ", strip=True)
                    break
                # Stop at next course heading
                if sib.find("span", {"class": "CourseCode"}):
                    break

        description = re.sub(r"\s+", " ", description).strip()

        courses.append({
            "dept_code": dept_code,
            "course_number": course_num,
            "title": title,
            "description": description,
        })

    return courses


def scrape_year(session, year, index_file, output_dir):
    """Scrape all courses for a given academic year."""
    catalog_year = year + 1  # 2016 academic year = 2016-17 = catalog year 2017
    label = f"{year}-{str(year+1)[-2:]}"

    print(f"\n=== {label} (AcademicYear={year}) ===")

    dept_links = get_dept_links(session, year, index_file)
    if not dept_links:
        print(f"  No departments found for {year}")
        return [], 0

    print(f"  Found {len(dept_links)} departments")

    all_courses = []
    failed = 0

    for i, (dept_name, href) in enumerate(dept_links):
        # Build full URL
        if href.startswith("http"):
            url = href
        else:
            url = BASE_URL + href

        # Update year in URL to be safe
        url = re.sub(r'AcademicYear=\d+', f'AcademicYear={year}', url)

        html = fetch(session, url, delay=0.3)
        if not html:
            failed += 1
            continue

        dept_courses = parse_dept_page(html)

        for c in dept_courses:
            text_for_kw = f"{c['title']} {c['description']}"
            row = {
                "university": "Georgetown University",
                "academic_year": catalog_year,
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
            }
            all_courses.append(row)

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(dept_links)} depts, {len(all_courses)} courses so far")

        time.sleep(0.2)

    print(f"  Completed: {len(all_courses)} courses from {len(dept_links)-failed} depts ({failed} failed)")
    return all_courses, catalog_year


FIELDNAMES = [
    "university", "academic_year", "academic_year_label",
    "department_code", "course_number", "title", "description",
    "broad_area", "level",
    "progressive_signal", "western_canon_signal",
    "climate_narrow_signal", "climate_broad_signal",
    "cross_listed", "deduplicated",
]


def main():
    output_dir = "/home/user/routine/data/georgetown"
    os.makedirs(output_dir, exist_ok=True)

    session = make_session()

    summary = {
        "university": "Georgetown University",
        "short_name": "georgetown",
        "source": "sitearchives.georgetown.edu",
        "years": {}
    }

    total_courses = 0

    # Scrape all available years, most recent first
    for year in sorted(YEAR_INDEX_FILES.keys(), reverse=True):
        index_file = YEAR_INDEX_FILES[year]
        courses, catalog_year = scrape_year(session, year, index_file, output_dir)

        if not courses:
            continue

        # Write CSV for this year
        fname = f"georgetown_{catalog_year}.csv"
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(courses)

        n = len(courses)
        total_courses += n
        prog = sum(1 for c in courses if c["progressive_signal"]) / n if n else 0
        canon = sum(1 for c in courses if c["western_canon_signal"]) / n if n else 0

        label = f"{year}-{str(year+1)[-2:]}"
        summary["years"][str(catalog_year)] = {
            "catalog_year": catalog_year,
            "label": label,
            "courses": n,
            "progressive_pct": round(prog * 100, 2),
            "western_canon_pct": round(canon * 100, 2),
            "file": fname,
        }

        print(f"  Saved {fname}: {n} courses (prog={prog*100:.1f}%, canon={canon*100:.1f}%)")

    summary["total_courses"] = total_courses
    summary["catalog_years"] = len(summary["years"])

    with open(os.path.join(output_dir, "georgetown_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Georgetown complete: {total_courses} total courses across {len(summary['years'])} years ===")
    return summary


if __name__ == "__main__":
    main()
