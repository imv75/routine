#!/usr/bin/env python3
"""
UCSD Course Catalog Scraper.
Source: catalog.ucsd.edu/courses/{DEPT}.html
Format: p.course-name "DEPT NUM. Title (Credits)" + p.course-descriptions
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

STEM_DEPTS = {
    "aip", "astr", "bioi", "biol", "biom", "ceng", "chem", "cogs",
    "cse", "dse", "ece", "envr", "mae", "math", "mse", "nano",
    "neng", "phys", "se", "siob", "sio", "stao", "sts",
}
HUMANITIES_DEPTS = {
    "aasm", "awp", "chin", "clas", "clit", "comm", "ethn", "fren",
    "glbh", "hila", "hisc", "hius", "humn", "ital", "japn", "jwsp",
    "ling", "ltcs", "ltko", "ltsp", "ltwr", "musc", "phil", "port",
    "reli", "rus", "span", "thea", "warr",
}
SOCIAL_DEPTS = {
    "aapi", "anth", "cogr", "econ", "geog", "glps", "poli", "psyc",
    "soci", "us",
}
MEDICAL_DEPTS = {
    "fmph", "meds", "anes", "derm", "emed", "famp", "gnto", "imed",
    "nuro", "orth", "path", "peds", "phar", "psct", "rady", "repr",
    "surg", "urol",
}
PROFESSIONAL_DEPTS = {
    "bus", "econ", "esys", "gppa", "hds", "hrma", "irgn", "law",
    "mgt", "mgtf", "mgts", "mba", "msba", "mseg", "nlp", "plan",
    "ppha", "pppa", "pub", "pubh", "spps", "wri",
}


def classify_dept(dept):
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
        n = int(re.sub(r"[^0-9]", "", str(num))[:5])
        return "graduate" if n >= 200 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def get_dept_list():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    r = s.get("https://catalog.ucsd.edu/front/courses.html", timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    depts = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "/courses/" in href and href.endswith(".html"):
            m = re.search(r"/courses/([A-Z0-9]+)\.html$", href)
            if m:
                depts.append(m.group(1))
    return list(dict.fromkeys(depts))


def scrape_dept(dept):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    url = f"https://catalog.ucsd.edu/courses/{dept}.html"
    try:
        r = s.get(url, timeout=20)
        if r.status_code != 200:
            return dept, [], f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")

        courses = []
        all_p = soup.find_all("p", class_=["course-name", "course-descriptions"])

        current = None
        for p in all_p:
            cls = p.get("class", [])
            if "course-name" in cls:
                if current:
                    courses.append(current)
                name_text = p.get_text(" ", strip=True)
                # Format: "DEPT NUM. Title (Credits)" or "DEPT NUM. Title"
                m = re.match(
                    r"^([A-Z][A-Z0-9/]+)\s+([\d]+[A-Z]?)\.\s+(.+?)\s*\([\d\-]+\)\s*$",
                    name_text,
                )
                if not m:
                    m = re.match(
                        r"^([A-Z][A-Z0-9/]+)\s+([\d]+[A-Z]?)\.\s+(.+)$",
                        name_text,
                    )
                if not m:
                    current = None
                    continue
                dept_code = m.group(1).strip()
                num = m.group(2).strip()
                title = m.group(3).strip()
                title = re.sub(r"\s*\([\d\-]+\)\s*$", "", title).strip()
                current = {
                    "dept_code": dept_code,
                    "num": num,
                    "title": title,
                    "desc": "",
                }
            elif "course-descriptions" in cls and current:
                current["desc"] = p.get_text(" ", strip=True)

        if current:
            courses.append(current)

        results = []
        for c in courses:
            full_text = f"{c['title']} {c['desc']}"
            area = classify_dept(c["dept_code"])
            level = classify_level(c["num"])
            results.append({
                "university": "ucsd",
                "academic_year": "2026",
                "academic_year_label": "2026-2027",
                "department_code": c["dept_code"],
                "course_number": c["num"],
                "title": c["title"],
                "description": c["desc"],
                "broad_area": area,
                "level": level,
                "progressive_signal": check_keywords(full_text, PROGRESSIVE_KEYWORDS),
                "western_canon_signal": check_keywords(full_text, WESTERN_CANON_KEYWORDS),
                "climate_narrow_signal": check_keywords(full_text, CLIMATE_NARROW_KEYWORDS),
                "climate_broad_signal": check_keywords(full_text, CLIMATE_BROAD_KEYWORDS),
                "cross_listed": False,
                "deduplicated": True,
            })
        return dept, results, None
    except Exception as e:
        return dept, [], str(e)


def scrape_ucsd():
    output_dir = "/home/user/routine/data/ucsd"
    os.makedirs(output_dir, exist_ok=True)

    print("=== UCSD Course Catalog Scraper ===")
    print("Fetching department list...")
    depts = get_dept_list()
    print(f"Found {len(depts)} departments")

    all_courses = []
    seen = set()
    failed = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(scrape_dept, d): d for d in depts}
        for fut in as_completed(futures):
            dept, courses, err = fut.result()
            if err:
                print(f"  FAIL {dept}: {err}")
                failed.append(dept)
            else:
                new = 0
                for c in courses:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
                if new:
                    print(f"  {dept}: {new} courses")
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

    print(f"\n=== UCSD Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({round(100*prog/total,2)}%) | Canon: {canon} ({round(100*canon/total,2)}%)")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed)}")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({round(100*cnt/total)}%)")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/ucsd_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    summary = {
        "university": "ucsd",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "catalog.ucsd.edu/courses/{DEPT}.html",
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
    summary_path = f"{output_dir}/ucsd_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_ucsd()
