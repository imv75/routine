#!/usr/bin/env python3
"""
UCLA Course Catalog Scraper.
catalog.registrar.ucla.edu uses Courseloop CMS (Next.js SSR).
Course data is embedded in __NEXT_DATA__ JSON on each course page.
Course URLs are discovered via sitemap.xml.
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

# UCLA subject code → broad area mapping (partial; rest falls to "Other")
STEM_PREFIXES = {
    "AERO ST", "AM", "ANAT", "ANTHRO", "ASTRO", "BIOENGR", "BIOL",
    "BIOMATH", "BIOPHYS", "C&S BIO", "CBE", "CHEM", "CHEM ENGR", "CIVIL",
    "COM SCI", "CSB", "DESMA", "EC ENGR", "ENGR", "EPS SCI", "GEOG",
    "GEOL", "GEOPHYS", "HUM GNTC", "LIFESCI", "MATH", "MAT SCI",
    "MECH&AE", "MCD BIO", "MGMT", "MICROBIO", "MOL BIO", "MOL CLSC",
    "MOL TOX", "NEUROSCI", "NURSING", "NR EAST", "PHYSCI", "PHYSICS",
    "PSYCH", "STATS", "SYS BIOL",
}
HUM_PREFIXES = {
    "AFAM", "AF AMER", "ART", "ART HIS", "CAEM", "CHIN", "CLASSIC",
    "CLUSTER", "COMM", "COMPTLG", "DANCE", "DUTCH", "ENGL", "FILM TV",
    "FILIPN", "FREN", "GENDER", "GE CLST", "GERMAN", "GREEK", "HEBREW",
    "HIST", "HUN", "INDO", "IRAN", "ITAL", "JAPAN", "JEWISH", "KOREA",
    "LGBTQS", "LING", "MLATIN", "MUS", "MUSCLG", "MUSC", "MUS IND",
    "NR AMER", "PHILOS", "PORTGSE", "RELIG", "RUSSN", "SCAND", "SLAVC",
    "SPAN", "SWAHIL", "TAGALG", "THAI", "THEATER", "TURK", "VIET",
    "YIDDSH",
}
SOC_PREFIXES = {
    "ANTHRO", "ASIA AM", "ASIAN", "CHICANO", "COMM", "ECON", "EDUC",
    "ETHNMUS", "GLBL ST", "INTL DV", "LAW", "MGMT", "POL SCI", "PUB AFF",
    "SOC", "SOC WLF", "SOCIOL", "URBN PL", "WL ARTS",
}


def check_keywords(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def classify_area(subject):
    s = subject.upper().strip()
    if s in STEM_PREFIXES:
        return "STEM"
    if s in HUM_PREFIXES:
        return "Humanities"
    if s in SOC_PREFIXES:
        return "Social Sciences"
    return "Other"


def classify_level(course_level_str):
    if not course_level_str:
        return "undergraduate"
    cl = course_level_str.lower()
    if "graduate" in cl and "undergraduate" not in cl:
        return "graduate"
    return "undergraduate"


def strip_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(str(text), "html.parser")
    return soup.get_text(" ", strip=True)


def parse_course(page_content, year, label):
    code_raw = page_content.get("code", "")
    title = page_content.get("title", "")
    if not code_raw or not title:
        return None

    # Parse "AERO ST 130A" → subject="AERO ST", number="130A"
    # Pattern: letters/spaces then number+letter
    m = re.match(r"^([A-Z][A-Z &]+?)\s+(\d+\w*)$", code_raw.strip())
    if not m:
        # Try single-word subject
        m2 = re.match(r"^([A-Z]+)\s*(\d+\w*)$", code_raw.strip())
        if not m2:
            return None
        dept = m2.group(1)
        num = m2.group(2)
    else:
        dept = m.group(1).strip()
        num = m.group(2)

    desc_html = page_content.get("description", "") or ""
    desc = strip_html(desc_html)
    desc = re.sub(r"^(Pre-?requisite|Prerequisite)[^.]*\.\s*", "", desc, flags=re.IGNORECASE)

    course_level = page_content.get("course_level", "") or ""
    full = f"{title} {desc}"

    return {
        "university": "ucla",
        "academic_year": year,
        "academic_year_label": label,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept),
        "level": classify_level(course_level),
        "progressive_signal": int(check_keywords(full, PROGRESSIVE_KEYWORDS)),
        "western_canon_signal": int(check_keywords(full, WESTERN_CANON_KEYWORDS)),
        "climate_narrow_signal": int(check_keywords(full, CLIMATE_NARROW_KEYWORDS)),
        "climate_broad_signal": int(check_keywords(full, CLIMATE_BROAD_KEYWORDS)),
        "cross_listed": False,
        "deduplicated": True,
    }


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    return s


def fetch_course(session, url, year, label):
    try:
        r = session.get(url, timeout=25)
        if r.status_code == 429 or r.status_code == 503:
            return None, url, True  # rate limited
        if r.status_code != 200:
            return None, url, False
        soup = BeautifulSoup(r.text, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script:
            return None, url, False
        data = json.loads(script.string)
        pc = data.get("props", {}).get("pageProps", {}).get("pageContent", {})
        if not pc or pc.get("contentTypeLabel") != "Course":
            return None, None, False  # Not a course page, skip silently
        course = parse_course(pc, year, label)
        return course, None, False
    except Exception as e:
        return None, url, False


def get_course_urls(session):
    r = session.get("https://catalog.registrar.ucla.edu/sitemap.xml", timeout=15)
    soup = BeautifulSoup(r.text, "xml")
    sitemap_urls = [loc.text for loc in soup.find_all("loc")]

    all_course_urls = []
    for sm_url in sitemap_urls:
        r2 = session.get(sm_url, timeout=15)
        soup2 = BeautifulSoup(r2.text, "xml")
        urls = [loc.text for loc in soup2.find_all("loc")]
        # Only 2025 courses (most recent catalog year)
        for u in urls:
            if "/course/2025/" in u:
                all_course_urls.append(u)

    return all_course_urls


def scrape_ucla():
    university = "ucla"
    year = "2025"
    label = "2025-2026"
    output_dir = "/home/user/routine/data/ucla"
    os.makedirs(output_dir, exist_ok=True)

    print("=== UCLA Course Catalog Scraper ===")
    print("Collecting course URLs from sitemaps...")

    init_session = make_session()
    course_urls = get_course_urls(init_session)
    init_session.close()
    print(f"Found {len(course_urls)} course URLs for 2025-26")

    all_courses = []
    seen = set()
    failed = []

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/ucla_2025.csv"
    csvfile = open(csv_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csvfile, fieldnames=fields)
    writer.writeheader()

    SESSION_ROTATE_EVERY = 150  # new session every N requests
    session = make_session()
    completed = 0
    consecutive_fails = 0

    for i, url in enumerate(course_urls, 1):
        # Rotate session periodically to avoid rate limiting
        if i % SESSION_ROTATE_EVERY == 0:
            session.close()
            session = make_session()
            time.sleep(2.0)  # brief pause on session rotation

        course, err, rate_limited = fetch_course(session, url, year, label)
        if rate_limited:
            # Immediately rotate session and back off
            session.close()
            session = make_session()
            time.sleep(10.0)
            # Retry once with fresh session
            course, err, rate_limited = fetch_course(session, url, year, label)
            if rate_limited:
                failed.append(url)
                consecutive_fails += 1
            elif err:
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
        elif err:
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

        # If many consecutive failures, rotate session
        if consecutive_fails >= 20:
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

    # Retry failures once with fresh sessions
    if failed:
        print(f"\nRetrying {len(failed)} failed URLs...")
        retry_urls = failed[:]
        failed = []
        session = make_session()
        for i, url in enumerate(retry_urls, 1):
            if i % 100 == 0:
                session.close()
                session = make_session()
                time.sleep(3.0)
            course, err, _ = fetch_course(session, url, year, label)
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
                print(f"  Retry [{i}/{len(retry_urls)}] {completed} total", flush=True)
            time.sleep(0.2)
        session.close()
        csvfile.flush()

    csvfile.close()

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): sample: {failed[:5]}")

    # CSV already written progressively above

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
        "source": "catalog.registrar.ucla.edu (Courseloop CMS, Next.js SSR, sitemap discovery)",
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
    with open(f"{output_dir}/ucla_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn} ({summary['climate_narrow_pct']}%) | Climate broad: {cb} ({summary['climate_broad_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")
    return summary


if __name__ == "__main__":
    scrape_ucla()
