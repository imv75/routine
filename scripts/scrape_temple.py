#!/usr/bin/env python3
"""
Temple University course catalog scraper.
URL: bulletin.temple.edu/courses/{dept}/
HTML: div.courseblock > p.courseblocktitle "DEPT NUM.  Title.  N  Credit Hours."
      + div.courseblockdesc > div.courseblockheaddiv (description)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSITY = "temple"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://bulletin.temple.edu"
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
    "biol", "bioc", "bme", "chem", "cis", "ece", "ees", "engr", "envs",
    "geog", "geol", "math", "me", "mse", "phy", "stat", "acms", "anat",
    "ast", "bche", "bioe", "cee", "che", "csc", "ece", "ees", "engi",
    "geog", "msci", "nbs",
}
HUMANITIES_PREFIXES = {
    "amst", "arbc", "arch", "art", "arh", "clas", "comm", "danc", "engl",
    "film", "fren", "ger", "grek", "hist", "hum", "ital", "japn", "kore",
    "latn", "ling", "mhis", "mth", "musc", "mus", "phil", "port", "rel",
    "russ", "span", "tha", "thea", "writ",
}
SOCIAL_PREFIXES = {
    "aaas", "afam", "anth", "crj", "econ", "geog", "glst", "lgst", "pols",
    "psyc", "soc", "sowk", "wgss", "urbs",
}
MEDICAL_PREFIXES = {
    "anes", "dent", "epid", "kin", "md", "nrs", "ot", "pa", "pt", "phya",
    "phyb", "pha", "pth", "pub", "sph",
}
PROFESSIONAL_PREFIXES = {
    "acct", "adv", "bus", "fin", "hrm", "law", "mgmt", "mgt", "mktg",
    "real", "rjc", "sba", "soc", "tmgt",
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
        return "graduate" if n >= 5000 else "undergraduate"
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
        "Referer": f"{BASE_URL}/courses/",
    })
    try:
        s.get(f"{BASE_URL}/", timeout=15)
    except Exception:
        pass
    return s


def get_dept_slugs(session):
    url = f"{BASE_URL}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            print(f"  ERROR: dept listing returned {r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        slugs = []
        for a in soup.find_all("a", href=True):
            m = re.match(r"^/courses/([a-z][a-z0-9]*)/?$", a["href"])
            if m:
                slugs.append(m.group(1))
        return list(dict.fromkeys(slugs))
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def parse_dept_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        title_el = block.find("p", class_="courseblocktitle")
        if not title_el:
            continue
        title_text = title_el.get_text(" ", strip=True)
        # Format: "DEPT NUM.  Title.  N   Credit Hours."
        m = re.match(r"([A-Z][A-Z0-9]*)\s+(\w+)\.\s+(.+)", title_text)
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = m.group(3).strip()
        # Strip trailing "N Credit Hours." and trailing period
        title = re.sub(r"\s+\d+(?:\.\d+)?\s+Credit Hours?\.?\s*$", "", title, flags=re.IGNORECASE).strip()
        title = title.rstrip(".")

        desc = ""
        # Description in div.courseblockdesc > div.courseblockheaddiv or direct text
        desc_el = block.find("div", class_="courseblockdesc")
        if desc_el:
            head = desc_el.find("div", class_="courseblockheaddiv")
            if head:
                raw = head.get_text(" ", strip=True)
            else:
                raw = desc_el.get_text(" ", strip=True)
            if len(raw) > 10:
                desc = raw

        if not title:
            continue
        courses.append((dept, num, title, desc))
    return courses


def scrape_dept(slug):
    s = make_session()
    url = f"{BASE_URL}/courses/{slug}/"
    try:
        r = s.get(url, timeout=25)
        if r.status_code != 200:
            return slug, [], True
        parsed = parse_dept_page(r.text)
        return slug, parsed, (len(parsed) == 0)
    except Exception as e:
        print(f"  ERROR {slug}: {e}")
        return slug, [], True


def main():
    session = make_session()
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Temple University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    slugs = get_dept_slugs(session)
    print(f"Found {len(slugs)} departments. Scraping...")

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(scrape_dept, slug): slug for slug in slugs}
        for future in as_completed(futures):
            slug, parsed, had_error = future.result()
            if had_error:
                failed.append(slug)
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
                print(f"  {slug.upper()}: {new} courses")

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
