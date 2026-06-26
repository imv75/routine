#!/usr/bin/env python3
"""
UIUC time-series scraper using the CIS REST API.
Source: courses.illinois.edu/cisapp/explorer/schedule/{year}/fall/{SUBJ}.xml
Gives offered courses per fall semester with full descriptions.
Available years: 2020–2025 (Fall roster).
"""

import csv, json, os, re, time
import requests
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

VERIFY = "/root/.ccr/ca-bundle.crt"
BASE = "https://courses.illinois.edu/cisapp/explorer"
OUTPUT_DIR = "/home/user/routine/data/uiuc"

PROGRESSIVE_KEYWORDS = [
    "diversity","diverse","inclusion","inclusive","belonging","dei","race","racial","racism",
    "racist","anti-racist","antiracist","racialized","white supremacy","white privilege","whiteness",
    "bipoc","people of color","black lives","critical race","gender","gendered","feminist","feminism",
    "sexism","patriarchy","misogyny","queer","lgbtq","transgender","nonbinary","intersex","sexuality",
    "heteronormativity","equity","equitable","social justice","injustice","oppression","oppressive",
    "liberation","decolonize","decolonial","colonialism","colonial","postcolonial","settler colonialism",
    "identity","identities","positionality","intersectionality","privilege","marginalized",
    "marginalization","underrepresented","allyship","indigenous","native american","latinx","chicano",
    "chicana","diaspora","reparations","microaggression","implicit bias","systemic racism",
]
WESTERN_CANON_KEYWORDS = [
    "western civilization","western tradition","western thought","great books","liberal arts tradition",
    "ancient greece","ancient rome","greek philosophy","roman law","classical antiquity","greco-roman",
    "renaissance","enlightenment","medieval philosophy","reformation","shakespeare","plato","aristotle",
    "homer","dante","virgil","milton","cicero","socrates","augustine","aquinas","machiavelli","hobbes",
    "descartes","kant","hegel","locke","tocqueville","montesquieu","bible","biblical","iliad","odyssey",
    "aeneid","divine comedy","canterbury tales","leviathan","federalist","classics","classical",
]
CLIMATE_NARROW = [
    "climate change","global warming","greenhouse gas","carbon emission","fossil fuel","sea level rise","climate crisis",
]
CLIMATE_BROAD = [
    "climate","sustainability","sustainable","renewable energy","environmental justice","carbon",
    "decarbonization","net zero","clean energy","green energy","ecological","ecosystem","biodiversity",
]

FIELDS = [
    "university","academic_year","academic_year_label","department_code","course_number",
    "title","description","broad_area","level","progressive_signal","western_canon_signal",
    "climate_narrow_signal","climate_broad_signal","cross_listed","deduplicated",
]


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def classify_level(num_str):
    m = re.search(r'\d+', num_str or '')
    if not m:
        return "undergraduate"
    n = int(m.group())
    return "graduate" if n >= 500 else "undergraduate"


def get_subjects(year):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    r = s.get(f"{BASE}/schedule/{year}/fall.xml", timeout=20, verify=VERIFY)
    if r.status_code != 200:
        return []
    root = ET.fromstring(r.text)
    return [e.get("id") for e in root.findall(".//subject") if e.get("id")]


