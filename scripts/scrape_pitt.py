#!/usr/bin/env python3
"""
University of Pittsburgh Course Catalog Scraper.
catalog.upp.pitt.edu uses Acalog CMS.
Course listing pages at content.php (paginated, 100/page).
Individual course data at preview_course.php (small, ~6KB, static HTML).
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
    "BIOENGR", "BIOINF", "BIOL", "CHEM", "CHEM ENG", "CE", "CHE",
    "CS", "CSC", "CMPBIO", "CMPINF", "CMPSC",
    "ECE", "ENGR", "GEOL", "MATH", "ME", "MSE", "NEUROSCI",
    "PHYS", "PHYCS", "STAT", "STATS", "EAS", "EE", "IE", "ISE",
    "BIOSC", "BIOC", "BMIS", "ENG", "PETE", "PITT EE",
}
HUM_SUBJECTS = {
    "AFRCNA", "ART", "ARTSC", "CL", "CLASS", "DUTCH", "ENGL",
    "FILM", "FILMG", "FILMST", "FREN", "GERST", "GREEK",
    "HIST", "HPS", "ITAL", "JAPAN", "JPNSE", "LCTL", "LING",
    "MUS", "MUSIC", "PHIL", "PORT", "RUSS", "SLAVC", "SPAN",
    "THEA", "ADMPS", "ARABIC", "CHIN", "COGSCI", "ENGWRT", "RELGST",
}
SOC_SUBJECTS = {
    "ADMJ", "ANTH", "BUSACC", "BUSECN", "BUSENV", "BUSFIN", "BUSMIS",
    "BUSMKT", "BUSORG", "BUSPHR", "COMM", "ECON", "EDUC", "EPIDEM",
    "GEOG", "GSWS", "HS", "HUM", "INTBP", "LAW", "LSOCI", "MGMT",
    "POL", "POLSC", "PSY", "PSYC", "PUBHLT", "SOC", "SOCWRK", "SW",
    "URBNST", "WGS",
}
MED_SUBJECTS = {
    "BCHS", "BIOST", "CLBSC", "CLRES", "DENT", "EPID", "FTADM",
    "HCMG", "IDM", "INTMD", "MED", "MICBIO", "MLAB", "NURS",
    "OT", "PATH", "PHARM", "PT", "RAD", "REHSCI", "RSPH", "SHRS",
}


def classify_area(subject):
    s = subject.upper().strip()
    if s in STEM_SUBJECTS:
        return "STEM"
    if s in HUM_SUBJECTS:
        return "Humanities"
    if s in SOC_SUBJECTS:
        return "Social Sciences"
    if s in MED_SUBJECTS:
        return "Medical Sciences"
    return "Other"


def classify_level(career_str, course_number):
    c = (career_str or "").lower()
    if c and "undergraduate" not in c and "graduate" in c:
        return "graduate"
    # Also infer from number (Pitt uses 2000+ for grad in some schools)
    nums = re.findall(r'\d+', str(course_number))
    if nums:
        try:
            if int(nums[0]) >= 2000:
                return "graduate"
        except Exception:
            pass
    return "undergraduate"


def check_keywords(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_pitt_course(html, year, label):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Pattern: "DEPT XXXX - TITLE Minimum Credits: N ..."
    # or "DEPT XXXX - TITLE No Credits Offered ..."
    m = re.search(
        r'\b([A-Z][A-Z0-9 ]{1,10}?)\s+(\d{4}[A-Z]?)\s+-\s+(.+?)\s+'
        r'(?:Minimum Credits?:|No Credits)',
        text
    )
    if not m:
        return None

    dept = m.group(1).strip()
    num = m.group(2)
    title = m.group(3).strip()
    # Remove any trailing junk from title (catalog header text leaks in)
    title = re.sub(r'\s*(Acalog|ACMS|Print|Add to).*', '', title).strip()

    # Extract description: between credits/no-credits line and "Academic Career:"
    desc = ""
    m2 = re.search(
        r'(?:Minimum Credits?:.*?Maximum Credits?:.*?\d+|No Credits Offered)\s+(.+?)\s+'
        r'(?:Academic Career:|Course Component:|Grade Component:|Course Requirements:)',
        text, re.DOTALL
    )
    if m2:
        desc = m2.group(1).strip()
    desc = re.sub(r'\s+', ' ', desc)
    desc = re.sub(r'^(Pre-?requisite|Prerequisite)[^.]*\.\s*', '', desc, flags=re.IGNORECASE)

    # Academic Career
    m3 = re.search(r'Academic Career:\s*(\S+)', text)
    career = m3.group(1) if m3 else ""

    level = classify_level(career, num)
    full = f"{title} {desc}"

    return {
        "university": "pitt",
        "academic_year": year,
        "academic_year_label": label,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept),
        "level": level,
        "progressive_signal": int(check_keywords(full, PROGRESSIVE_KEYWORDS)),
        "western_canon_signal": int(check_keywords(full, WESTERN_CANON_KEYWORDS)),
        "climate_narrow_signal": int(check_keywords(full, CLIMATE_NARROW_KEYWORDS)),
        "climate_broad_signal": int(check_keywords(full, CLIMATE_BROAD_KEYWORDS)),
        "cross_listed": False,
        "deduplicated": True,
    }


BASE = "https://catalog.upp.pitt.edu"
CATOID = 235
NAVOID = 24840


def get_all_coids(session):
    coids = []
    page = 1
    while True:
        if page == 1:
            url = f"{BASE}/content.php?catoid={CATOID}&navoid={NAVOID}"
        else:
            url = (f"{BASE}/content.php?catoid={CATOID}&navoid={NAVOID}"
                   f"&filter%5Bitem_type%5D=3&filter%5Bonly_active%5D=1"
                   f"&filter%5B3%5D=1&filter%5Bcpage%5D={page}")
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            print(f"  Listing page {page} returned {r.status_code}, stopping")
            break
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.find_all("a", href=True)
        page_coids = []
        for a in links:
            h = a.get("href", "")
            mm = re.search(r'preview_course\.php\?catoid=\d+&coid=(\d+)', h)
            if mm:
                page_coids.append(mm.group(1))
        if not page_coids:
            break
        coids.extend(page_coids)
        print(f"  Page {page}: {len(page_coids)} courses (total: {len(coids)})", flush=True)
        # Check if there's a next page
        next_page_links = [a for a in links
                           if f"cpage%5D={page+1}" in a.get("href", "")
                           or f"cpage]={page+1}" in a.get("href", "")]
        if not next_page_links:
            break
        page += 1
        time.sleep(0.3)
    return list(set(coids))


def fetch_course(session, coid, year, label):
    url = f"{BASE}/preview_course.php?catoid={CATOID}&coid={coid}"
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return None, coid
        course = parse_pitt_course(r.text, year, label)
        return course, None
    except Exception:
        return None, coid


def scrape_pitt():
    university = "pitt"
    year = "2025"
    label = "2025-2026"
    output_dir = "/home/user/routine/data/pitt"
    os.makedirs(output_dir, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    print("=== University of Pittsburgh Course Catalog Scraper ===")
    print("Collecting course COIDs from catalog pages...")
    coids = get_all_coids(session)
    print(f"Found {len(coids)} unique course COIDs")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/pitt_2025.csv"
    csvfile = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csvfile, fieldnames=fields)
    writer.writeheader()

    all_courses = []
    seen = set()
    failed = []
    completed = 0

    for i, coid in enumerate(coids, 1):
        # Rotate session every 300 requests
        if i % 300 == 0:
            session.close()
            session = requests.Session()
            session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            time.sleep(2.0)

        course, err = fetch_course(session, coid, year, label)
        if err:
            failed.append(coid)
        elif course:
            key = f"{course['department_code']}_{course['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(course)
                writer.writerow(course)
                completed += 1
        if i % 500 == 0:
            csvfile.flush()
            print(f"  [{i}/{len(coids)}] {completed} courses, {len(failed)} failed", flush=True)
        time.sleep(0.15)

    csvfile.flush()

    if failed:
        print(f"\nRetrying {len(failed)} failed COIDs...")
        session.close()
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        retry = failed[:]
        failed = []
        for coid in retry:
            course, err = fetch_course(session, coid, year, label)
            if err:
                failed.append(coid)
            elif course:
                key = f"{course['department_code']}_{course['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(course)
                    writer.writerow(course)
                    completed += 1
            time.sleep(0.2)
        csvfile.flush()

    csvfile.close()
    session.close()

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
        "source": "catalog.upp.pitt.edu (Acalog CMS, preview_course.php)",
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
    with open(f"{output_dir}/pitt_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn} ({summary['climate_narrow_pct']}%) | Climate broad: {cb} ({summary['climate_broad_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")
    return summary


if __name__ == "__main__":
    scrape_pitt()
