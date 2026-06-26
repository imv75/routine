#!/usr/bin/env python3
"""
Brown University Course Catalog Scraper.
Source: bulletin.brown.edu/{dept}/
Format: CourseleafCMS div.courseblock > p.courseblocktitle[data-code] + p.courseblockdesc
Graduate level: course number >= 2000
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
BASE_URL = "https://bulletin.brown.edu"

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

# Department-to-area mapping based on path slug
DEPT_AREA_MAP = {
    "africanastudies": "Social Sciences",
    "americanstudies": "Social Sciences",
    "anthropology": "Social Sciences",
    "appliedmathematics": "STEM",
    "biologyandmedicine": "STEM",
    "bibs": "STEM",
    "chemistry": "STEM",
    "classics": "Humanities",
    "cognitivelinguisticandpsychologicalsciences": "Social Sciences",
    "comparativeliterature": "Humanities",
    "computerscience": "STEM",
    "datascience": "STEM",
    "earth-environmental-planetary-sciences": "STEM",
    "eastasianstudies": "Humanities",
    "economics": "Social Sciences",
    "education": "Professional",
    "egyptology-assyriology": "Humanities",
    "engineering": "STEM",
    "english": "Humanities",
    "frenchfs": "Humanities",
    "germanstudies": "Humanities",
    "hispanicstudies": "Humanities",
    "history": "Humanities",
    "historyofartandarchitecture": "Humanities",
    "international-public-affairs": "Social Sciences",
    "italianstudies": "Humanities",
    "latinamericanandcaribbeanstudies": "Social Sciences",
    "mathematics": "STEM",
    "music": "Humanities",
    "musics": "Humanities",
    "musicsstudies": "Humanities",
    "philosophy": "Humanities",
    "physics": "STEM",
    "politicalscience": "Social Sciences",
    "public-health": "Medical Sciences",
    "religiousstudies": "Humanities",
    "slavicstudies": "Humanities",
    "sociology": "Social Sciences",
    "theatreartsandperformancestudies": "Humanities",
    "urbanstudies": "Social Sciences",
    "universitycourses": "Other",
}


def classify_area(path_slug, dept_code):
    # Try path slug first
    slug = path_slug.strip("/").split("/")[-1].lower()
    if slug in DEPT_AREA_MAP:
        return DEPT_AREA_MAP[slug]
    return "Other"


def classify_level(course_code):
    # Brown: "DEPT NNNN[X]" - graduate if number >= 2000
    m = re.search(r"\d+", course_code.split()[-1] if " " in course_code else course_code)
    if m:
        try:
            n = int(m.group())
            return "graduate" if n >= 2000 else "undergraduate"
        except Exception:
            pass
    return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def get_dept_paths():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    paths = set()

    # Primary source: departments page
    for page_url in [
        f"{BASE_URL}/departments-centers-programs-institutes/",
        f"{BASE_URL}/universitycourses/",
    ]:
        try:
            r = s.get(page_url, timeout=15, verify=VERIFY)
            soup = BeautifulSoup(r.text, "html.parser")
            content = soup.find("div", id="textcontainer") or soup.body
            if content:
                for a in content.find_all("a", href=True):
                    h = a["href"]
                    if (
                        h.startswith("/")
                        and h != "/"
                        and not h.startswith("/#")
                        and not h.startswith("/azindex")
                        and not h.startswith("/pdf")
                        and "." not in h.split("/")[-1]
                    ):
                        paths.add(h)
        except Exception:
            pass

    return sorted(paths)


def scrape_path(path):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    url = f"{BASE_URL}{path}"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return path, {}, f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")

        courses = {}  # code -> course dict, to dedup within this page
        for block in blocks:
            title_p = block.find("p", class_="courseblocktitle")
            if not title_p:
                continue

            code = title_p.get("data-code", "").strip()
            if not code:
                # Try to parse from text
                text = title_p.get_text(strip=True)
                m = re.match(r"^([A-Z]+\s+[\d]+[A-Z]?)\.", text)
                if m:
                    code = m.group(1).strip()
                else:
                    continue

            # Parse: "DEPT NNNN Title" or "DEPT NNNN. Title"
            title_text = title_p.get_text(strip=True)
            m = re.match(r"^[A-Z]+\s+[\dA-Z]+[.]\s*(.+)$", title_text)
            title = m.group(1).rstrip(".").strip() if m else title_text

            desc_p = block.find("p", class_="courseblockdesc")
            desc = desc_p.get_text(" ", strip=True) if desc_p else ""

            # Extract dept code and number
            parts = code.split()
            dept_code = parts[0] if parts else code
            course_num = parts[1] if len(parts) > 1 else ""

            full_text = f"{title} {desc}"
            area = classify_area(path, dept_code)
            level = classify_level(code)

            courses[code] = {
                "university": "brown",
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


def scrape_brown():
    output_dir = "/home/user/routine/data/brown"
    os.makedirs(output_dir, exist_ok=True)

    print("=== Brown University Course Catalog Scraper ===")
    print("Fetching department list...")
    dept_paths = get_dept_paths()
    print(f"Found {len(dept_paths)} department paths")

    all_courses = {}  # code -> course (global dedup)
    failed = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(scrape_path, p): p for p in dept_paths}
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

    print(f"\n=== Brown Summary ===")
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
    csv_path = f"{output_dir}/brown_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(course_list)

    summary = {
        "university": "brown",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "bulletin.brown.edu/{dept}/",
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
    summary_path = f"{output_dir}/brown_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_brown()
