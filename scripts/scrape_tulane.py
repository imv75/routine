#!/usr/bin/env python3
"""
Tulane University course catalog scraper.
Same HTML structure as UNC: div.courseblock > span.detail-code/title + p.courseblockdesc
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://catalog.tulane.edu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
UNIVERSITY = "tulane"
OUTPUT_DIR = "/home/user/routine/data/tulane"
OUTPUT_CSV = f"{OUTPUT_DIR}/tulane_{CATALOG_YEAR}.csv"
SUMMARY_FILE = f"{OUTPUT_DIR}/tulane_summary.json"

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

CLIMATE_NARROW_KEYWORDS = [
    "climate change", "global warming", "greenhouse gas", "carbon emission",
    "fossil fuel", "sea level rise", "climate crisis",
]

CLIMATE_BROAD_KEYWORDS = [
    "climate", "sustainability", "sustainable", "renewable energy",
    "environmental justice", "carbon", "decarbonization", "net zero",
    "clean energy", "green energy", "ecological", "ecosystem", "biodiversity",
]

HUMANITIES = {"afrs", "arbc", "arhs", "arch", "asta", "astc", "astj", "astk", "cine",
              "clas", "colt", "comm", "danc", "engl", "enls", "fren", "germ", "grek",
              "hacr", "hbrw", "hist", "hisa", "hisb", "hisc", "hise", "hisl", "hism",
              "hisu", "huma", "ital", "jwst", "latn", "lctl", "ling", "mems", "musc",
              "nais", "paah", "paen", "pahs", "pahm", "pamu", "parl", "pasc", "patr",
              "phil", "port", "rlst", "russ", "spec", "span", "swhl", "thea", "yrba"}
SOCIAL_SCIENCES = {"anth", "econ", "educ", "evst", "gdev", "glsp", "last", "paan",
                   "pabi", "pass", "paso", "pola", "polc", "poli", "pols", "polt",
                   "pecn", "psyc", "psdv", "soci", "urst", "socb"}
STEM = {"astr", "biol", "bmen", "bimi", "bmsp", "bios", "bioc", "cell", "ceng",
        "chem", "cmps", "cosc", "data", "ebio", "eens", "elec", "engp", "gbch",
        "gene", "hmgn", "immu", "math", "mech", "mpen", "miim", "nsci", "phys",
        "rcse", "pamt", "brbh"}
MEDICAL = {"anes", "bemh", "bioc", "brbh", "cldg", "derm", "emer", "famy", "fim1",
           "fim2", "genm", "gant", "gphr", "gpso", "hsto", "kine", "med", "micr",
           "mscr", "neur", "nesc", "nrsr", "nrsg", "obgy", "opth", "orth", "otln",
           "peds", "phar", "pysi", "pych", "phea", "rads", "sbps", "spmd", "surg",
           "trmd", "urol", "enhs", "epid", "hpam", "path"}
PROFESSIONAL = {"accn", "admr", "agst", "bsls", "busn", "busg", "cdma", "crdv", "circ",
                "celt", "cccc", "csmt", "desg", "ddsn", "dmpc", "drls", "emba", "efin",
                "fine", "fnar", "frln", "gmba", "gfin", "gdev", "glsp", "hmls",
                "inbs", "intd", "ihsd", "isib", "intr", "info", "intu", "land",
                "lgst", "mlar", "laws", "1law", "2law", "3law", "4law", "clin",
                "mini", "ncls", "lger", "ergl", "empl", "taxn", "para", "mpad",
                "mgmt", "mcom", "mgsc", "pers", "mktg", "mdes", "pres",
                "pais", "papl", "sola", "sopa", "scen", "sise", "sowk", "pasw",
                "srvc", "slam", "sred", "surb", "tide", "tidr", "tylr", "aero",
                "mils", "navs", "enrg", "cpst", "colq", "eapp", "rels"}

AREA_MAP = {
    "Humanities": HUMANITIES,
    "Social Sciences": SOCIAL_SCIENCES,
    "STEM": STEM,
    "Medical Sciences": MEDICAL,
    "Professional": PROFESSIONAL,
}

DEPARTMENTS = [
    "circ", "accn", "admr", "afrs", "agst", "asls", "anat", "anth", "paan",
    "arbc", "arch", "paar", "arhs", "paah", "arst", "asta", "astr", "gbch",
    "bemh", "biol", "pabi", "bmen", "bimi", "bmsp", "bios", "bsls", "busn",
    "busg", "cdma", "crdv", "cell", "celt", "ceng", "chem", "astc", "cine",
    "cccc", "clas", "mscr", "colq", "comm", "colt", "cosc", "cmps", "data",
    "csmt", "danc", "desg", "ddsn", "dmpc", "drls", "eens", "ebio", "econ",
    "educ", "elec", "essc", "enrg", "ergl", "engp", "engl", "enls", "paen",
    "eapp", "enhs", "evst", "epid", "emba", "efin", "fine", "fnar", "frln",
    "fren", "gess", "glsp", "germ", "gmba", "gdev", "gfin", "grek", "hacr",
    "hpam", "hbrw", "pres", "hist", "pahs", "hisb", "hisa", "hisc", "hisl",
    "hism", "hise", "hisu", "hmls", "hmgn", "huma", "pahm", "immu", "info",
    "cpst", "intu", "intd", "inbs", "ihsd", "isib", "intr", "ital", "astj",
    "jwst", "kine", "astk", "empl", "land", "latn", "last", "clin", "1law",
    "mini", "ncls", "laws", "lger", "2law", "3law", "4law", "lgst", "lctl",
    "ling", "mgmt", "mcom", "mgsc", "pers", "mktg", "mlar", "mpen", "pamt",
    "math", "anes", "bioc", "brbh", "cldg", "derm", "emer", "famy", "fim1",
    "fim2", "genm", "gene", "gant", "hsto", "path", "med", "micr", "neur",
    "nesc", "nrsr", "obgy", "opth", "orth", "otln", "peds", "phar", "pysi",
    "pych", "phea", "rads", "surg", "urol", "mech", "mdes", "mems", "miim",
    "musc", "pamu", "apms", "nais", "nsci", "nrsg", "para", "gphr", "phil",
    "phys", "gpso", "pecn", "pola", "polc", "pols", "poli", "psdv", "polt",
    "port", "pais", "papl", "psyc", "mpad", "sphl", "sphu", "srvc", "parl",
    "rlst", "rcse", "aero", "mils", "navs", "russ", "sola", "sopa", "scen",
    "pasc", "sise", "pass", "pasw", "sowk", "sbps", "paso", "soci", "span",
    "spec", "spmd", "slam", "sred", "surb", "swhl", "taxn", "tylr", "patr",
    "thea", "tidr", "tide", "trmd", "urst", "yrba",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})


def classify_area(dept_code):
    dept = dept_code.lower()
    for area, codes in AREA_MAP.items():
        if dept in codes:
            return area
    return "Other"


def classify_level(course_num):
    try:
        num = int(re.sub(r"[^0-9]", "", str(course_num))[:4])
        return "graduate" if num >= 5000 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def parse_course_block(block):
    # Tulane: span.detail-code, span.detail-title, p.courseblockdesc
    code_span = block.find("span", class_="detail-code")
    title_span = block.find("span", class_="detail-title")
    desc_p = block.find("p", class_="courseblockdesc")

    if not code_span or not title_span:
        return None

    code_text = code_span.get_text(strip=True).rstrip(".")
    parts = code_text.split()
    if len(parts) < 2:
        return None
    dept = parts[0]
    num = parts[1]

    title = title_span.get_text(strip=True).rstrip(".")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""
    full_text = f"{title} {desc}"

    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept),
        "level": classify_level(num),
        "progressive_signal": check_keywords(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_keywords(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_keywords(full_text, CLIMATE_NARROW_KEYWORDS),
        "climate_broad_signal": check_keywords(full_text, CLIMATE_BROAD_KEYWORDS),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_dept(dept_slug):
    url = f"{BASE_URL}/courses/{dept_slug}/"
    try:
        r = SESSION.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for b in blocks:
            c = parse_course_block(b)
            if c:
                courses.append(c)
        return courses
    except Exception as e:
        print(f"  ERROR {dept_slug}: {e}")
        return []


def main():
    all_courses = []
    seen = set()
    failed = []

    print("=== Tulane University Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}\n")

    depts = list(dict.fromkeys(DEPARTMENTS))
    print(f"Scraping {len(depts)} departments...")

    for dept in depts:
        courses = scrape_dept(dept)
        if not courses:
            failed.append(dept)
            continue
        new = 0
        for c in courses:
            key = f"{c['department_code']}_{c['course_number']}"
            if key not in seen:
                seen.add(key)
                all_courses.append(c)
                new += 1
        if new:
            print(f"  {dept.upper()}: {new} courses")
        time.sleep(0.25)

    print(f"\nTotal unique courses: {len(all_courses)}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    prog_count = sum(1 for c in all_courses if c["progressive_signal"])
    canon_count = sum(1 for c in all_courses if c["western_canon_signal"])
    cn_count = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb_count = sum(1 for c in all_courses if c["climate_broad_signal"])
    total = len(all_courses)
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": UNIVERSITY, "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL, "total_courses": total,
        "progressive_count": prog_count,
        "progressive_pct": round(100 * prog_count / total, 2) if total else 0,
        "canon_count": canon_count,
        "canon_pct": round(100 * canon_count / total, 2) if total else 0,
        "climate_narrow_count": cn_count,
        "climate_narrow_pct": round(100 * cn_count / total, 2) if total else 0,
        "climate_broad_count": cb_count,
        "climate_broad_pct": round(100 * cb_count / total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote {OUTPUT_CSV}\nWrote {SUMMARY_FILE}")
    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog_count} ({summary['progressive_pct']}%) | Canon: {canon_count} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({100*cnt//total if total else 0}%)")


if __name__ == "__main__":
    main()
