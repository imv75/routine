#!/usr/bin/env python3
"""
West Virginia University Course Catalog Scraper.
Source: catalog.wvu.edu/undergraduate/courses/ and /graduate/courses/
Format: CourseleafCMS — all courses in a single large page.
Title pattern: "DEPT NUM.  Title.  N Hours."
"""

import csv
import json
import os
import re
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

STEM_DEPTS = {
    "aero", "agbi", "ageg", "agen", "aget", "agr", "biol", "biom", "chem",
    "cs", "cse", "ce", "ee", "evdm", "for", "geog", "geol", "hort",
    "math", "me", "mie", "mine", "nre", "phys", "stat", "wlf",
    "bch", "bcmb", "envp", "envs", "anth_biol", "wvurc",
    "bmeg", "cpeg", "ece", "eveg", "ieng", "maeg", "pnge",
    "a&vs", "avs", "div", "plsc", "soil",
}
HUMANITIES_DEPTS = {
    "engl", "hist", "phil", "reli", "art", "musi", "thea", "danc",
    "chin", "fren", "germ", "grek", "ital", "japn", "latn", "port",
    "russ", "span", "wlc", "writ", "comm", "jour", "ling",
    "clcs", "clas", "mdvl",
}
SOCIAL_DEPTS = {
    "econ", "geog", "pols", "psyc", "soc", "anth", "crj", "wmst",
    "afam", "amst", "intr", "intl", "wgss", "gss",
    "pub", "ppa",
}
MEDICAL_DEPTS = {
    "ahln", "bcmb", "hnrs", "klls", "mded", "mdim", "medi", "nurs",
    "ot", "path", "phar", "phsl", "pt", "pubh", "rsp", "vmd",
    "anat", "bphy", "dent", "epid", "hlth", "immn", "mcbi", "neuro",
    "nutr", "obgy", "ophm", "orch", "orth", "peds", "psyc_med",
    "rdio", "surg",
}
PROFESSIONAL_DEPTS = {
    "acct", "ba", "badm", "busa", "bus", "educ", "edhe", "edld", "edps",
    "edrs", "edsp", "edte", "edtl", "entk", "fin", "leid", "mgmt",
    "mkt", "ib", "ls", "law", "lsc", "rdg", "sahs", "sw", "tchl",
    "are", "ldrc", "coun",
}


def classify_dept(dept):
    d = dept.lower().replace("&", "").replace(" ", "").replace("_", "").rstrip("0123456789")
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
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def parse_courseblock(block, level_override=None):
    title_p = block.find("p", class_="courseblocktitle")
    if not title_p:
        return None
    strong = title_p.find("strong")
    title_text = strong.get_text(" ", strip=True) if strong else title_p.get_text(" ", strip=True)

    # Format: "DEPT NUM.  Title.  N Hours."
    m = re.match(
        r"([A-Z][A-Z0-9&\s]+?)\s+([\d]+[A-Z]?)\.\s+(.+?)\.\s+[\d\-]+\s+Hours?\.",
        title_text,
        re.IGNORECASE,
    )
    if not m:
        # Looser parse
        m = re.match(
            r"([A-Z][A-Z0-9&\s]+?)\s+([\d]+[A-Z]?)\.\s+(.+)",
            title_text,
        )
    if not m:
        return None

    dept = m.group(1).strip()
    num = m.group(2).strip()
    title = m.group(3).strip()
    title = re.sub(r"\.\s*[\d\-]+\s*Hours?\.?$", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\.$", "", title).strip()

    desc_p = block.find("p", class_="courseblockdesc")
    desc = desc_p.get_text(" ", strip=True) if desc_p else ""
    desc = re.sub(r"^(Description|Course Description):\s*", "", desc, flags=re.IGNORECASE)

    full_text = f"{title} {desc}"
    area = classify_dept(dept)
    level = level_override or classify_level(num)

    return {
        "university": "wvu",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
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


def scrape_wvu():
    output_dir = "/home/user/routine/data/wvu"
    os.makedirs(output_dir, exist_ok=True)

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"

    all_courses = []
    seen = set()

    pages = [
        ("https://catalog.wvu.edu/undergraduate/courses/", "undergraduate"),
        ("https://catalog.wvu.edu/graduate/courses/", "graduate"),
    ]

    for url, level_hint in pages:
        print(f"Fetching {level_hint} catalog: {url}")
        try:
            r = s.get(url, timeout=60)
            if r.status_code != 200:
                print(f"  ERROR {r.status_code}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            blocks = soup.find_all("div", class_="courseblock")
            print(f"  Found {len(blocks)} course blocks")

            new_count = 0
            for b in blocks:
                c = parse_courseblock(b, level_override=level_hint)
                if c:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new_count += 1
            print(f"  Added {new_count} unique courses")
        except Exception as e:
            print(f"  EXCEPTION: {e}")
        time.sleep(1)

    total = len(all_courses)
    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    print(f"\n=== WVU Summary ===")
    print(f"Total unique courses: {total}")
    print(f"Progressive: {prog} ({round(100*prog/total,2)}%)")
    print(f"Canon: {canon} ({round(100*canon/total,2)}%)")
    print(f"Climate narrow: {cn} | Climate broad: {cb}")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({round(100*cnt/total)}%)")

    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/wvu_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)
    print(f"\nSaved: {csv_path}")

    summary = {
        "university": "wvu",
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "catalog.wvu.edu/undergraduate/courses/ + /graduate/courses/",
        "total_courses": total,
        "progressive_count": prog,
        "progressive_pct": round(100 * prog / total, 2) if total else 0,
        "canon_count": canon,
        "canon_pct": round(100 * canon / total, 2) if total else 0,
        "climate_narrow_count": cn,
        "climate_narrow_pct": round(100 * cn / total, 2) if total else 0,
        "climate_broad_count": cb,
        "climate_broad_pct": round(100 * cb / total, 2) if total else 0,
        "by_area": area_counts,
    }
    summary_path = f"{output_dir}/wvu_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved: {summary_path}")
    return summary


if __name__ == "__main__":
    scrape_wvu()
