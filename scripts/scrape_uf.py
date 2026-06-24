#!/usr/bin/env python3
"""
University of Florida course catalog scraper.
URL: catalog.ufl.edu/UGRD/courses/{dept_name}/
HTML: div.courseblock > p.courseblocktitle > strong "DEPT NUM Title" + p.courseblockdesc
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "uf"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://catalog.ufl.edu"
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

# UF uses 3-4 letter dept codes in course IDs
STEM_PREFIXES = {"aeb", "abe", "agr", "agro", "ame", "aom", "asp", "ast", "bch",
                 "bch", "bsc", "bst", "bot", "bme", "bsc", "che", "chm", "cis",
                 "cgs", "cls", "cnt", "cop", "cot", "cox", "dep", "eee", "eel",
                 "egn", "enc", "ent", "env", "evr", "foe", "for", "frc",
                 "geo", "glg", "hid", "hsc", "hsc", "ias", "ics", "ids",
                 "kha", "map", "mas", "mae", "mat", "mcb", "mca", "mch", "mde",
                 "mer", "met", "mic", "msc", "nsc", "nss", "nst", "oce",
                 "pcb", "phy", "plb", "plc", "plp", "plsc", "pmb", "psy",
                 "sta", "ste", "sur", "wis", "zoo"}
HUMANITIES_PREFIXES = {"aml", "ant", "afa", "arh", "afr", "afa", "ari", "art",
                       "asp", "anh", "ams", "cla", "com", "dra", "eas",
                       "enc", "enl", "enh", "eul", "fil", "fre", "gre",
                       "grk", "heb", "his", "hun", "ias", "ita", "lat",
                       "lin", "lit", "mas", "mus", "mue", "mut", "phl",
                       "por", "rel", "rum", "rus", "san", "sca", "spa",
                       "tpa", "wsm"}
SOCIAL_PREFIXES = {"adu", "afa", "afh", "afr", "agc", "alh", "amh", "ant",
                   "ccj", "clp", "com", "crw", "dev", "eco", "ecp", "edu",
                   "edf", "edr", "edh", "eme", "ems", "emh", "evr", "fly",
                   "geo", "gif", "gis", "glb", "hsa", "hse", "ied", "ids",
                   "ins", "lah", "lsa", "map", "mdv", "obs", "pac", "pch",
                   "poc", "pol", "pos", "puf", "reh", "soc", "swk", "ura",
                   "wss", "uvp"}
MEDICAL_PREFIXES = {"anh", "aph", "apt", "aud", "ban", "bmi", "cen", "cge",
                    "chs", "cla", "clb", "clt", "cnd", "dnt", "epi", "epr",
                    "est", "exs", "fnp", "gms", "gnt", "hpa", "hpn", "hps",
                    "hsc", "hsm", "ims", "mph", "msc", "nsc", "nss", "ntr",
                    "oph", "opt", "ort", "pab", "pac", "pch", "pep", "pha",
                    "phm", "phr", "phy", "pio", "ptd", "rad", "reh", "res",
                    "smb", "srd", "srm", "vem", "vhr"}


def classify_area(dept_code):
    d = dept_code.lower()[:3]
    if d in STEM_PREFIXES:
        return "STEM"
    if d in HUMANITIES_PREFIXES:
        return "Humanities"
    if d in SOCIAL_PREFIXES:
        return "Social Sciences"
    if d in MEDICAL_PREFIXES:
        return "Medical Sciences"
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


def get_dept_urls(session, catalog="UGRD"):
    url = f"{BASE_URL}/{catalog}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select(f"li a[href*='/{catalog}/courses/']")
        depts = []
        for l in links:
            href = l.get("href", "")
            m = re.search(rf"/{catalog}/courses/([^/]+)/", href)
            if m:
                depts.append(m.group(1))
        return list(dict.fromkeys(depts))  # deduplicate preserving order
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def parse_block(block):
    title_p = block.find("p", class_="courseblocktitle")
    if not title_p:
        return None
    strong = title_p.find("strong")
    if not strong:
        return None
    # Remove credits span from text
    credits_span = strong.find("span", class_="credits")
    if credits_span:
        credits_span.decompose()
    title_text = strong.get_text(" ", strip=True)

    # Format: "DEPT NUM Title" (space-separated, dept is 2-4 letters, num is 4 digits)
    m = re.match(r"([A-Z]{2,6}[A-Z0-9]*)\s+([\w]+)\s+(.+)", title_text)
    if not m:
        return None
    dept = m.group(1)
    num = m.group(2)
    title = m.group(3).strip()

    desc_p = block.find("p", class_="courseblockdesc")
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
        "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
        "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_dept(session, dept_slug, catalog="UGRD"):
    url = f"{BASE_URL}/{catalog}/courses/{dept_slug}/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        return [c for c in (parse_block(b) for b in soup.find_all("div", class_="courseblock")) if c]
    except Exception as e:
        print(f"  ERROR {dept_slug}: {e}")
        return []


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Florida Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    for catalog in ["UGRD", "GRAD"]:
        depts = get_dept_urls(session, catalog)
        print(f"Scraping {len(depts)} {catalog} departments...")
        for dept in depts:
            courses = scrape_dept(session, dept, catalog)
            new = 0
            for c in courses:
                key = f"{c['department_code']}_{c['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(c)
                    new += 1
            if not courses:
                failed.append(dept)
            elif new:
                print(f"  {dept} ({catalog}): {new} courses")
            time.sleep(0.2)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}")

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
