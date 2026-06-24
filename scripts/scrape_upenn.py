#!/usr/bin/env python3
"""
UPenn course catalog scraper for Marinovic (2026) curriculum dataset.
Scrapes catalog.upenn.edu/courses/ for all departments.
HTML structure: div.courseblock > p.courseblocktitle + p.courseblockextra...
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

BASE_URL = "https://catalog.upenn.edu"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
OUTPUT_DIR = "/home/user/routine/data/upenn"
PROGRESS_FILE = "/home/user/routine/data/upenn/scrape_progress.json"
OUTPUT_CSV = f"{OUTPUT_DIR}/upenn_{CATALOG_YEAR}_raw.csv"
CLEAN_CSV = f"{OUTPUT_DIR}/upenn_{CATALOG_YEAR}.csv"

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
    "diaspora", "reparations", "microaggression", "implicit bias",
    "systemic racism",
]

WESTERN_CANON_KEYWORDS = [
    "western civilization", "western tradition", "western thought",
    "great books", "liberal arts tradition",
    "ancient greece", "ancient rome", "greek philosophy", "roman law",
    "classical antiquity", "greco-roman",
    "renaissance", "enlightenment", "medieval philosophy", "reformation",
    "shakespeare", "plato", "aristotle", "homer", "dante", "virgil",
    "milton", "cicero", "socrates", "augustine", "aquinas", "machiavelli",
    "hobbes", "descartes", "kant", "hegel", "locke", "tocqueville",
    "montesquieu",
    "bible", "biblical", "iliad", "odyssey", "aeneid", "divine comedy",
    "canterbury tales", "leviathan", "federalist",
    "classics", "classical",
]

CLIMATE_NARROW_KEYWORDS = [
    "climate change", "global warming", "greenhouse gas", "carbon emissions",
    "decarbonization", "net zero", "climate policy", "climate science",
    "climate adaptation", "climate mitigation", "climate justice",
]

CLIMATE_BROAD_KEYWORDS = CLIMATE_NARROW_KEYWORDS + [
    "sustainability", "sustainable", "sustainable development",
    "renewable energy", "clean energy",
]

AREA_MAP = {
    "ACCT": "Professional", "AFRC": "Humanities", "AMCH": "Humanities",
    "AMEL": "Humanities", "AMCS": "STEM", "AMHR": "Humanities",
    "ANTH": "Social Sciences", "APOP": "Social Sciences", "ARAB": "Humanities",
    "ARCH": "Professional", "AAMW": "Humanities", "ARTH": "Humanities",
    "ASAM": "Social Sciences", "ALAN": "Humanities", "ASTR": "STEM",
    "ASLD": "Humanities", "ANAT": "Medical Sciences", "ANCH": "Humanities",
    "BAAS": "Other", "BDS": "Social Sciences", "BENG": "Humanities",
    "BENF": "Humanities", "BMB": "STEM", "BCHE": "STEM", "BE": "STEM",
    "BIOE": "Humanities", "BIOL": "STEM", "BIOM": "Medical Sciences",
    "BMIN": "Medical Sciences", "BSTA": "STEM", "BIOT": "STEM",
    "BCS": "Humanities", "BEPP": "Social Sciences", "CAMB": "STEM",
    "CBE": "STEM", "CHEM": "STEM", "CHIC": "Humanities", "CHIN": "Humanities",
    "CINM": "Humanities", "CIMS": "Humanities", "CPLN": "Professional",
    "CLST": "Humanities", "CLSC": "Humanities", "CLCH": "STEM",
    "COGS": "Social Sciences", "COLL": "Other", "COMM": "Social Sciences",
    "COML": "Humanities", "CIS": "STEM", "CIT": "STEM", "CRWR": "Humanities",
    "CRIM": "Social Sciences", "CZCH": "Humanities", "DATA": "STEM",
    "DATS": "STEM", "DEMG": "Social Sciences", "DENT": "Medical Sciences",
    "GADS": "Medical Sciences", "DADE": "Medical Sciences", "GDSD": "Medical Sciences",
    "GEND": "Medical Sciences", "GOPH": "Medical Sciences", "GBIO": "Medical Sciences",
    "GOHS": "Medical Sciences", "GOMD": "Medical Sciences", "GORT": "Medical Sciences",
    "GPED": "Medical Sciences", "GPRD": "Medical Sciences", "GPRS": "Medical Sciences",
    "DSGN": "Humanities", "DISG": "Humanities", "DIGC": "Humanities",
    "DTCH": "Humanities", "EESC": "STEM", "EALC": "Humanities",
    "ECON": "Social Sciences", "EDUC": "Professional", "EDEN": "Professional",
    "EDHE": "Professional", "EDPR": "Professional", "EDME": "Professional",
    "EDMC": "Professional", "EDCL": "Professional", "EDSC": "Professional",
    "EDSL": "Professional", "EDTC": "Professional", "EDTF": "Professional",
    "ESE": "STEM", "ENMG": "Professional", "EAS": "STEM", "ENGR": "STEM",
    "ENM": "STEM", "ENGL": "Humanities", "ENLT": "Humanities",
    "ENVS": "Social Sciences", "EPID": "Medical Sciences", "ETHC": "Humanities",
    "FILP": "Humanities", "FNCE": "Professional", "FNAR": "Humanities",
    "FRSM": "Humanities", "FIGS": "Humanities", "FREN": "Humanities",
    "GSWS": "Humanities", "GENC": "Medical Sciences", "GCB": "STEM",
    "GRMN": "Humanities", "GMPA": "Professional", "GLBS": "Social Sciences",
    "GAFL": "Professional", "GAS": "Other", "GREK": "Humanities",
    "GUJR": "Humanities", "HSOC": "Social Sciences", "HCIN": "Medical Sciences",
    "HCMG": "Professional", "HPR": "Medical Sciences", "HQS": "Medical Sciences",
    "HEBR": "Humanities", "HIND": "Humanities", "HSPV": "Humanities",
    "HSSC": "Social Sciences", "HIST": "Humanities", "HUNG": "Humanities",
    "IGBO": "Humanities", "IMUN": "Medical Sciences", "IMP": "Medical Sciences",
    "INDO": "Humanities", "IPD": "Professional", "INTG": "Other",
    "ICOM": "Social Sciences", "INTR": "Social Sciences", "INSP": "Social Sciences",
    "IRIS": "Humanities", "ITAL": "Humanities", "JPAN": "Humanities",
    "JWST": "Humanities", "KAND": "Humanities", "KORN": "Humanities",
    "LARP": "Professional", "LANG": "Humanities", "LATN": "Humanities",
    "LALS": "Social Sciences", "LAW": "Professional", "LAWM": "Professional",
    "LEAD": "Other", "LGST": "Professional", "LING": "Humanities",
    "LGIC": "STEM", "MALG": "Humanities", "MLYM": "Humanities",
    "MGMT": "Professional", "MRTI": "Humanities", "MKTG": "Professional",
    "MAPP": "Social Sciences", "MLA": "Humanities", "MSSP": "Social Sciences",
    "MTR": "Medical Sciences", "MUSA": "Social Sciences", "MSE": "STEM",
    "MTHS": "STEM", "MATH": "STEM", "MEAM": "STEM", "MPHY": "Medical Sciences",
    "MELC": "Humanities", "MSCI": "Other", "MODM": "Humanities",
    "MUSC": "Humanities", "NANO": "STEM", "NSCI": "Other",
    "NETS": "STEM", "NEUR": "Medical Sciences", "NGG": "Medical Sciences",
    "NRSC": "Medical Sciences", "NPLD": "Professional", "NURS": "Medical Sciences",
    "NUTR": "Medical Sciences", "OIDD": "Professional", "ORGC": "Social Sciences",
    "DYNM": "Social Sciences", "PASH": "Humanities", "PERS": "Humanities",
    "PHRM": "Medical Sciences", "PHIL": "Humanities", "PPE": "Humanities",
    "PHYL": "STEM", "PHYS": "STEM", "PLSH": "Humanities", "PSCI": "Social Sciences",
    "PPOL": "Professional", "PRTG": "Humanities", "PROW": "Other",
    "PSYC": "Social Sciences", "PUBH": "Medical Sciences", "PUNJ": "Humanities",
    "QUEC": "Humanities", "REAL": "Professional", "REG": "Professional",
    "RELC": "Humanities", "RELS": "Humanities", "ROBO": "STEM",
    "ROML": "Humanities", "RUSS": "Humanities", "REES": "Humanities",
    "SKRT": "Humanities", "SSPP": "Social Sciences", "STSC": "Social Sciences",
    "SCMP": "STEM", "SPRO": "STEM", "SOCW": "Professional", "SWRK": "Professional",
    "SOCI": "Social Sciences", "SAST": "Humanities", "SPAN": "Humanities",
    "SPPO": "Humanities", "STAT": "STEM", "SARB": "Humanities",
    "SWAH": "Humanities", "SWED": "Humanities", "TAML": "Humanities",
    "TELU": "Humanities", "THAI": "Humanities", "THAR": "Humanities",
    "TIBT": "Humanities", "TIGR": "Humanities", "TURK": "Humanities",
    "TWI": "Humanities", "UKRN": "Humanities", "URBS": "Social Sciences",
    "URDU": "Humanities", "VMED": "Medical Sciences", "VCSN": "Medical Sciences",
    "VCSP": "Medical Sciences", "VISR": "Medical Sciences", "VPTH": "Medical Sciences",
    "VIET": "Humanities", "VIPR": "Other", "VLST": "Humanities",
    "WHCP": "Professional", "WH": "Professional", "WOLF": "Humanities",
    "WRIT": "Humanities", "YDSH": "Humanities", "YORB": "Humanities", "ZULU": "Humanities",
}

DEPARTMENTS = [
    "acct", "afrc", "asld", "amhr", "anat", "anch", "amel", "anth", "amcs",
    "apop", "arab", "arch", "aamw", "arth", "asam", "alan", "astr", "baas",
    "bds", "beng", "benf", "bmb", "bche", "be", "bioe", "biol", "biom",
    "bmin", "bsta", "biot", "bcs", "bepp", "camb", "cbe", "chem", "chic",
    "chin", "cinm", "cims", "cpln", "clst", "clsc", "clch", "cogs", "coll",
    "comm", "coml", "cis", "cit", "crwr", "crim", "czch", "data", "dats",
    "demg", "dent", "gads", "dade", "gdsd", "gend", "goph", "gbio", "gohs",
    "gomd", "gort", "gped", "gprd", "gprs", "dsgn", "disg", "digc", "dtch",
    "eesc", "ealc", "econ", "educ", "eden", "edhe", "edpr", "edme", "edmc",
    "edcl", "edsc", "edsl", "edtc", "edtf", "ese", "enmg", "eas", "engr",
    "enm", "engl", "enlt", "envs", "epid", "ethc", "filp", "fnce", "fnar",
    "frsm", "figs", "fren", "gsws", "genc", "gcb", "grmn", "gmpa", "glbs",
    "gafl", "gas", "grek", "gujr", "hsoc", "hcin", "hcmg", "hpr", "hqs",
    "hebr", "hind", "hspv", "hssc", "hist", "hung", "igbo", "imun", "imp",
    "indo", "ipd", "intg", "icom", "intr", "insp", "iris", "ital", "jpan",
    "jwst", "kand", "korn", "larp", "lang", "latn", "lals", "law", "lawm",
    "lead", "lgst", "ling", "lgic", "malg", "mlym", "mgmt", "mrti", "mktg",
    "mapp", "mla", "mssp", "mtr", "musa", "mse", "mths", "math", "meam",
    "mphy", "melc", "msci", "modm", "musc", "nano", "nsci", "nets", "neur",
    "ngg", "nrsc", "npld", "nurs", "nutr", "oidd", "orgc", "dynm", "pash",
    "pers", "phrm", "phil", "ppe", "phyl", "phys", "plsh", "psci", "ppol",
    "prtg", "prow", "psyc", "pubh", "punj", "quec", "real", "reg", "relc",
    "rels", "robo", "roml", "russ", "rees", "skrt", "sspp", "stsc", "scmp",
    "spro", "socw", "swrk", "soci", "sast", "span", "sppo", "stat", "sarb",
    "swah", "swed", "taml", "telu", "thai", "thar", "tibt", "tigr", "turk",
    "twi", "ukrn", "urbs", "urdu", "vmed", "vcsn", "vcsp", "visr", "vpth",
    "viet", "vipr", "vlst", "whcp", "wh", "wolf", "writ", "ydsh", "yorb", "zulu",
]


def keyword_match(text: str, keywords: list) -> bool:
    text_lower = text.lower()
    for kw in keywords:
        if " " in kw:
            if kw in text_lower:
                return True
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                return True
    return False


def classify_level(course_num: str) -> str:
    digits = re.sub(r"[^0-9]", "", course_num)
    if digits:
        return "undergraduate" if int(digits) < 2000 else "graduate"
    return "unknown"


def parse_courses_from_html(html: str, dept_code: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    courses = []
    blocks = soup.find_all("div", class_="courseblock")

    for block in blocks:
        title_p = block.find("p", class_="courseblocktitle")
        if not title_p:
            continue

        # Title like "AFRC\xa00008  Sociology of the Black Community"
        title_text = title_p.get_text(" ", strip=True)
        # Normalize non-breaking spaces and multiple spaces
        title_text = title_text.replace("\xa0", " ").strip()

        m = re.match(r"([A-Z]+)\s+(\S+)\s+(.*)", title_text)
        if not m:
            continue

        dept = m.group(1).upper()
        num = m.group(2).strip()
        title = m.group(3).strip()

        # Collect extra paragraphs
        extra_paras = block.find_all("p", class_="courseblockextra")
        description = ""
        cross_listed_codes = []

        for p in extra_paras:
            txt = p.get_text(" ", strip=True)
            # First substantive paragraph is the description
            # (not semester info, not "Also Offered As:", not credit units)
            if re.match(r"(Fall|Spring|Summer|Year)", txt):
                continue
            if txt.startswith("Also Offered As:") or txt.startswith("Crosslisted"):
                # Extract cross-listed codes
                m2 = re.findall(r"([A-Z]+)\s*[\xa0\s]+(\d+\w*)", txt)
                cross_listed_codes = [f"{c[0]} {c[1]}" for c in m2]
                continue
            if re.match(r"[\d.]+ Course Unit", txt):
                continue
            if not description and len(txt) > 20:
                description = txt

        combined = f"{title} {description}".strip()
        dept_code_upper = dept_code.upper()
        area = AREA_MAP.get(dept, AREA_MAP.get(dept_code_upper, "Other"))

        courses.append({
            "university": "upenn",
            "academic_year": CATALOG_YEAR,
            "academic_year_label": CATALOG_LABEL,
            "department_code": dept,
            "course_number": num,
            "title": title,
            "description": description,
            "broad_area": area,
            "level": classify_level(num),
            "progressive_signal": keyword_match(combined, PROGRESSIVE_KEYWORDS),
            "western_canon_signal": keyword_match(combined, WESTERN_CANON_KEYWORDS),
            "climate_narrow_signal": keyword_match(combined, CLIMATE_NARROW_KEYWORDS),
            "climate_broad_signal": keyword_match(combined, CLIMATE_BROAD_KEYWORDS),
            "cross_listed_with": "|".join(cross_listed_codes),
            "cross_listed": len(cross_listed_codes) > 0,
            "deduplicated": False,  # set during dedup pass
        })

    return courses


def fetch_department(session, dept: str) -> list:
    url = f"{BASE_URL}/courses/{dept}/"
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            print(f"  [{dept}] HTTP {resp.status_code}")
            return []
        return parse_courses_from_html(resp.text, dept)
    except Exception as e:
        print(f"  [{dept}] Error: {e}")
        return []


def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_depts": [], "failed_depts": [], "total_courses": 0}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def deduplicate(rows: list) -> list:
    """
    Remove cross-listed duplicates. Keep the canonical listing (first dept code
    alphabetically among the cross-list group), matching paper methodology.
    """
    seen = {}  # (normalized_title, course_num) -> canonical row index

    for row in rows:
        key = (row["title"].lower().strip(), row["course_number"])
        if key not in seen:
            seen[key] = row
            row["deduplicated"] = True
        else:
            row["deduplicated"] = False

    return rows


def compute_summary(rows: list) -> dict:
    deduplicated = [r for r in rows if r["deduplicated"]]
    total = len(deduplicated)
    if total == 0:
        return {}

    prog = sum(1 for r in deduplicated if r["progressive_signal"])
    canon = sum(1 for r in deduplicated if r["western_canon_signal"])
    clim_n = sum(1 for r in deduplicated if r["climate_narrow_signal"])
    clim_b = sum(1 for r in deduplicated if r["climate_broad_signal"])

    return {
        "university": "upenn",
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "total_raw_courses": len(rows),
        "total_deduplicated": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2),
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2),
        "climate_narrow_count": clim_n,
        "climate_narrow_pct": round(100 * clim_n / total, 2),
        "climate_broad_count": clim_b,
        "climate_broad_pct": round(100 * clim_b / total, 2),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    progress = load_progress()
    completed = set(progress.get("completed_depts", []))
    failed = set(progress.get("failed_depts", []))

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (research; curriculum-dataset; contact: imvial@stanford.edu)",
        "Accept": "text/html,application/xhtml+xml",
    })

    all_rows = []

    # Load previously scraped data if resuming
    if completed and os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            all_rows = list(reader)
        print(f"Resuming: {len(all_rows)} rows already loaded from {OUTPUT_CSV}")

    new_this_run = 0
    start_time = time.time()

    for i, dept in enumerate(DEPARTMENTS):
        if dept in completed:
            continue
        if dept in failed:
            continue

        elapsed = time.time() - start_time
        print(f"[{i+1}/{len(DEPARTMENTS)}] {dept.upper()} (elapsed {elapsed:.0f}s)...", end="", flush=True)
        courses = fetch_department(session, dept)

        if courses:
            all_rows.extend(courses)
            completed.add(dept)
            new_this_run += len(courses)
            print(f" {len(courses)} courses (total {len(all_rows)})")
        else:
            failed.add(dept)
            print(f" (no courses)")

        progress["completed_depts"] = list(completed)
        progress["failed_depts"] = list(failed)
        progress["total_courses"] = len(all_rows)
        progress["last_updated"] = datetime.now().isoformat()
        save_progress(progress)

        # Write incrementally every 10 departments
        if new_this_run % 10 == 0 or len(completed) % 10 == 0:
            _write_csv(all_rows, OUTPUT_CSV)

        time.sleep(0.3)

    # Final write
    _write_csv(all_rows, OUTPUT_CSV)
    print(f"\nRaw scrape: {len(all_rows)} courses across {len(completed)} departments")

    # Deduplication pass
    print("Running deduplication pass...")
    all_rows = deduplicate(all_rows)
    deduped = [r for r in all_rows if r["deduplicated"]]
    dupes = len(all_rows) - len(deduped)
    print(f"Deduplicated: {len(all_rows)} raw -> {len(deduped)} unique ({dupes} cross-listed duplicates removed, {100*dupes/max(len(all_rows),1):.1f}%)")

    # Write deduplicated CSV
    _write_csv(all_rows, CLEAN_CSV)
    print(f"Clean CSV: {CLEAN_CSV}")

    # Compute and save summary statistics
    summary = compute_summary(all_rows)
    summary_file = f"{OUTPUT_DIR}/upenn_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n=== SUMMARY (deduplicated courses) ===")
    print(f"Total courses: {summary.get('total_deduplicated', 0)}")
    print(f"Progressive signal: {summary.get('progressive_count', 0)} ({summary.get('progressive_pct', 0):.1f}%)")
    print(f"Western canon signal: {summary.get('canon_count', 0)} ({summary.get('canon_pct', 0):.1f}%)")
    print(f"Climate (narrow): {summary.get('climate_narrow_count', 0)} ({summary.get('climate_narrow_pct', 0):.1f}%)")
    print(f"Climate (broad): {summary.get('climate_broad_count', 0)} ({summary.get('climate_broad_pct', 0):.1f}%)")

    return summary


def _write_csv(rows: list, path: str):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
