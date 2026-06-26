#!/usr/bin/env python3
"""
Johns Hopkins University Course Catalog Scraper.
Source: e-catalogue.jhu.edu/course-descriptions/{dept}/
Format: div.courseblock > span.detail-code "SCHOOL.DEPT.NUM." + span.detail-title + p.courseblockextra
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

VERIFY = "/root/.ccr/ca-bundle.crt"

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

# JHU school prefixes and their broad areas
SCHOOL_AREA = {
    "AS": None,   # Arts & Sciences — classify by dept num
    "EN": "STEM",
    "PH": "Medical Sciences",  # Public Health
    "MD": "Medical Sciences",
    "NR": "Medical Sciences",  # Nursing
    "ED": "Professional",      # Education
    "BU": "Professional",
    "EP": "Professional",      # Carey Business
    "SA": "Professional",      # SAIS
    "ME": "Professional",
    "DN": "Medical Sciences",  # Dentistry
}

# AS department numbers → broad area
AS_STEM_DEPTS = {
    "020", "030", "040", "080", "110", "173", "250", "270", "280",
    "290", "301", "302", "362", "370", "390",
}
AS_HUMANITIES_DEPTS = {
    "001", "004", "010", "060", "120", "130", "140", "150", "160",
    "191", "200", "210", "211", "212", "213", "214", "215", "216",
    "217", "218", "219", "220", "221", "222", "223", "224", "230",
    "232", "260", "290", "300", "310", "320", "367",
}
AS_SOCIAL_DEPTS = {
    "050", "070", "100", "180", "190", "192", "193", "240",
    "330", "340", "360", "361", "363", "365", "368",
}


def classify_jhu_dept(school, dept_num):
    if school in SCHOOL_AREA and SCHOOL_AREA[school]:
        return SCHOOL_AREA[school]
    if school == "AS":
        if dept_num in AS_STEM_DEPTS:
            return "STEM"
        if dept_num in AS_HUMANITIES_DEPTS:
            return "Humanities"
        if dept_num in AS_SOCIAL_DEPTS:
            return "Social Sciences"
    return "Other"


def classify_level(course_num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[:5])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def get_dept_links():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    r = s.get(
        "https://e-catalogue.jhu.edu/course-descriptions/",
        timeout=20, verify=VERIFY,
    )
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if (
            "/course-descriptions/" in href
            and href != "/course-descriptions/"
            and not href.endswith(".pdf")
        ):
            # relative → absolute
            if href.startswith("/"):
                href = "https://e-catalogue.jhu.edu" + href
            links.append(href)
    return list(dict.fromkeys(links))


def scrape_dept(url):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return url, [], f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for block in blocks:
            code_el = block.find("span", class_="detail-code")
            title_el = block.find("span", class_="detail-title")
            if not code_el or not title_el:
                continue
            code_raw = code_el.get_text(strip=True).rstrip(".")
            # Format: SCHOOL.DEPT_NUM.COURSE_NUM  e.g. "AS.150.112"
            parts = code_raw.split(".")
            if len(parts) < 3:
                continue
            school = parts[0]
            dept_num = parts[1]
            course_num = parts[2]
            dept_code = f"{school}.{dept_num}"

            title = title_el.get_text(strip=True).rstrip(".")

            # First courseblockextra is description; others are metadata
            extras = block.find_all("p", class_="courseblockextra")
            desc = extras[0].get_text(" ", strip=True) if extras else ""

            full_text = f"{title} {desc}"
            area = classify_jhu_dept(school, dept_num)
            level = classify_level(course_num)

            courses.append({
                "university": "jhu",
                "academic_year": "2026",
                "academic_year_label": "2026-2027",
                "department_code": dept_code,
                "course_number": course_num,
                "title": title,
                "description": desc,
                "broad_area": area,
                "level": level,
                "progressive_signal": check_keywords(full_text, PROGRESSIVE_KEYWORDS),
                "western_canon_signal": check_keywords(full_text, WESTERN_CANON_KEYWORDS),
                "climate_narrow_signal": check_keywords(full_text, CLIMATE_NARROW_KEYWORDS),
                "climate_broad_signal": check_keywords(full_text, CLIMATE_BROAD_KEYWORDS),
                "cross_listed": False,
                "deduplicated": True,
            })
        return url, courses, None
    except Exception as e:
        return url, [], str(e)


def scrape_jhu():
    output_dir = "/home/user/routine/data/jhu"
    os.makedirs(output_dir, exist_ok=True)

    print("=== JHU Course Catalog Scraper ===")
    print("Fetching department list...")
    dept_links = get_dept_links()
    print(f"Found {len(dept_links)} department URLs")

    all_courses = []
    seen = set()
    failed = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(scrape_dept, url): url for url in dept_links}
        for fut in as_completed(futures):
            url, courses, err = fut.result()
            dept_name = url.rstrip("/").split("/")[-1]
            if err:
                print(f"  FAIL {dept_name}: {err}")
                failed.append(dept_name)
            else:
                new = 0
                for c in courses:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
                if new:
                    print(f"  {dept_name}: {new} courses")
            time.sleep(0.05)

    total = len(all_courses)
    if total == 0:
        print("No courses collected!")
        return {}

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    print(f"\n=== JHU Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({round(100*prog/total,2)}%) | Canon: {canon} ({round(100*canon/total,2)}%)")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({round(100*cnt/total)}%)")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/jhu_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    summary = {
        "university": "jhu",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "e-catalogue.jhu.edu/course-descriptions/{dept}/",
        "total_courses": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2),
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2),
        "climate_narrow_count": cn,
        "climate_narrow_pct": round(100 * cn / total, 2),
        "climate_broad_count": cb,
        "climate_broad_pct": round(100 * cb / total, 2),
        "by_area": area_counts,
        "failed_depts": failed,
    }
    summary_path = f"{output_dir}/jhu_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_jhu()
