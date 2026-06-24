#!/usr/bin/env python3
"""
University of Wisconsin-Madison course catalog scraper.
URL: guide.wisc.edu/courses/{dept_slug}/
HTML: div.courseblock > p.courseblocktitle > strong > span.courseblockcode + title
      + p.courseblockdesc (description)
"""

import csv
import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup

UNIVERSITY = "wisc"
CATALOG_YEAR = "2026"
CATALOG_LABEL = "2026-2027"
BASE_URL = "https://guide.wisc.edu"
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

STEM_SLUGS = {"act_sci", "agroecol", "a_a_e", "anatomy", "anat_phy", "an_sci",
              "astron", "atm_ocn", "biochem", "bse", "biology", "biocore",
              "b_m_e", "biomdsci", "bmolchem", "b_m_i", "botany", "chem",
              "c_e", "c_i", "comp_sci", "cons_biol", "c_d_e", "crop_sci",
              "d_r_y_sci", "d_s", "e_c_e", "entom", "environ", "f_w_e",
              "food_sci", "f_s_l", "genetics", "geog", "geol", "geosci",
              "hort", "h_s_m", "i_s_y_e", "integr_bio", "kines", "l_a_s",
              "limnol", "m_e", "math", "m_d_l_e", "med_phys", "microbio",
              "m_s_e", "neurosci", "n_e", "nursing", "nutr_sci", "o_t",
              "phrm_sci", "phys_ther", "physics", "physiol", "pl_path",
              "pop_hlth", "poultry", "prev_vet", "psych", "radiol",
              "soil_sci", "soil_crop", "stat", "surgery", "toxicol",
              "vet_sci", "v_s_c_s", "wildlife", "zoology"}
HUMANITIES_SLUGS = {"afroamer", "african", "amer_ind", "art", "art_ed", "art_hist",
                    "asian_am", "asian", "asialang", "c_c", "classics",
                    "comp_lit", "dance", "dutch", "engl", "folklore",
                    "french", "german", "greek", "hebrew", "hist",
                    "hist_sci", "illibarts", "ital", "japanese", "jewish",
                    "ling", "lit_trns", "media_c_i", "music", "music_ed",
                    "musicol", "phil", "port", "russ", "scand", "slavic",
                    "spanish", "s_s_a_w", "theatre", "urb_reg_pl"}
SOCIAL_SLUGS = {"anthro", "a_f_aero", "comm_arts", "c_j", "econ", "educ",
                "educ_ldsp", "educ_pol", "edpol", "edpsych", "geog",
                "gen_b_m_s", "global_hlth", "i_r", "legalstud",
                "lib_i_s", "pol_sci", "pop_hlth", "pub_aff", "r_m_s",
                "rural_soc", "s_o_h_e", "soc", "soc_welf", "soc_work",
                "urb_reg_pl", "wom_gend"}
MEDICAL_SLUGS = {"anesthes", "anatomy", "anat_phy", "b_m_i", "biomdsci",
                 "c_h_e_m", "dermatol", "epid", "family_med", "gen_surg",
                 "global_hlth", "h_s_m", "kines", "med", "med_phys",
                 "n_e", "neurol", "neurosurg", "nursing", "nutr_sci",
                 "o_t", "obg", "ophth", "orthoped", "path",
                 "ped", "pharm", "phrm_sci", "phys_ther", "physiol",
                 "pop_hlth", "prev_vet", "psych", "pub_hlth", "radiol",
                 "surgery", "toxicol", "urology", "vet_sci"}
PROFESSIONAL_SLUGS = {"acct_i_s", "abt", "bus_admin", "bus_law", "econ",
                      "fin", "gen_bus", "i_b", "i_s_y_e", "la_r",
                      "law", "lib_i_s", "man", "mkt", "o_i_m",
                      "pub_aff", "r_e", "risk_i_s", "s_o_h_e", "soc_welf"}


def classify_area(dept_slug):
    d = dept_slug.lower()
    if d in STEM_SLUGS:
        return "STEM"
    if d in HUMANITIES_SLUGS:
        return "Humanities"
    if d in SOCIAL_SLUGS:
        return "Social Sciences"
    if d in MEDICAL_SLUGS:
        return "Medical Sciences"
    if d in PROFESSIONAL_SLUGS:
        return "Professional"
    return "Other"


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:4])
        return "graduate" if n >= 700 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def get_depts(session):
    url = f"{BASE_URL}/courses/"
    try:
        r = session.get(url, timeout=25)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = soup.select("a[href*='/courses/']")
        depts = []
        for l in links:
            href = l.get("href", "")
            m = re.search(r"/courses/([^/]+)/", href)
            if m and m.group(1):
                depts.append(m.group(1))
        return list(dict.fromkeys(depts))
    except Exception as e:
        print(f"  ERROR fetching dept list: {e}")
        return []


def parse_block(block, dept_slug):
    code_span = block.find("span", class_="courseblockcode")
    if not code_span:
        return None
    code_text = code_span.get_text(strip=True)
    # Code format: "ENGL 140" or "ENGL/THEATRE 120"
    # Take first dept code
    parts = code_text.split()
    if len(parts) < 2:
        return None
    dept = parts[0].split("/")[0].rstrip(",")
    num = parts[-1] if len(parts) > 1 else ""

    # Title: everything in strong after the code
    title_p = block.find("p", class_="courseblocktitle")
    title = ""
    if title_p:
        title_text = title_p.get_text(" ", strip=True)
        # Remove the code part: "ENGL 140 — COMM B TOPICS..."
        sep = " — "
        if sep in title_text:
            title = title_text.split(sep, 1)[1].strip()
        else:
            # Try after code
            idx = title_text.find(code_text)
            if idx >= 0:
                title = title_text[idx + len(code_text):].strip().lstrip("—").strip()

    desc_p = block.find("p", class_="courseblockdesc")
    desc = ""
    if desc_p:
        # Get text but exclude the toggle button and cb-extras
        for tag in desc_p.find_all(["button", "div"]):
            tag.decompose()
        desc = desc_p.get_text(" ", strip=True)

    full_text = f"{title} {desc}"
    return {
        "university": UNIVERSITY,
        "academic_year": CATALOG_YEAR,
        "academic_year_label": CATALOG_LABEL,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_area(dept_slug),
        "level": classify_level(num),
        "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
        "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
        "cross_listed": False,
        "deduplicated": True,
    }


def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})
    all_courses = []
    seen = set()
    failed = []

    print(f"=== University of Wisconsin-Madison Course Catalog Scraper ===")
    print(f"Catalog year: {CATALOG_LABEL}")

    depts = get_depts(session)
    print(f"Scraping {len(depts)} departments...")

    for dept in depts:
        url = f"{BASE_URL}/courses/{dept}/"
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                failed.append(dept)
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            blocks = soup.find_all("div", class_="courseblock")
            new = 0
            for b in blocks:
                c = parse_block(b, dept)
                if c:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
            if new:
                print(f"  {dept}: {new} courses")
        except Exception as e:
            print(f"  ERROR {dept}: {e}")
            failed.append(dept)
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
