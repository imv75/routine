#!/usr/bin/env python3
"""
University of New Mexico Course Catalog Scraper.
Source: lobowebapp.unm.edu/ban_ssb/bwckctlg.p_display_courses (Banner SIS)
Format: td.nttitle (course code+title) + td.ntdefault (description+metadata)
Graduate level: leading digit of course number >= 5
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
BASE_URL = "https://lobowebapp.unm.edu/ban_ssb"
TERM = "202680"  # Fall 2026

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

STEM_SUBJS = {
    "astr", "bioc", "biol", "bme", "biom", "cbe", "ce", "chem", "cj",
    "comp", "cs", "ece", "econ", "ees", "ene", "engl", "esnr", "envs",
    "geog", "geol", "math", "me", "nurs", "nutri", "phys", "psy",
    "stat", "aiml",
}
HUMANITIES_SUBJS = {
    "afst", "amst", "arab", "arbc", "arch", "art", "arth", "arts", "arts",
    "chin", "clst", "comp", "crwr", "dram", "engl", "film", "fren",
    "germ", "grek", "hist", "ital", "japn", "jour", "latn", "ling",
    "musc", "phil", "port", "reli", "russ", "span", "thea", "writ",
}
SOCIAL_SUBJS = {
    "afst", "amst", "anth", "ccs", "ccst", "comm", "cj", "crj", "econ",
    "educ", "glst", "pols", "psyc", "soci", "wmst",
}
MEDICAL_SUBJS = {
    "anes", "bioc", "biom", "clns", "dent", "med", "nurs", "nutri",
    "pa", "phmd", "pubh", "pthl", "radt", "surg",
}
PROFESSIONAL_SUBJS = {
    "acct", "arch", "busa", "bcis", "bfin", "bstc", "bu", "const",
    "crp", "educ", "engl", "fmgt", "info", "law", "mba", "mgmt",
    "mktg", "oia", "plan", "pub",
}


def classify_dept(subj):
    s = subj.lower()
    if s in STEM_SUBJS:
        return "STEM"
    if s in MEDICAL_SUBJS:
        return "Medical Sciences"
    if s in HUMANITIES_SUBJS:
        return "Humanities"
    if s in SOCIAL_SUBJS:
        return "Social Sciences"
    if s in PROFESSIONAL_SUBJS:
        return "Professional"
    return "Other"


def classify_level(course_num):
    digits = re.sub(r"[^0-9]", "", str(course_num))
    if not digits:
        return "undergraduate"
    first_digit = int(digits[0])
    return "graduate" if first_digit >= 5 else "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def get_subjects():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    # Navigate to term selection page
    r = s.get(f"{BASE_URL}/bwckctlg.p_disp_dyn_ctlg", timeout=15, verify=VERIFY)
    # POST to select term
    r2 = s.post(
        f"{BASE_URL}/bwckctlg.p_disp_cat_term_date",
        data={"cat_term_in": TERM},
        timeout=15, verify=VERIFY,
    )
    soup = BeautifulSoup(r2.text, "html.parser")
    sel = soup.find("select", {"name": "sel_subj"})
    if not sel:
        return []
    return [
        o["value"]
        for o in sel.find_all("option")
        if o.get("value") and o["value"] not in ("", "dummy")
    ]


def scrape_subject(subj):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    try:
        r = s.post(
            f"{BASE_URL}/bwckctlg.p_display_courses",
            data=[
                ("term_in", TERM), ("call_proc_in", ""),
                ("sel_subj", "dummy"), ("sel_subj", subj),
                ("sel_levl", "dummy"), ("sel_levl", "%"),
                ("sel_schd", "dummy"), ("sel_schd", "%"),
                ("sel_coll", "dummy"), ("sel_coll", "%"),
                ("sel_divs", "dummy"), ("sel_divs", "%"),
                ("sel_dept", "dummy"), ("sel_dept", "%"),
                ("sel_attr", "dummy"), ("sel_attr", "%"),
                ("sel_crse_strt", ""), ("sel_crse_end", "9999"),
                ("sel_title", ""), ("sel_from_cred", ""), ("sel_to_cred", ""),
                ("sel_ptrm", "%"),
            ],
            timeout=20, verify=VERIFY,
        )
        if r.status_code != 200:
            return subj, [], f"HTTP {r.status_code}"

        soup = BeautifulSoup(r.text, "html.parser")
        courses = []

        # Pair nttitle + ntdefault rows (use recursive=False to avoid nested table confusion)
        rows = soup.find_all("tr")
        current_title = None
        for row in rows:
            td = row.find("td", class_="nttitle", recursive=False)
            if td:
                a = td.find("a", href=True)
                if a:
                    current_title = a.get_text(strip=True)
                continue
            td2 = row.find("td", class_="ntdefault", recursive=False)
            if td2 and current_title:
                # Parse "SUBJ NNNN - Title" or "SUBJ NNNN - Title"
                m = re.match(r"^([A-Z][A-Z0-9]*)\s+([\d]+[A-Z]?)\s*-\s*(.+)$", current_title)
                if m:
                    dept_code = m.group(1)
                    course_num = m.group(2)
                    title = m.group(3).strip()

                    # Description is the first text block in ntdefault
                    desc_parts = []
                    for item in td2.contents:
                        text = item.get_text(" ", strip=True) if hasattr(item, 'get_text') else str(item).strip()
                        if text and not text.startswith(("Credit hours", "Lecture hours", "Schedule Types")):
                            # Stop at metadata
                            if re.match(r"^\d+\.\d{3}", text):
                                break
                            desc_parts.append(text)
                        elif re.match(r"^\d+\.\d{3}", text):
                            break
                    desc = " ".join(desc_parts).strip()
                    # Take only until first numeric metadata
                    full_text = f"{title} {desc}"
                    area = classify_dept(dept_code)
                    level = classify_level(course_num)

                    courses.append({
                        "university": "unm",
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
                current_title = None

        return subj, courses, None
    except Exception as e:
        return subj, [], str(e)


def scrape_unm():
    output_dir = "/home/user/routine/data/unm"
    os.makedirs(output_dir, exist_ok=True)

    print("=== UNM Course Catalog Scraper ===")
    print("Fetching subject list...")
    subjects = get_subjects()
    print(f"Found {len(subjects)} subjects")

    all_courses = []
    seen = set()
    failed = []

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(scrape_subject, subj): subj for subj in subjects}
        for fut in as_completed(futures):
            subj, courses, err = fut.result()
            if err:
                print(f"  FAIL {subj}: {err}")
                failed.append(subj)
            else:
                new = 0
                for c in courses:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
                if new:
                    print(f"  {subj}: {new} courses")
            time.sleep(0.1)

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

    print(f"\n=== UNM Summary ===")
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
    csv_path = f"{output_dir}/unm_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    summary = {
        "university": "unm",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "lobowebapp.unm.edu/ban_ssb/bwckctlg.p_display_courses (Banner SIS, Fall 2026)",
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
        "failed_subjects": failed,
    }
    summary_path = f"{output_dir}/unm_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSaved: {csv_path}")
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_unm()
