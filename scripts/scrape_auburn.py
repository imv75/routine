#!/usr/bin/env python3
"""
Auburn University course catalog scraper.
URL: bulletin.auburn.edu/coursesofinstruction/{dept}/
HTML: div.courseblock > p > strong "DEPT NUM TITLE (CREDITS) " + rest is description
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "auburn"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://bulletin.auburn.edu"
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

HUMANITIES_DEPTS = {
    "anth", "arth", "arts", "clas", "engl", "flch", "flfr", "flgn", "flgr", "fljp",
    "flkn", "flln", "flru", "flsp", "forl", "hist", "humn", "ling", "musc", "phil",
    "reli", "rels", "thea", "wms",
}
SOCIAL_DEPTS = {
    "anth", "comm", "crim", "econ", "geog", "pols", "psyc", "soci", "socl", "sw",
    "wms",
}
STEM_DEPTS = {
    "aero", "agri", "agrn", "aero", "apbt", "batm", "bche", "biol", "biop", "bsen",
    "bssc", "chem", "civl", "comp", "csci", "elec", "engr", "ermc", "fdsc", "fore",
    "geol", "hort", "inds", "math", "mche", "mech", "nuc", "phys", "stat", "wild",
}
MEDICAL_DEPTS = {
    "bsci", "coun", "fdsc", "kine", "nurs", "occp", "phmd", "phth", "pths", "pubh",
    "rha", "rsed",
}
PROFESSIONAL_DEPTS = {
    "acct", "arch", "avmg", "busn", "finc", "hdfs", "hdre", "ibus", "larc", "lawe",
    "ldrs", "mgmt", "mktg", "puba", "scmn",
}


def classify_area(dept):
    d = dept.lower()
    if d in STEM_DEPTS:
        return "STEM"
    if d in HUMANITIES_DEPTS:
        return "Humanities"
    if d in SOCIAL_DEPTS:
        return "Social Sciences"
    if d in MEDICAL_DEPTS:
        return "Medical Sciences"
    if d in PROFESSIONAL_DEPTS:
        return "Professional"
    return "Other"


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:4])
        return "graduate" if n >= 5000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_dept_links(session):
    r = session.get(f"{BASE_URL}/azindex/", timeout=25)
    if r.status_code != 200:
        print(f"  ERROR fetching azindex: {r.status_code}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/coursesofinstruction/") and href != "/coursesofinstruction/":
            if href not in links:
                links.append(href)
    return links


def parse_courses(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        p = block.find("p")
        if not p:
            continue
        strong = p.find("strong")
        if not strong:
            continue
        strong_text = strong.get_text(strip=True)
        # Extract description: text in p after removing strong
        strong.extract()
        desc = p.get_text(" ", strip=True).strip()
        # Strip leading "LEC. N." type prefixes from description
        # Parse strong_text: "DEPT NUM TITLE (N) " or "DEPT NUM TITLE (N-N)"
        # Pattern: WORD NUMBER REST (CREDITS)
        m = re.match(r"^([A-Z]{2,6})\s+(\d{4}[A-Z]?)\s+(.+?)\s*\(\d[\d\.\-]*\)\s*$",
                     strong_text)
        if not m:
            # Fallback: split on whitespace
            parts = strong_text.split()
            if len(parts) < 3:
                continue
            dept = parts[0]
            num = parts[1]
            title = " ".join(parts[2:])
            # Remove trailing (N) if present
            title = re.sub(r"\s*\(\d[\d\.\-]*\)\s*$", "", title).strip()
        else:
            dept = m.group(1)
            num = m.group(2)
            title = m.group(3).strip()
        courses.append((dept, num, title, desc))
    return courses


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Auburn University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    dept_links = get_dept_links(session)
    print(f"Found {len(dept_links)} department links")

    for link in dept_links:
        url = BASE_URL + link
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                print(f"  SKIP {link}: {r.status_code}")
                failed.append(link)
                continue
            parsed = parse_courses(r.text)
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
            print(f"  {link}: {new} courses")
        except Exception as e:
            print(f"  ERROR {link}: {e}")
            failed.append(link)
        time.sleep(0.2)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(f[:50] for f in failed[:10])}")

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
        "progressive_count": prog, "progressive_pct": round(100 * prog / total, 2) if total else 0,
        "canon_count": canon, "canon_pct": round(100 * canon / total, 2) if total else 0,
        "climate_narrow_count": cn, "climate_narrow_pct": round(100 * cn / total, 2) if total else 0,
        "climate_broad_count": cb, "climate_broad_pct": round(100 * cb / total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote {OUTPUT_CSV}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({100 * cnt // total if total else 0}%)")


if __name__ == "__main__":
    main()
