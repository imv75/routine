#!/usr/bin/env python3
"""Scrape Emory College catalog (static HTML, current academic year)."""

import re, csv, json, os, time
import requests
from bs4 import BeautifulSoup

PROXY = {"http": "http://127.0.0.1:34919", "https": "http://127.0.0.1:34919"}
CAFILE = "/root/.ccr/ca-bundle.crt"
BASE_URL = "https://catalog.college.emory.edu"
DEPTS_URL = f"{BASE_URL}/academics/departments/index.html"
OUT_DIR = "data/emory"
AY_YEAR = 2026
AY_LABEL = "2025-26"

PROGRESSIVE_KWS = [
    "social justice","equity","inequity","inequality","marginalized","oppression","oppressed",
    "anti-racist","antiracist","decolonial","decolonize","colonialism","postcolonial",
    "intersectionality","intersectional","privilege","whiteness","white supremacy","systemic racism",
    "structural racism","implicit bias","microaggression","allyship","diversity","inclusion",
    "inclusive","belonging","underrepresented","gender identity","gender expression","transgender",
    "non-binary","queer theory","lgbtq","heteronormativity","cisgender","patriarchy",
    "feminist","feminism","climate justice","environmental justice","racial justice",
    "indigenous knowledge","indigenous rights","land acknowledgment","reparations",
    "defund","abolitionist","abolition","restorative justice","trigger warning","safe space",
    "positionality","lived experience","epistemic","standpoint theory","critical race",
    "whiteness studies","settler colonialism","afrofuturism","diaspora studies",
    "neurodiversity","ableism","disability justice","fat studies"
]
CANON_KWS = [
    "western civilization","western canon","great books","great works","ancient greece",
    "ancient rome","classical antiquity","renaissance","enlightenment","plato","aristotle",
    "socrates","homer","virgil","dante","shakespeare","milton","locke","rousseau","kant",
    "hegel","nietzsche","marx","freud","descartes","bacon","hobbes","burke","tocqueville",
    "montaigne","cicero","augustine","aquinas","medieval philosophy","scholasticism",
    "judeo-christian","biblical tradition","greek tragedy","roman history",
    "classical literature","western philosophy","canon","masterworks","great tradition"
]

BROAD_AREA_MAP = {
    "Humanities": ["philosophy","english","literature","history","art history","music","theater",
                   "dance","classics","religious","religion","film","linguistics","creative writing",
                   "comparative literature","medieval","rhetoric","archaeology","studio"],
    "Social Sciences": ["sociology","psychology","political","economics","anthropology",
                        "geography","criminology","international","communications","public policy",
                        "social work","africana","women","gender","ethnic","latin american",
                        "asian studies","middle eastern","jewish","african american","american studies"],
    "STEM": ["mathematics","math","statistics","computer","biology","chemistry","physics",
             "geology","environmental science","astronomy","engineering","biochemistry",
             "neuroscience","data science","quantitative"],
    "Medical Sciences": ["medicine","nursing","public health","pharmacology","anatomy",
                         "physiology","epidemiology","nutrition","kinesiology","health science"],
    "Professional": ["business","accounting","finance","management","marketing","law",
                     "education","journalism","architecture","social work degree"],
}

def classify_broad_area(dept_name: str, title: str) -> str:
    combined = (dept_name + " " + title).lower()
    for area, kws in BROAD_AREA_MAP.items():
        if any(kw in combined for kw in kws):
            return area
    return "Other"

def has_kw(text: str, kws: list) -> bool:
    t = text.lower()
    return any(kw in t for kw in kws)

