#!/usr/bin/env python3
"""
University of Louisville course catalog scraper.
URL: catalog.louisville.edu/[undergraduate|graduate]/courses/{dept}/
HTML: div.courseblock > p.courseblocktitle "DEPT NUM. Title N Units"
      + p.courseblockdesc (description)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSITY = "louisville"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.louisville.edu"
OUTPUT_DIR = f"/home/user/routine/data/{UNIVERSITY}"
OUTPUT_CSV = f"{OUTPUT_DIR}/{UNIVERSITY}_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/{UNIVERSITY}_summary.json"

os.makedirs(OUTPUT_DIR, exist_ok=True)

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
CLIMATE_NARROW = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]
CLIMATE_BROAD = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]

STEM_PREFIXES = {
    "ae", "be", "bioc", "biol", "bsta", "ce", "che", "chem", "cis", "cs",
    "ece", "engr", "math", "me", "mse", "phys", "stat", "ast", "asnb",
    "biol", "cee", "ees", "env", "geog", "geol", "nurs",
}
HUMANITIES_PREFIXES = {
    "art", "arth", "chns", "clas", "cmds", "comm", "engl", "film", "fren",
    "germ", "hist", "hum", "ital", "japn", "lat", "ling", "musi", "musc",
    "phil", "port", "rels", "russ", "span", "spd", "thea", "wgst", "arab",
    "asl", "hebr",
}
SOCIAL_PREFIXES = {
    "anth", "crim", "econ", "geog", "pols", "psyc", "soc", "urbn", "afs",
    "asnb", "wgst",
}
MEDICAL_PREFIXES = {
    "audi", "beth", "bohc", "dent", "hsci", "medi", "nurs", "ot", "pa",
    "ph", "phth", "pt", "resp", "surg", "urol",
}
PROFESSIONAL_PREFIXES = {
    "acct", "airs", "bus", "econ", "fin", "hrls", "law", "mgmt", "mgt",
    "mktg", "msba", "pa", "plan", "pub", "real", "soc", "sowk", "spd",
    "urbn",
}


def classify_area(dept):
    d = dept.lower()
    if d in MEDICAL_PREFIXES:
        return "Medical Sciences"
    if d in STEM_PREFIXES:
        return "STEM"
    if d in HUMANITIES_PREFIXES:
        return "Humanities"
    if d in SOCIAL_PREFIXES:
        return "Social Sciences"
    if d in PROFESSIONAL_PREFIXES:
        return "Professional"
    if any(x in d for x in ["eng", "sci", "tech", "phys", "math", "bio", "chem", "stat"]):
        return "STEM"
    if any(x in d for x in ["hist", "phil", "art", "lit", "lang", "ling", "music", "reli"]):
        return "Humanities"
    if any(x in d for x in ["soc", "psyc", "pols", "econ", "geog", "anth"]):
        return "Social Sciences"
    if any(x in d for x in ["nurs", "med", "vet", "pharm", "hlth"]):
        return "Medical Sciences"
    if any(x in d for x in ["bus", "acct", "mgmt", "fin", "mktg", "law", "educ"]):
        return "Professional"
    return "Other"


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
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": f"{BASE_URL}/",
    })
    try:
        s.get(f"{BASE_URL}/", timeout=15)
    except Exception:
        pass
    return s


def get_dept_slugs(session, level):
    url = f"{BASE_URL}/{level}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            print(f"  ERROR: {level} dept listing returned {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        slugs = []
        pattern = re.compile(rf"^/{level}/courses/([a-z][a-z0-9-]*)/?$")
        for a in soup.find_all("a", href=True):
            m = pattern.match(a["href"])
            if m:
                slugs.append((level, m.group(1)))
        return list(dict.fromkeys(slugs))
    except Exception as e:
        print(f"  ERROR fetching {level} dept list: {e}")
        return []


def parse_dept_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        title_el = block.find("p", class_="courseblocktitle")
        if not title_el:
            continue
        title_text = title_el.get_text(" ", strip=True)
        # Format: "DEPT NUM. Title N Units" or "DEPT NUM. Title"
        m = re.match(r"([A-Z][A-Z0-9]*)\s+(\w+)\.\s+(.+?)(?:\s+\d+(?:\.\d+)?\s+Units?)?$", title_text)
        if not m:
            # try without trailing units
            m = re.match(r"([A-Z][A-Z0-9]*)\s+(\w+)\.\s+(.+)", title_text)
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = m.group(3).strip()
        # Strip trailing units pattern if present
        title = re.sub(r"\s+\d+(?:\.\d+)?\s+Units?\.?$", "", title).strip()

        desc = ""
        desc_el = block.find("p", class_=lambda c: c and "courseblockdesc" in c)
        if desc_el:
            raw = desc_el.get_text(" ", strip=True)
            # Strip "Description: " prefix
            raw = re.sub(r"^Description:\s*", "", raw).strip()
            if len(raw) > 10:
                desc = raw

        if not title:
            continue
        courses.append((dept, num, title, desc))
    return courses


def scrape_dept(level_slug):
    level, slug = level_slug
    s = make_session()
    url = f"{BASE_URL}/{level}/courses/{slug}/"
    try:
        r = s.get(url, timeout=25)
        if r.status_code != 200:
            return level_slug, [], True
        parsed = parse_dept_page(r.text)
        return level_slug, parsed, (len(parsed) == 0)
    except Exception as e:
        print(f"  ERROR {slug}: {e}")
        return level_slug, [], True


def main():
    session = make_session()
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Louisville Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    all_slugs = []
    for level in ["undergraduate", "graduate"]:
        slugs = get_dept_slugs(session, level)
        print(f"Found {len(slugs)} {level} departments")
        all_slugs.extend(slugs)

    print(f"Total departments: {len(all_slugs)}. Scraping...")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scrape_dept, ls): ls for ls in all_slugs}
        for future in as_completed(futures):
            level_slug, parsed, had_error = future.result()
            level, slug = level_slug
            if had_error:
                failed.append(f"{level}/{slug}")
                continue
            new = 0
            for dept, num, title, desc in parsed:
                key = f"{dept}_{num}"
                if key not in seen:
                    seen.add(key)
                    full_text = f"{title} {desc}"
                    all_courses.append({
                        "university": UNIVERSITY,
                        "academic_year": CATALOG_YEAR,
                        "academic_year_label": CATALOG_LABEL,
                        "department_code": dept,
                        "course_number": num,
                        "title": title,
                        "description": desc,
                        "broad_area": classify_area(dept),
                        "level": classify_level(num),
                        "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
                        "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
                        "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
                        "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
                        "cross_listed": False,
                        "deduplicated": True,
                    })
                    new += 1
            if new:
                print(f"  {slug.upper()} ({level[:4]}): {new} courses")

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:30])}")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal", "cross_listed", "deduplicated",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_courses)

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
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
        "failed_depts": failed,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote: {OUTPUT_CSV}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        pct = round(100 * cnt / total) if total else 0
        print(f"  {area}: {cnt} ({pct}%)")


if __name__ == "__main__":
    main()
