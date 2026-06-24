#!/usr/bin/env python3
"""
Generic Acalog CMS course catalog scraper.
Handles multiple common Acalog HTML variants.
Usage: python3 scrape_acalog_generic.py <university_config>
"""

import csv
import json
import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup

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


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def classify_level_num(course_num, threshold=500):
    try:
        num = int(re.sub(r"[^0-9]", "", str(course_num))[:5])
        return "graduate" if num >= threshold else "undergraduate"
    except Exception:
        return "undergraduate"


def parse_block_standard(block, university, catalog_year, catalog_label, area_classifier):
    """Parse standard Acalog courseblock with p.courseblocktitle + p.courseblockdesc."""
    title_p = block.find("p", class_="courseblocktitle") or block.find("div", class_="courseblocktitle")
    if not title_p:
        return None
    title_text = title_p.get_text(" ", strip=True)

    # Various formats:
    # "DEPT 1234: Course Title (N credits)"
    # "DEPT 1234  Course Title Credits: N"
    # "DEPT 1234. Course Title. N Credits."
    m = re.match(r"([A-Z][A-Z0-9_&]*)\s+([\w]+)[:\.\s]+(.+?)(?:\.\s*\d+|\s+Credits?|\s+\(\d+\))", title_text, re.IGNORECASE)
    if not m:
        m = re.match(r"([A-Z][A-Z0-9_&]*)\s+([\w]+)[:\.\s]+(.+)", title_text)
    if not m:
        return None

    dept = m.group(1).strip()
    num = m.group(2).strip()
    title = m.group(3).strip()
    title = re.sub(r"\s*\.\s*\d+[\-\d]*\s*Credits?\.?$", "", title).strip()
    title = re.sub(r"\s+\(\d+\)$", "", title).strip()

    desc_p = block.find("p", class_="courseblockdesc") or block.find("div", class_="courseblockdesc")
    if not desc_p:
        # Try prereq paragraph
        desc_p = block.find("p", class_="prereq")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""
    # Clean up "Description:" prefix
    desc = re.sub(r"^(Description|Course Description):\s*", "", desc, flags=re.IGNORECASE)

    full_text = f"{title} {desc}"
    area = area_classifier(dept)
    level = classify_level_num(num)

    return {
        "university": university,
        "academic_year": catalog_year,
        "academic_year_label": catalog_label,
        "department_code": dept,
        "course_number": num,
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


def scrape_university(config):
    university = config["university"]
    catalog_year = config["catalog_year"]
    catalog_label = config["catalog_label"]
    base_url = config["base_url"]
    dept_url_pattern = config["dept_url_pattern"]  # e.g. "/azcourses/{dept}/"
    departments = config["departments"]
    area_classifier = config["area_classifier"]
    output_dir = f"/home/user/routine/data/{university}"
    os.makedirs(output_dir, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (academic research crawler)"})

    all_courses = []
    seen = set()
    failed = []

    print(f"=== {config.get('name', university)} Course Catalog Scraper ===")
    print(f"Catalog year: {catalog_label}")
    print(f"Scraping {len(departments)} departments...\n")

    for dept in departments:
        url = base_url + dept_url_pattern.format(dept=dept)
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                failed.append(dept)
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            blocks = soup.find_all("div", class_="courseblock")
            new = 0
            for b in blocks:
                c = parse_block_standard(b, university, catalog_year, catalog_label, area_classifier)
                if c:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
            if new:
                print(f"  {dept.upper()}: {new} courses")
        except Exception as e:
            print(f"  ERROR {dept}: {e}")
            failed.append(dept)
        time.sleep(0.25)

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:30])}")

    output_csv = f"{output_dir}/{university}_{catalog_year}.csv"
    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": university, "academic_year": catalog_year,
        "academic_year_label": catalog_label, "total_courses": total,
        "progressive_count": prog, "progressive_pct": round(100*prog/total, 2) if total else 0,
        "canon_count": canon, "canon_pct": round(100*canon/total, 2) if total else 0,
        "climate_narrow_count": cn, "climate_narrow_pct": round(100*cn/total, 2) if total else 0,
        "climate_broad_count": cb, "climate_broad_pct": round(100*cb/total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(f"{output_dir}/{university}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({100*cnt//total if total else 0}%)")
    return summary


# ─── Iowa State University ───────────────────────────────────────────────────

def isu_area(dept):
    dept = dept.lower()
    STEM = {"aer_e", "bbmb", "bcb", "bcbio", "biol", "bme", "b_m_s", "ch_e", "chem",
             "com_s", "cpr_e", "c_e", "clsci", "datascience", "dsn_s", "e_e", "eeb",
             "eeob", "engr", "e_m", "ent", "env_e", "ensci", "game", "gdcb", "gen",
             "genet", "geol", "hci", "hphy", "i_e", "imbio", "math", "mat_e", "m_s_e",
             "m_e", "mteor", "micro", "mcdb", "neuro", "phys", "plbio", "pl_p", "s_e",
             "stat", "tox", "wesep", "ai", "astro", "bcbio", "cybersecurity",
             "cybersecurityengineering"}
    HUMANITIES = {"engl", "art", "arted", "art_h", "chin", "cl_st", "dance", "des",
                  "frnch", "ger", "hist", "italian", "japn", "latn", "ling", "ling",
                  "music", "perf", "phil", "port", "relig", "rus", "span", "thtre",
                  "wlc", "worldfilmstudies", "us_ls", "arabc", "asl"}
    SOCIAL = {"af_am", "am_in", "anthr", "comst", "econ", "intst", "jl_mc", "pol_s",
              "psych", "soc", "wgs", "gl_st"}
    MEDICAL = {"b_m_s", "a_tr", "diet", "fs_hn", "hd_fs", "h_s", "ihs", "kin",
               "nursing", "nutrs", "sp_cm", "tox", "v_c_s", "vdpam", "v_mpm", "v_pth",
               "wfce", "health", "hhsci", "hcm"}
    PROFESSIONAL = {"acct", "actuarialscience", "advrt", "aeshm", "ageds", "agron",
                    "an_s", "abe", "a_m_d", "arch", "afas", "ath", "bpm_i", "busad",
                    "comdv", "c_dev", "con_e", "ecp", "ecfp", "edadm", "el_ps",
                    "education", "event", "fdm", "ffp", "fin", "for", "geron", "globe",
                    "gr_st", "artgr", "hg_ed", "hort", "hsp_m", "igs", "ind_d", "artid",
                    "ia_ll", "l_a", "la", "ld_st", "lls", "las", "lib", "mis", "mgmt",
                    "mkt", "m_s", "n_s", "nrem", "ots", "scm", "sp_ed", "smc", "stb",
                    "susag", "sustainableenvironments", "trans", "tsm", "u_st", "urp",
                    "urbandesign", "uxd", "wise", "yth", "publicrelations", "resev",
                    "fceds", "digitalstorytelling", "digitalandprecisionagriculture",
                    "dh", "entsp"}
    if dept in STEM:
        return "STEM"
    if dept in HUMANITIES:
        return "Humanities"
    if dept in SOCIAL:
        return "Social Sciences"
    if dept in MEDICAL:
        return "Medical Sciences"
    if dept in PROFESSIONAL:
        return "Professional"
    return "Other"


ISU_DEPTS = [
    "acct", "actuarialscience", "advrt", "aer_e", "af_am", "abe", "ageds",
    "agron", "afas", "am_in", "asl", "an_s", "anthr", "aeshm", "a_m_d",
    "arabc", "arch", "art", "arted", "art_h", "ai", "astro", "ath", "a_tr",
    "bbmb", "bcb", "bcbio", "biol", "bme", "b_m_s", "busad", "ch_e", "chem",
    "chin", "c_e", "cl_st", "clsci", "comst", "comdv", "c_dev", "cpr_e",
    "com_s", "con_e", "criminaljustice", "cybersecurity",
    "cybersecurityengineering", "dance", "datascience", "des", "dsn_s", "diet",
    "digitalandprecisionagriculture", "dh", "digitalstorytelling", "ecp", "ecfp",
    "eeb", "eeob", "econ", "edadm", "el_ps", "education", "e_e", "engr",
    "e_m", "engl", "ent", "entsp", "env_e", "ensci", "env_s", "event",
    "fceds", "ffp", "fdm", "fin", "fs_hn", "for", "frnch", "game", "gdcb",
    "gen", "genet", "geol", "ger", "geron", "globe", "gr_st", "artgr",
    "hhsci", "hcm", "h_s", "hg_ed", "hist", "hon", "hort", "hsp_m", "hci",
    "hd_fs", "imbio", "ind_d", "artid", "i_e", "igs", "ihs", "intst",
    "ia_ll", "italian", "jl_mc", "kin", "l_a", "latn", "la", "las", "ld_st",
    "lls", "lib", "ling", "mis", "mgmt", "mkt", "mat_e", "m_s_e", "math",
    "m_e", "mteor", "micro", "m_s", "mcdb", "music", "nrem", "n_s", "neuro",
    "nursing", "nutrs", "ots", "perf", "phil", "phys", "plbio", "pl_p",
    "pol_s", "port", "psych", "publicrelations", "relig", "resev", "rus",
    "bpm_i", "stb", "soc", "s_e", "span", "sp_ed", "sp_cm", "smc", "stat",
    "scm", "susag", "sustainableenvironments", "tsm", "thtre", "tox", "trans",
    "u_st", "urp", "urbandesign", "uxd", "us_ls", "v_c_s", "vdpam", "v_mpm",
    "v_pth", "wfce", "wesep", "wise", "wgs", "worldfilmstudies", "wlc", "yth",
]

ISU_CONFIG = {
    "name": "Iowa State University",
    "university": "iastate",
    "catalog_year": "2026",
    "catalog_label": "2026-2027",
    "base_url": "https://catalog.iastate.edu",
    "dept_url_pattern": "/azcourses/{dept}/",
    "departments": ISU_DEPTS,
    "area_classifier": isu_area,
}


# ─── Oklahoma State University ────────────────────────────────────────────────

def okstate_area(dept):
    dept = dept.lower()
    STEM = {"bioc", "biol", "biom", "bae", "ban", "che", "chem", "cs", "ecen",
             "eet", "engr", "ensc", "enpp", "ento", "envr", "fdsc", "frns",
             "gene", "geog", "geol", "glhe", "iem", "itox", "mae", "mse", "math",
             "micr", "nrem", "nsci", "pete", "phys", "plnt", "pbio", "plp", "stat"}
    HUMANITIES = {"afam", "amst", "arb", "art", "chin", "danc", "engl", "fren", "grmn",
                  "grek", "hbrw", "hist", "japn", "jazz", "krn", "latn", "ling",
                  "ll", "llce", "musi", "msin", "phil", "rel", "russ", "span", "th"}
    SOCIAL = {"agec", "amis", "anth", "bcom", "cdis", "econ", "glst", "gs", "gwst",
              "mc", "mmj", "pols", "psyc", "soc", "sc", "spm"}
    MEDICAL = {"cbsc", "cdis", "cpsy", "ffp", "hdfs", "hlth", "hhp", "hca", "mat",
               "mph", "nurs", "pa", "soil", "spsy", "vcs", "vme", "vmed", "waed"}
    PROFESSIONAL = {"acct", "aero", "agin", "agcm", "aged", "aecl", "agle", "ast",
                    "ag", "aadm", "astr", "aved", "badm", "bhon", "bcom", "cet",
                    "cied", "cps", "dm", "dhm", "divr", "edhs", "edle", "epsy",
                    "edtc", "etm", "eee", "entm", "fdep", "femp", "fpst", "fsep",
                    "fin", "geng", "gent", "gted", "grad", "hesa", "honr", "hort",
                    "htm", "la", "lbsc", "lsb", "leis", "mgmt", "msis", "mktg",
                    "mba", "met", "mero", "mlsc", "orgl", "oos", "psaf", "rm",
                    "rmrt", "rt", "rems", "res", "spch", "scfd", "smed", "sped",
                    "univ"}
    if dept in STEM:
        return "STEM"
    if dept in HUMANITIES:
        return "Humanities"
    if dept in SOCIAL:
        return "Social Sciences"
    if dept in MEDICAL:
        return "Medical Sciences"
    if dept in PROFESSIONAL:
        return "Professional"
    return "Other"


OKSTATE_DEPTS = [
    "acct", "aero", "afam", "agin", "agcm", "agec", "aged", "aecl", "agle",
    "ast", "ag", "amis", "asl", "amst", "ansi", "anth", "arb", "arch", "art",
    "a_s", "aadm", "astr", "aved", "bioc", "biol", "biom", "bae", "badm",
    "ban", "bcom", "bhon", "che", "chem", "chin", "cive", "cps", "cdis",
    "cbsc", "cs", "cet", "cpsy", "cied", "danc", "dm", "dhm", "divr", "econ",
    "edhs", "edle", "epsy", "edtc", "ecen", "eet", "etm", "engr", "ensc",
    "engl", "entm", "enpp", "ento", "eee", "envr", "ffp", "fin", "femp",
    "fpst", "fsep", "fdsc", "frns", "fdep", "fren", "gwst", "geng", "gent",
    "gene", "geog", "geol", "grmn", "gted", "glhe", "glst", "gs", "grad",
    "grek", "hlth", "hhp", "hca", "hbrw", "hesa", "hist", "honr", "hort",
    "htm", "hdfs", "iem", "itox", "japn", "jazz", "krn", "la", "llce",
    "ll", "latn", "lsb", "leis", "lbsc", "mgmt", "msis", "mktg", "mc",
    "mat", "mba", "mph", "mse", "math", "mae", "met", "mero", "micr",
    "mlsc", "mmj", "musi", "msin", "nrem", "nurs", "nsci", "oos", "orgl",
    "pete", "phil", "pa", "phys", "bot", "plp", "plnt", "pols", "psyc",
    "psaf", "rmrt", "rm", "rt", "rel", "res", "rems", "russ", "spsy",
    "smed", "scfd", "soc", "soil", "span", "sped", "spch", "spm", "stat",
    "sc", "th", "univ", "vcs", "vme", "vmed", "waed",
]

OKSTATE_CONFIG = {
    "name": "Oklahoma State University",
    "university": "okstate",
    "catalog_year": "2026",
    "catalog_label": "2026-2027",
    "base_url": "https://catalog.okstate.edu",
    "dept_url_pattern": "/courses/{dept}/",
    "departments": OKSTATE_DEPTS,
    "area_classifier": okstate_area,
}


# ─── Colorado State University ────────────────────────────────────────────────

def csu_area(dept):
    dept = dept.lower()
    STEM = {"ab", "aneq", "ats", "aa", "biom", "bms", "chem", "cive", "cs",
             "dsci", "engr", "geol", "hort", "math", "mech", "ph", "staa"}
    HUMANITIES = {"art", "e", "hist", "mu", "phil", "th", "spcm", "lspa", "amst"}
    SOCIAL = {"anth", "econ", "pols", "psy", "soc", "sowk"}
    MEDICAL = {"am"}
    PROFESSIONAL = {"aead", "aeba", "act", "as", "aged", "arec", "aged", "con",
                    "d", "fin", "hort"}
    if dept in STEM:
        return "STEM"
    if dept in HUMANITIES:
        return "Humanities"
    if dept in SOCIAL:
        return "Social Sciences"
    if dept in MEDICAL:
        return "Medical Sciences"
    if dept in PROFESSIONAL:
        return "Professional"
    return "Other"


CSU_DEPTS = [
    "aead", "aeba", "act", "as", "ab", "aged", "agri", "arec", "amst",
    "aneq", "anth", "am", "staa", "art", "aa", "ats", "biom", "bms",
    "chem", "cive", "spcm", "cs", "con", "d", "dsci", "econ", "engr",
    "e", "fin", "geol", "hist", "hort", "math", "mech", "mu", "phil",
    "ph", "pols", "psy", "sowk", "soc", "lspa", "th",
]

CSU_CONFIG = {
    "name": "Colorado State University",
    "university": "colostate",
    "catalog_year": "2026",
    "catalog_label": "2026-2027",
    "base_url": "https://catalog.colostate.edu",
    "dept_url_pattern": "/general-catalog/courses-az/{dept}/",
    "departments": CSU_DEPTS,
    "area_classifier": csu_area,
}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "iastate"
    configs = {
        "iastate": ISU_CONFIG,
        "okstate": OKSTATE_CONFIG,
        "colostate": CSU_CONFIG,
    }
    if target not in configs:
        print(f"Unknown target: {target}. Choose from: {list(configs.keys())}")
        sys.exit(1)
    scrape_university(configs[target])
