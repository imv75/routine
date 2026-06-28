#!/usr/bin/env python3
"""
Baylor University Course Catalog Scraper.
catalog.baylor.edu/undergraduate/courses-instruction/{dept}/ and
catalog.baylor.edu/graduate-school/courses-instruction/{dept}/
CourseleafCMS format with span.detail-code / div.courseblockextra.
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

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

STEM_CODES = {
    "bio", "chm", "csc", "cis", "ece", "egr", "env", "geo", "mth",
    "phy", "sta", "che", "cps", "bch", "bme", "ceg", "ene", "gnc",
    "ids", "mec", "neuro", "nsc", "biol", "chem", "math", "phys",
    "stat", "cs", "engr", "ee", "ce", "me", "ae", "ibe", "mgt",
}
HUM_CODES = {
    "art", "arth", "cla", "dh", "enc", "eng", "fre", "ger", "grk",
    "heb", "his", "ita", "lat", "mus", "phi", "rel", "rlg", "rli",
    "rus", "spa", "thf", "wlt", "arb", "ara", "ara", "chn", "jpn",
    "kor", "mll", "por", "sla", "lin", "fst", "mdv",
}
SOC_CODES = {
    "anth", "ast", "com", "eco", "edu", "fin", "geog", "jou", "mkt",
    "pol", "psy", "soc", "swk", "adv", "bus", "gst", "wom", "afr",
    "ams", "lns", "lhp", "sis", "hon", "glb",
}
MED_CODES = {
    "atr", "kin", "nrs", "nut", "fcs", "fam", "mph", "pre",
}
PROF_CODES = {
    "acc", "ba", "blaw", "fns", "ins", "mgmt", "mis", "mba", "ent",
    "lbs", "law", "edl", "cur", "eed", "sped", "ci", "hre",
}


def classify_area(dept):
    d = dept.lower().strip()
    if d in STEM_CODES:
        return "STEM"
    if d in HUM_CODES:
        return "Humanities"
    if d in SOC_CODES:
        return "Social Sciences"
    if d in MED_CODES:
        return "Medical Sciences"
    if d in PROF_CODES:
        return "Professional"
    return "Other"


def classify_level(code):
    nums = re.findall(r'\d+', code)
    if nums:
        try:
            n = int(nums[0])
            return "graduate" if n >= 5000 else "undergraduate"
        except Exception:
            pass
    return "undergraduate"


def check_keywords(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def parse_courseblock(block, university, year, label):
    code_span = block.find("span", class_="detail-code")
    title_span = block.find("span", class_="detail-title")
    if not code_span or not title_span:
        return None
    raw_code = code_span.get_text(strip=True)
    title = title_span.get_text(strip=True)
    # raw_code like "ACC 2303" or "ACC2303"
    m = re.match(r"([A-Z][A-Z0-9_&]*)\s*([\w]+)", raw_code)
    if not m:
        return None
    dept = m.group(1)
    num = m.group(2)

    # Description in div.courseblockextra
    desc_div = block.find("div", class_="courseblockextra")
    desc = desc_div.get_text(" ", strip=True) if desc_div else ""
    # Remove prereq prefix
    desc = re.sub(r"^(Pre-?requisite|Prerequisite)[^.]*\.\s*", "", desc, flags=re.IGNORECASE)

    full = f"{title} {desc}"
    return {
        "university": university,
        "academic_year": year,
        "academic_year_label": label,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept),
        "level": classify_level(raw_code),
        "progressive_signal": int(check_keywords(full, PROGRESSIVE_KEYWORDS)),
        "western_canon_signal": int(check_keywords(full, WESTERN_CANON_KEYWORDS)),
        "climate_narrow_signal": int(check_keywords(full, CLIMATE_NARROW_KEYWORDS)),
        "climate_broad_signal": int(check_keywords(full, CLIMATE_BROAD_KEYWORDS)),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_dept(session, url, university, year, label):
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return [], url
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for b in blocks:
            c = parse_courseblock(b, university, year, label)
            if c:
                courses.append(c)
        return courses, None
    except Exception as e:
        return [], url


def scrape_baylor():
    university = "baylor"
    year = "2026"
    label = "2026-2027"
    base = "https://catalog.baylor.edu"
    output_dir = "/home/user/routine/data/baylor"
    os.makedirs(output_dir, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"

    print("=== Baylor University Course Catalog Scraper ===")
    print("Fetching catalog homepage to discover department links...")

    r = session.get(f"{base}/", timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    # Collect all dept URLs
    dept_urls = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/courses-instruction/" in href and href.count("/") >= 4:
            if not href.startswith("http"):
                href = base + href
            dept_urls.add(href)

    dept_urls = sorted(dept_urls)
    print(f"Found {len(dept_urls)} department URLs")

    all_courses = []
    seen = set()
    failed = []

    def fetch(url):
        courses, err = scrape_dept(session, url, university, year, label)
        return url, courses, err

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, url): url for url in dept_urls}
        for i, fut in enumerate(as_completed(futures), 1):
            url, courses, err = fut.result()
            dept_slug = url.rstrip("/").split("/")[-1].upper()
            if err:
                print(f"  [{i}/{len(dept_urls)}] FAIL {dept_slug}: {err}")
                failed.append(url)
            else:
                new = 0
                for c in courses:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
                if new:
                    print(f"  [{i}/{len(dept_urls)}] {dept_slug}: {new} courses")

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {[u.split('/')[-2] for u in failed[:20]]}")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/baylor_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
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
        "university": university,
        "academic_year": year,
        "academic_year_label": label,
        "source": "catalog.baylor.edu/undergraduate/courses-instruction/ + /graduate-school/",
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
    with open(f"{output_dir}/baylor_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn} ({summary['climate_narrow_pct']}%) | Climate broad: {cb} ({summary['climate_broad_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")
    return summary


if __name__ == "__main__":
    scrape_baylor()