def scrape_subject(year, subj):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    url = f"{BASE}/schedule/{year}/fall/{subj}.xml"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return subj, [], f"HTTP {r.status_code}"
        root = ET.fromstring(r.text)
        courses = []
        seen = set()
        for course in root.findall(".//course"):
            num = course.get("id", "")
            href = course.get("href", "")
            # fetch course detail for description
            if not href:
                continue
            try:
                rd = s.get(href, timeout=15, verify=VERIFY)
                if rd.status_code != 200:
                    continue
                detail = ET.fromstring(rd.text)
                title = detail.findtext(".//label") or detail.findtext(".//title") or ""
                desc = detail.findtext(".//description") or ""
                title = title.strip()
                desc = desc.strip()
            except Exception:
                title = course.findtext(".//label") or ""
                desc = ""

            if not title:
                continue

            key = (subj, num, title)
            if key in seen:
                continue
            seen.add(key)

            full = f"{title} {desc}"
            courses.append({
                "dept": subj,
                "num": str(num),
                "title": title,
                "desc": desc,
                "prog": check_kw(full, PROGRESSIVE_KEYWORDS),
                "canon": check_kw(full, WESTERN_CANON_KEYWORDS),
                "cn": check_kw(full, CLIMATE_NARROW),
                "cb": check_kw(full, CLIMATE_BROAD),
                "level": classify_level(str(num)),
            })
            time.sleep(0.03)
        return subj, courses, None
    except Exception as e:
        return subj, [], str(e)


def scrape_year(year):
    label = f"{year}-{year+1}"
    print(f"  Scraping UIUC Fall {year}...")
    subjects = get_subjects(year)
    print(f"    {len(subjects)} subjects")

    all_courses = []
    seen_global = set()
    failed = []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(scrape_subject, year, subj): subj for subj in subjects}
        for fut in as_completed(futs):
            subj, courses, err = fut.result()
            if err:
                failed.append(subj)
            else:
                for c in courses:
                    key = (c["dept"], c["num"], c["title"])
                    if key not in seen_global:
                        seen_global.add(key)
                        all_courses.append(c)
            time.sleep(0.02)

    total = len(all_courses)
    if total == 0:
        return None

    prog_n  = sum(1 for c in all_courses if c["prog"])
    canon_n = sum(1 for c in all_courses if c["canon"])
    cn_n    = sum(1 for c in all_courses if c["cn"])
    cb_n    = sum(1 for c in all_courses if c["cb"])

    prog_pct  = round(100 * prog_n / total, 2)
    canon_pct = round(100 * canon_n / total, 2)
    cn_pct    = round(100 * cn_n / total, 2)
    cb_pct    = round(100 * cb_n / total, 2)

    print(f"    {total} courses | prog {prog_pct}% | canon {canon_pct}%")
    if failed:
        print(f"    Failed: {failed[:10]}")

    # Write CSV
    rows = []
    for c in all_courses:
        rows.append({
            "university": "uiuc",
            "academic_year": str(year),
            "academic_year_label": label,
            "department_code": c["dept"],
            "course_number": c["num"],
            "title": c["title"],
            "description": c["desc"],
            "broad_area": "Other",
            "level": c["level"],
            "progressive_signal": c["prog"],
            "western_canon_signal": c["canon"],
            "climate_narrow_signal": c["cn"],
            "climate_broad_signal": c["cb"],
            "cross_listed": False,
            "deduplicated": True,
        })

    csv_path = f"{OUTPUT_DIR}/uiuc_{year}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    return {
        "academic_year": str(year),
        "academic_year_label": label,
        "total_courses": total,
        "progressive_pct": prog_pct,
        "canon_pct": canon_pct,
        "climate_narrow_pct": cn_pct,
        "climate_broad_pct": cb_pct,
        "failed_subjects": failed,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=== UIUC Time Series (CIS REST API) ===")

    YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
    per_year = []

    for year in YEARS:
        result = scrape_year(year)
        if result:
            per_year.append(result)

    ts = {
        "university": "uiuc",
        "source": "courses.illinois.edu/cisapp/explorer (Fall roster per year)",
        "years": per_year,
    }
    ts_path = f"{OUTPUT_DIR}/uiuc_timeseries.json"
    with open(ts_path, "w") as f:
        json.dump(ts, f, indent=2)

    print(f"\nSaved timeseries to {ts_path}")
    print("\nSummary:")
    for y in per_year:
        print(f"  {y['academic_year_label']}: {y['total_courses']:,} courses, "
              f"prog={y['progressive_pct']}%, canon={y['canon_pct']}%")


if __name__ == "__main__":
    main()
