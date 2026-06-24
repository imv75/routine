#!/usr/bin/env python3
"""
Dartmouth College course catalog scraper.
Uses SmartCatalogIQ — one page per course.
JSON nav: dartmouth.smartcatalogiq.com/Institutions/Dartmouth/json/current/orc-local.json
Course URL: /en/current/orc/departments-programs-{undergrad|graduate}/{dept}/{prefix}/{course}/
Content in: div#main
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

UNIVERSITY = "dartmouth"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://dartmouth.smartcatalogiq.com"
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
CLIMATE_NARROW = ["climate change", "global warming", "greenhouse gas", "carbon emission",
                   "fossil fuel", "sea level rise", "climate crisis"]
CLIMATE_BROAD = ["climate", "sustainability", "sustainable", "renewable energy",
                  "environmental justice", "carbon", "decarbonization", "net zero",
                  "clean energy", "green energy", "ecological", "ecosystem", "biodiversity"]

STEM = {"aaas", "astr", "biol", "chem", "cosc", "cogs", "ear", "engg", "envs",
        "isc", "math", "nrsc", "pbpl", "phys", "psyc", "qbs", "qss", "stat"}
HUMANITIES = {"aaas", "afst", "ames", "arab", "arth", "chin", "clas", "coco",
              "comp", "danc", "engl", "film", "fren", "germ", "gk", "hebr",
              "hist", "ital", "japn", "jwst", "kor", "latn", "ling", "musi",
              "phil", "port", "rel", "russ", "span", "thea", "writ"}
SOCIAL = {"afst", "ames", "anth", "econ", "educ", "geog", "govt", "hist",
          "lacs", "pbpl", "pols", "psyc", "soan", "socy", "wgss"}
MEDICAL = {"biol", "hmsc", "hlth", "nrsc", "nurs", "phys"}
PROFESSIONAL = {"engm", "tuck"}


def classify_area(dept):
    d = dept.lower()
    if d in STEM:
        return "STEM"
    if d in HUMANITIES:
        return "Humanities"
    if d in SOCIAL:
        return "Social Sciences"
    if d in MEDICAL:
        return "Medical Sciences"
    if d in PROFESSIONAL:
        return "Professional"
    return "Other"


def classify_level(num):
    # Dartmouth uses 1-99 for undergrad, 100+ for grad
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:3])
        return "graduate" if n >= 100 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_all_course_paths(session):
    """Fetch the JSON nav file and extract all course leaf paths."""
    url = f"{BASE_URL}/Institutions/Dartmouth/json/current/orc-local.json"
    try:
        r = session.get(url, timeout=30)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception as e:
        print(f"  ERROR fetching nav JSON: {e}")
        return []

    courses = []

    def traverse(node):
        path = node.get("Path", "")
        name = node.get("Name", "")
        children = node.get("Children", [])
        # Leaf node with course code pattern
        if not children and re.search(r"[A-Z]+-[\d]", path.split("/")[-1]):
            # Convert sitecore path to web URL path
            # Example: /sitecore/content/Catalogs/Dartmouth-College/current/orc/Departments-Programs-Undergraduate/...
            # → /en/current/orc/departments-programs-undergraduate/...
            parts = path.split("/")
            # Find 'current' in parts
            try:
                idx = parts.index("current")
            except ValueError:
                return
            web_parts = parts[idx:]
            web_url = "/en/" + "/".join(p.lower() for p in web_parts) + "/"
            # Determine level from path
            is_undergrad = "Departments-Programs-Undergraduate" in path
            is_grad = "Departments-Programs-Graduate" in path
            level_section = "undergraduate" if is_undergrad else "graduate"
            courses.append((web_url, name, level_section))
        for child in children:
            traverse(child)

    traverse(data)
    return courses


def fetch_course_page(session, url, name, retries=2):
    """Fetch a single course page and extract title + description."""
    full_url = BASE_URL + url
    for attempt in range(retries + 1):
        try:
            r = session.get(full_url, timeout=20)
            if r.status_code != 200:
                return None
            soup = BeautifulSoup(r.text, "html.parser")
            main = soup.find("div", id="main")
            if not main:
                return None
            text = main.get_text(" ", strip=True)
            # text starts with course code+title then description
            # e.g. "ECON 1The Price System: Analysis...Description text..."
            # Extract code: known from nav JSON name field
            # Parse: "DEPT NUM" from name, rest is title then desc
            # The name from JSON is like "ECON 1" or "AAAS 7"
            m_name = re.match(r"([A-Z][A-Z0-9&/]*)\s+([\w.-]+)", name.strip())
            if not m_name:
                return None
            dept = m_name.group(1).strip().split("/")[0].split("&")[0].strip()
            num = m_name.group(2).strip()

            # Find title and description from page text
            # The main div has: "DEPT NUMTitle TextDescription text"
            prefix = re.escape(name.strip())
            m_content = re.match(rf"{prefix}\s*(.+?)(?:\s*Offered|$)", text, re.DOTALL)
            if m_content:
                content = m_content.group(1).strip()
            else:
                content = text

            # Split title from description - first sentence or up to period
            # Try to find a natural break (description often starts with a capital letter after title)
            # Heuristic: title is first sentence-like chunk, desc is the rest
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", content, maxsplit=1)
            if len(sentences) >= 2:
                title = sentences[0].rstrip(".").strip()
                desc = sentences[1].strip()
            else:
                title = content[:150].strip()
                desc = content[150:].strip()

            return (dept, num, title, desc)
        except Exception as e:
            if attempt < retries:
                time.sleep(1)
            continue
    return None


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Dartmouth College Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    print("Fetching course list from nav JSON...")
    course_paths = get_all_course_paths(session)
    print(f"Found {len(course_paths)} courses to scrape")

    # Scrape concurrently with a thread pool
    MAX_WORKERS = 8
    total_fetched = 0
    batch_size = 100

    for batch_start in range(0, len(course_paths), batch_size):
        batch = course_paths[batch_start:batch_start + batch_size]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(fetch_course_page, session, url, name): (url, name)
                for url, name, level in batch
            }
            for future in as_completed(futures):
                url, name = futures[future]
                try:
                    result = future.result()
                    if result:
                        dept, num, title, desc = result
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
                    else:
                        failed.append(url)
                except Exception as e:
                    failed.append(url)
        total_fetched += len(batch)
        print(f"  Progress: {total_fetched}/{len(course_paths)} ({len(all_courses)} parsed)")
        time.sleep(0.5)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:5]}")

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
        "university": UNIVERSITY, "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL, "total_courses": total,
        "progressive_count": prog, "progressive_pct": round(100*prog/total, 2) if total else 0,
        "canon_count": canon, "canon_pct": round(100*canon/total, 2) if total else 0,
        "climate_narrow_count": cn, "climate_narrow_pct": round(100*cn/total, 2) if total else 0,
        "climate_broad_count": cb, "climate_broad_pct": round(100*cb/total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed[:20],
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {OUTPUT_CSV}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({100*cnt//total if total else 0}%)")


if __name__ == "__main__":
    main()
