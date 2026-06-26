#!/usr/bin/env python3
"""
Washington University in St. Louis Course Catalog Scraper.
Source: bulletin.wustl.edu (CourseleafCMS)
Format: div.courseblock > p.courseblocktitle strong "DEPT NNNN Title" + p.courseblockdesc
Graduate level: course number >= 5000
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
BASE_URL = "https://bulletin.wustl.edu"

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

DEPT_AREA = {
    # Engineering
    "bme": "STEM", "biol": "STEM", "cse": "STEM", "chem": "STEM",
    "ece": "STEM", "eece": "STEM", "ese": "STEM", "math": "STEM",
    "phys": "STEM", "stat": "STEM", "wase": "STEM", "mems": "STEM",
    "eece": "STEM", "cs": "STEM", "cse": "STEM",
    # Arts & Sciences humanities
    "anthro": "Social Sciences", "afas": "Social Sciences", "ams": "Social Sciences",
    "econ": "Social Sciences", "educ": "Professional", "glst": "Social Sciences",
    "lals": "Social Sciences", "polsc": "Social Sciences", "psych": "Social Sciences",
    "soci": "Social Sciences", "comms": "Social Sciences",
    # Humanities
    "arth": "Humanities", "cl": "Humanities", "clit": "Humanities",
    "eal": "Humanities", "engl": "Humanities", "film": "Humanities",
    "hist": "Humanities", "ling": "Humanities", "musi": "Humanities",
    "perf": "Humanities", "phil": "Humanities", "rlst": "Humanities",
    "rlpa": "Humanities", "rll": "Humanities", "russ": "Humanities",
    "wgss": "Humanities", "jimes": "Humanities",
    # STEM
    "eeps": "STEM", "envs": "STEM", "pnp": "STEM", "pbs": "STEM",
    "appliedling": "Humanities",
    # Architecture/Art
    "arch": "Humanities", "art": "Humanities",
    # Business
    "acct": "Professional", "fin": "Professional", "mktg": "Professional",
    "mgmt": "Professional", "ibus": "Professional", "info": "Professional",
    "bus": "Professional", "olin": "Professional",
    # Medical/Health
    "phs": "Medical Sciences", "speech": "Medical Sciences",
    # Law
    "law": "Professional",
}

PATH_AREA = {
    "architecture": "Humanities",
    "art": "Humanities",
    "business": "Professional",
    "engineering": "STEM",
    "caps": "Professional",
}

UNDERGRAD_SCHOOLS = [
    "/undergrad/architecture/",
    "/undergrad/art/",
    "/undergrad/business/",
]
GRAD_SCHOOLS = [
    "/grad/architecture/",
    "/grad/art/",
    "/grad/business/",
]


def classify_dept(dept_code, path=""):
    d = dept_code.lower()
    if d in DEPT_AREA:
        return DEPT_AREA[d]
    for part in path.split("/"):
        if part in PATH_AREA:
            return PATH_AREA[part]
    return "Other"


def classify_level(course_num):
    digits = re.sub(r"[^0-9]", "", str(course_num))
    if not digits:
        return "undergraduate"
    return "graduate" if int(digits[0]) >= 5 else "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def get_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    return s


def get_dept_paths():
    s = get_session()
    paths = set()

    seed_pages = [
        "/undergrad/artsci/fields/",
        "/grad/artsci/fields/",
        "/grad/engineering/fields/",
        "/undergrad/engineering/fields/",
    ]

    for page in seed_pages:
        try:
            r = s.get(f"{BASE_URL}{page}", timeout=15, verify=VERIFY)
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                h = a["href"]
                if (
                    h.startswith("/")
                    and "." not in h.split("/")[-1].split("?")[0]
                    and len(h.rstrip("/").split("/")) >= 3
                    and not any(
                        x in h for x in [
                            "fields/", "majors/", "minors/", "honors/",
                            "administration/", "policies/", "requirements/",
                            "degrees/", "doctorates/", "masters/", "phd/",
                            "admissions/", "caps/", "summer/", "visiting/",
                            "additional/", "pre-college/", "beyondboundaries/",
                            "cross-school", "interdisciplinary", "graduate-study",
                            "azindex", "#",
                        ]
                    )
                ):
                    paths.add(h.rstrip("/") + "/")
        except Exception as e:
            print(f"  WARN get_dept_paths {page}: {e}")

    # Add top-level school pages directly
    for p in UNDERGRAD_SCHOOLS + GRAD_SCHOOLS:
        paths.add(p)

    return sorted(paths)


def scrape_page(path):
    s = get_session()
    url = f"{BASE_URL}{path}"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return path, {}, f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = {}
        for block in blocks:
            title_p = block.find("p", class_="courseblocktitle")
            if not title_p:
                continue
            title_text = title_p.get_text(" ", strip=True)
            # Format: "DEPT NNNN Title of Course" (no dot separator like Brown)
            m = re.match(r"^([A-Z][A-Z0-9/]*)\s+([\d]+[A-Z]?)\s+(.+)$", title_text)
            if not m:
                continue
            dept_code = m.group(1).strip()
            course_num = m.group(2).strip()
            title = m.group(3).strip()

            desc_p = block.find("p", class_="courseblockdesc")
            desc = desc_p.get_text(" ", strip=True) if desc_p else ""

            code = f"{dept_code} {course_num}"
            full_text = f"{title} {desc}"
            area = classify_dept(dept_code, path)
            level = classify_level(course_num)

            courses[code] = {
                "university": "washu",
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
            }
        return path, courses, None
    except Exception as e:
        return path, {}, str(e)


def scrape_washu():
    output_dir = "/home/user/routine/data/washu"
    os.makedirs(output_dir, exist_ok=True)

    print("=== WashU Course Catalog Scraper ===")
    print("Fetching department paths...")
    paths = get_dept_paths()
    print(f"Found {len(paths)} paths to scrape")

    all_courses = {}
    failed = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(scrape_page, p): p for p in paths}
        for fut in as_completed(futures):
            path, courses, err = fut.result()
            if err:
                print(f"  FAIL {path}: {err}")
                failed.append(path)
            else:
                new = 0
                for code, c in courses.items():
                    if code not in all_courses:
                        all_courses[code] = c
                        new += 1
                if new:
                    print(f"  {path}: {new} new courses")
            time.sleep(0.05)

    course_list = list(all_courses.values())
    total = len(course_list)
    if total == 0:
        print("No courses collected!")
        return {}

    prog = sum(1 for c in course_list if c["progressive_signal"])
    canon = sum(1 for c in course_list if c["western_canon_signal"])
    cn = sum(1 for c in course_list if c["climate_narrow_signal"])
    cb = sum(1 for c in course_list if c["climate_broad_signal"])
    area_counts = {}
    for c in course_list:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    print(f"\n=== WashU Summary ===")
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
    csv_path = f"{output_dir}/washu_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(course_list)

    summary = {
        "university": "washu",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "bulletin.wustl.edu (CourseleafCMS)",
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
        "failed_paths": failed,
    }
    summary_path = f"{output_dir}/washu_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_washu()