def get_dept_links(session):
    r = session.get(DEPTS_URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    links = []
    # Department cards use class="card card-button" with relative hrefs like "aas.html"
    for a in soup.find_all("a", class_="card"):
        href = a.get("href", "")
        if href.endswith(".html") and "index" not in href and "/" not in href:
            full = f"{BASE_URL}/academics/departments/{href}"
            dept_name = a.get_text(strip=True)
            links.append((dept_name, full))
    return links

def parse_dept_page(session, dept_name, url):
    time.sleep(0.3)
    r = session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    courses = []
    # Each course is in an accordion div with card elements
    for accordion in soup.find_all("div", class_="accordion"):
        for card in accordion.find_all("div", class_="card"):
            # Get title button
            btn = card.find("button", class_="accordion__toggle")
            if not btn:
                continue
            title_text = btn.get_text(strip=True)
            # Parse "AAS 100: Course Title" format
            m = re.match(r"^([A-Z][A-Z0-9 ]+?)\s+(\d+[A-Z]?):\s+(.+)$", title_text)
            if not m:
                continue
            dept_code = m.group(1).strip()
            course_num = m.group(2).strip()
            course_title = m.group(3).strip()

            # Get description from card-body p.card-text
            card_body = card.find("div", class_="card-body")
            description = ""
            if card_body:
                desc_p = card_body.find("p", class_="card-text")
                if desc_p:
                    description = desc_p.get_text(" ", strip=True)

            # Cross-listed
            cross_listed = False
            if card_body:
                dl = card_body.find("dl")
                if dl:
                    dts = [dt.get_text(strip=True) for dt in dl.find_all("dt")]
                    dds = [dd.get_text(strip=True) for dd in dl.find_all("dd")]
                    for dt, dd in zip(dts, dds):
                        if "Cross" in dt and dd.lower() not in ("none", ""):
                            cross_listed = True

            text_for_signal = f"{course_title} {description}"
            prog = 1 if has_kw(text_for_signal, PROGRESSIVE_KWS) else 0
            canon = 1 if has_kw(text_for_signal, CANON_KWS) else 0

            # Determine level
            try:
                num = int(re.sub(r"[^0-9]", "", course_num)[:3])
                if num < 200:
                    level = "100"
                elif num < 300:
                    level = "200"
                elif num < 400:
                    level = "300"
                elif num < 500:
                    level = "400"
                else:
                    level = "500+"
            except:
                level = "Unknown"

            courses.append({
                "university": "Emory University",
                "academic_year": AY_YEAR,
                "academic_year_label": AY_LABEL,
                "department_code": dept_code,
                "course_number": course_num,
                "title": course_title,
                "description": description,
                "broad_area": classify_broad_area(dept_name, course_title),
                "level": level,
                "progressive_signal": prog,
                "western_canon_signal": canon,
                "climate_narrow_signal": 0,
                "climate_broad_signal": 0,
                "cross_listed": 1 if cross_listed else 0,
                "deduplicated": 0,
            })

    return courses

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    session = requests.Session()
    session.proxies = PROXY
    session.verify = CAFILE
    session.headers["User-Agent"] = "Mozilla/5.0 (research scraper)"

    print("Fetching department list...")
    dept_links = get_dept_links(session)
    print(f"Found {len(dept_links)} departments")

    all_courses = []
    for i, (dept_name, url) in enumerate(dept_links, 1):
        try:
            courses = parse_dept_page(session, dept_name, url)
            all_courses.extend(courses)
            print(f"  {i}/{len(dept_links)} {dept_name}: {len(courses)} courses")
        except Exception as e:
            print(f"  {i}/{len(dept_links)} {dept_name}: ERROR {e}")

    # Deduplicate
    seen = set()
    unique = []
    for c in all_courses:
        key = (c["department_code"], c["course_number"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
        else:
            # Mark duplicates
            for u in unique:
                if (u["department_code"], u["course_number"]) == key:
                    u["deduplicated"] = 1
                    break

    print(f"\nTotal unique courses: {len(unique)}")

    # Write CSV
    out_csv = os.path.join(OUT_DIR, f"emory_{AY_YEAR}.csv")
    fieldnames = ["university","academic_year","academic_year_label","department_code",
                  "course_number","title","description","broad_area","level",
                  "progressive_signal","western_canon_signal","climate_narrow_signal",
                  "climate_broad_signal","cross_listed","deduplicated"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(unique)

    prog_pct = round(100 * sum(c["progressive_signal"] for c in unique) / max(len(unique), 1), 2)
    canon_pct = round(100 * sum(c["western_canon_signal"] for c in unique) / max(len(unique), 1), 2)
    print(f"Saved {out_csv}: {len(unique)} courses (prog={prog_pct}%, canon={canon_pct}%)")

    # Write summary
    summary = {
        "university": "Emory University",
        "short_name": "emory",
        "source": "catalog.college.emory.edu",
        "note": "Emory College of Arts & Sciences static HTML catalog. Current year only (HTML); prior years are PDFs.",
        "years": {
            str(AY_YEAR): {
                "catalog_year": AY_YEAR,
                "label": AY_LABEL,
                "courses": len(unique),
                "progressive_pct": prog_pct,
                "western_canon_pct": canon_pct,
                "file": f"emory_{AY_YEAR}.csv"
            }
        },
        "total_courses": len(unique),
        "catalog_years": 1,
    }
    with open(os.path.join(OUT_DIR, "emory_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("Saved emory_summary.json")

if __name__ == "__main__":
    main()
