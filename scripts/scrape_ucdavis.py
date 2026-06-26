#!/usr/bin/env python3
"""
UC Davis Course Catalog Scraper.
Source: catalog.ucdavis.edu/courses-subject-code/{dept}/
Format: CourseleafCMS detail format with h3 > span.detail-code/title, p.courseblockextra
"""

import csv, json, os, re, time, requests
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
    "eae", "apc", "anb", "abi", "abg", "ang", "ans", "abt", "ead", "bic",
    "bis", "bim", "bme", "cbe", "chm", "che", "cls", "cse", "ecs", "eel",
    "ent", "env", "evo", "fst", "gdb", "geo", "ggb", "mat", "mec", "mes",
    "mps", "neu", "nsc", "oar", "pbg", "phs", "pla", "plb", "plp",
    "pts", "sta", "ssm", "vmb", "vme",
}
HUMANITIES_DEPTS = {
    "ara", "arb", "art", "cla", "chi", "chn", "com", "eas", "eng", "fre",
    "ger", "grk", "his", "ita", "jpn", "kor", "lat", "lin", "mus", "phi",
    "por", "rel", "rus", "spa", "tcs", "thea", "wri",
}
SOCIAL_DEPTS = {
    "ams", "ant", "are", "cmm", "crm", "ecs", "edu", "eco", "geo_soc",
    "glb", "gov", "int", "mss", "pol", "psc", "psy", "sas", "soc", "ssm",
    "sts", "wms",
}
MEDICAL_DEPTS = {
    "ane", "apc", "bim", "dnt", "ept", "hlt", "mdc", "med", "nro", "nur",
    "oph", "ort", "osr", "pbs", "phr", "phs", "pmr", "ptx", "rds", "sas",
    "sph", "sur", "vmb", "vme", "vmc", "vpa", "vph", "vsr",
}
PROFESSIONAL_DEPTS = {
    "acc", "bax", "bus", "edu", "ldp", "law", "lda", "mbm", "mgt", "mkt",
    "oad", "ppa", "pub", "soc_wk", "ssm_pro",
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


def parse_ucd_block(block):
    code_span = block.find("span", class_="detail-code")
    title_span = block.find("span", class_="detail-title")
    
    if not code_span:
        return None
    
    code_text = code_span.get_text(" ", strip=True).strip()
    title_text = title_span.get_text(" ", strip=True).lstrip("—- ").strip() if title_span else ""
    
    m = re.match(r"^(.*?)\s+([\d]+[A-Z]?)\s*$", code_text)
    if not m:
        return None
    
    dept = m.group(1).strip()
    num = m.group(2).strip()
    title = re.sub(r"\s*\(\d[\d\-]* units?\)\s*$", "", title_text, flags=re.IGNORECASE).strip()
    
    # Description: first p.courseblockextra
    desc_p = block.find("p", class_="courseblockextra")
    desc = ""
    if desc_p:
        # Remove "Course Description:" prefix
        desc = re.sub(r"Course Description:\s*", "", desc_p.get_text(" ", strip=True), flags=re.IGNORECASE)
    
    full_text = f"{title} {desc}"
    area = classify_dept(dept)
    level = classify_level(num)
    
    return {
        "university": "ucdavis",
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


def get_departments():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    r = s.get("https://catalog.ucdavis.edu/courses-subject-code/", timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")
    pc = soup.find("div", class_="page_content") or soup
    depts = []
    for a in pc.find_all("a", href=True):
        m = re.match(r"^/courses-subject-code/([^/]+)/?$", a["href"])
        if m and m.group(1) not in ("", "course-search", "about-courses"):
            depts.append(m.group(1))
    return list(dict.fromkeys(depts))


def scrape_dept(dept_slug):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    url = f"https://catalog.ucdavis.edu/courses-subject-code/{dept_slug}/"
    try:
        r = s.get(url, timeout=20)
        if r.status_code != 200:
            return dept_slug, [], f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for b in blocks:
            c = parse_ucd_block(b)
            if c:
                courses.append(c)
        return dept_slug, courses, None
    except Exception as e:
        return dept_slug, [], str(e)


def scrape_ucdavis():
    output_dir = "/home/user/routine/data/ucdavis"
    os.makedirs(output_dir, exist_ok=True)
    print("=== UC Davis Course Catalog Scraper ===")
    depts = get_departments()
    print(f"Found {len(depts)} department slugs")

    all_courses = []
    seen = set()
    failed = []

    with ThreadPoolExecutor(max_workers=8) as ex:
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
                    print(f"  {dept.upper()}: {new} courses")
            time.sleep(0.05)

    total = len(all_courses)
    if not total:
        print("No courses found!")
        return {}

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    print(f"\n=== UC Davis Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({round(100*prog/total,2)}%) | Canon: {canon} ({round(100*canon/total,2)}%)")
    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed[:20])}")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt} ({round(100*cnt/total)}%)")

    fields = ["university","academic_year","academic_year_label","department_code",
              "course_number","title","description","broad_area","level",
              "progressive_signal","western_canon_signal","climate_narrow_signal",
              "climate_broad_signal","cross_listed","deduplicated"]
    csv_path = f"{output_dir}/ucdavis_2026.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_courses)

    summary = {
        "university": "ucdavis", "academic_year": "2026",
        "academic_year_label": "2026-2027",
        "source": "catalog.ucdavis.edu/courses-subject-code/",
        "total_courses": total,
        "progressive_count": prog, "progressive_pct": round(100*prog/total,2),
        "canon_count": canon, "canon_pct": round(100*canon/total,2),
        "climate_narrow_count": cn, "climate_narrow_pct": round(100*cn/total,2),
        "climate_broad_count": cb, "climate_broad_pct": round(100*cb/total,2),
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(f"{output_dir}/ucdavis_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: {csv_path}")
    return summary


if __name__ == "__main__":
    scrape_ucdavis()
