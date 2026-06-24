#!/usr/bin/env python3
"""
Mississippi State University course catalog scraper.
URL hierarchy: catalog.msstate.edu/undergraduate/collegesanddegreeprograms/{college}/{dept}/
HTML: div.courseblock > p.courseblocktitle > em > strong "HI 1003  History Title:  3 hours."
      + p.courseblockdesc
Also: catalog.msstate.edu/graduate/collegesandprograms/{college}/{dept}/
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "msstate"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.msstate.edu"
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

STEM = {"abe", "an", "bchs", "biol", "che", "chem", "cme", "cpe", "cs", "ece",
        "en", "ent", "ep", "erp", "for", "ge", "geo", "gphy", "ie", "me",
        "mse", "nse", "pe", "ph", "plp", "pss", "sta", "sts", "wfa"}
HUMANITIES = {"aas", "cl", "com", "eld", "en", "enl", "fllc", "for", "fr", "ge",
              "gr", "hi", "la", "mus", "phi", "sp", "thea"}
SOCIAL = {"aas", "ant", "com", "crim", "econ", "edf", "edl", "epsy", "geog",
          "gss", "hrm", "lss", "pol", "psy", "soc", "sw"}
MEDICAL = {"au", "biol", "cvm", "hlh", "kine", "nfs", "nur", "pt", "res", "vms"}
PROFESSIONAL = {"acc", "ba", "bu", "fin", "hr", "ib", "lbs", "mgt", "mkt",
                "nfm", "pub", "re"}


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
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:4])
        return "graduate" if n >= 6000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_dept_links(session, college_url):
    """Get list of department page links from a college page."""
    try:
        r = session.get(BASE_URL + college_url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Dept links are one level deeper than college_url
            if href.startswith(college_url) and href != college_url:
                # Ensure exactly one more level
                remainder = href[len(college_url):]
                if remainder and "/" not in remainder.rstrip("/"):
                    links.append(href)
        return list(dict.fromkeys(links))
    except Exception as e:
        print(f"  ERROR fetching college {college_url}: {e}")
        return []


def parse_dept_page(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        title_p = block.find("p", class_="courseblocktitle")
        if not title_p:
            continue
        # The strong might be inside em
        strong = title_p.find("strong")
        if not strong:
            continue
        title_text = strong.get_text(" ", strip=True)
        # Format: "HI 1003  History of Science in Six Ideas:  3 hours."
        # or: "ACCY 6113  Financial Reporting:  3 hours."
        m = re.match(r"([A-Z][A-Z0-9]*)\s+([\d][\w]*)\s+(.+?):\s+[\d.]+ hours?\.?", title_text)
        if not m:
            # Try without hours
            m = re.match(r"([A-Z][A-Z0-9]*)\s+([\d][\w]*)\s+(.+)", title_text)
            if not m:
                continue
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = m.group(3).strip().rstrip(":")

        desc_p = block.find("p", class_="courseblockdesc")
        desc = desc_p.get_text(" ", strip=True) if desc_p else ""

        courses.append((dept, num, title, desc))
    return courses


def get_all_dept_links(session):
    """Crawl colleges and gather all department page links."""
    all_dept_links = []

    for catalog_section in ["/undergraduate/collegesanddegreeprograms/", "/graduate/collegesandprograms/"]:
        try:
            r = session.get(BASE_URL + catalog_section, timeout=25)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            college_pattern = re.compile(rf"^{re.escape(catalog_section)}[^/]+/$")
            college_links = [a["href"] for a in soup.find_all("a", href=True)
                             if college_pattern.match(a.get("href", ""))]
            college_links = list(dict.fromkeys(college_links))
            print(f"  Found {len(college_links)} colleges in {catalog_section}")

            for college_url in college_links:
                dept_links = get_dept_links(session, college_url)
                all_dept_links.extend(dept_links)
                time.sleep(0.2)
        except Exception as e:
            print(f"  ERROR fetching catalog section {catalog_section}: {e}")

    return list(dict.fromkeys(all_dept_links))


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== Mississippi State University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    print("Discovering department pages...")
    dept_links = get_all_dept_links(session)
    print(f"Found {len(dept_links)} department pages")

    for dept_url in dept_links:
        url = BASE_URL + dept_url
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                failed.append(dept_url)
                continue
            parsed = parse_dept_page(r.text)
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
                print(f"  {dept_url.split('/')[-2]}: {new} courses")
        except Exception as e:
            print(f"  ERROR {dept_url}: {e}")
            failed.append(dept_url)
        time.sleep(0.2)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:10])}")

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
        "by_area": area_counts, "failed_depts": failed,
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
