#!/usr/bin/env python3
"""
JHU course catalog time-series scraper.
Scrapes 2020-21, 2025-26, and 2026-27 (current) catalogs.
Archive URL: e-catalogue.jhu.edu/archive/{YY-YY}/course-descriptions/{dept}/
Current URL: e-catalogue.jhu.edu/course-descriptions/{dept}/
"""

import csv, json, os, re, time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

VERIFY = "/root/.ccr/ca-bundle.crt"
BASE = "https://e-catalogue.jhu.edu"
OUTPUT_DIR = "/home/user/routine/data/jhu"

PROGRESSIVE_KEYWORDS = [
    "diversity","diverse","inclusion","inclusive","belonging","dei","race","racial","racism",
    "racist","anti-racist","antiracist","racialized","white supremacy","white privilege","whiteness",
    "bipoc","people of color","black lives","critical race","gender","gendered","feminist","feminism",
    "sexism","patriarchy","misogyny","queer","lgbtq","transgender","nonbinary","intersex","sexuality",
    "heteronormativity","equity","equitable","social justice","injustice","oppression","oppressive",
    "liberation","decolonize","decolonial","colonialism","colonial","postcolonial","settler colonialism",
    "identity","identities","positionality","intersectionality","privilege","marginalized",
    "marginalization","underrepresented","allyship","indigenous","native american","latinx","chicano",
    "chicana","diaspora","reparations","microaggression","implicit bias","systemic racism",
]
WESTERN_CANON_KEYWORDS = [
    "western civilization","western tradition","western thought","great books","liberal arts tradition",
    "ancient greece","ancient rome","greek philosophy","roman law","classical antiquity","greco-roman",
    "renaissance","enlightenment","medieval philosophy","reformation","shakespeare","plato","aristotle",
    "homer","dante","virgil","milton","cicero","socrates","augustine","aquinas","machiavelli","hobbes",
    "descartes","kant","hegel","locke","tocqueville","montesquieu","bible","biblical","iliad","odyssey",
    "aeneid","divine comedy","canterbury tales","leviathan","federalist","classics","classical",
]
CLIMATE_NARROW = ["climate change","global warming","greenhouse gas","carbon emission","fossil fuel","sea level rise","climate crisis"]
CLIMATE_BROAD = ["climate","sustainability","sustainable","renewable energy","environmental justice","carbon","decarbonization","net zero","clean energy","green energy","ecological","ecosystem","biodiversity"]

FIELDS = ["university","academic_year","academic_year_label","department_code","course_number","title","description","broad_area","level","progressive_signal","western_canon_signal","climate_narrow_signal","climate_broad_signal","cross_listed","deduplicated"]

YEAR_CONFIGS = [
    {"year": 2020, "label": "2020-2021", "archive_slug": "2020-21"},
    {"year": 2025, "label": "2025-2026", "archive_slug": "2025-26"},
    {"year": 2026, "label": "2026-2027", "archive_slug": None},
]


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def classify_level(course_num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(course_num))[:5])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def get_dept_links(archive_slug=None):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    if archive_slug:
        url = f"{BASE}/archive/{archive_slug}/course-descriptions/"
    else:
        url = f"{BASE}/course-descriptions/"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            h = a["href"]
            # Accept relative or absolute links to course-descriptions sub-pages
            if "/course-descriptions/" in h and h.rstrip("/") != "/course-descriptions/" and not h.endswith(".pdf"):
                if h.startswith("/"):
                    h = BASE + h
                links.append(h)
        return list(dict.fromkeys(links))
    except Exception as e:
        print(f"    Could not get dept list ({archive_slug}): {e}")
        return []


def scrape_dept(url, year, label):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return url, [], f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        courses = []
        for block in soup.find_all("div", class_="courseblock"):
            code_el = block.find("span", class_="detail-code")
            title_el = block.find("span", class_="detail-title")
            if not code_el or not title_el:
                continue
            code_raw = code_el.get_text(strip=True).rstrip(".")
            parts = code_raw.split(".")
            if len(parts) < 3:
                continue
            school = parts[0]
            dept_num = parts[1]
            course_num = parts[2]
            dept_code = f"{school}.{dept_num}"
            title = title_el.get_text(strip=True).rstrip(".")
            extras = block.find_all("p", class_="courseblockextra")
            desc = extras[0].get_text(" ", strip=True) if extras else ""
            full_text = f"{title} {desc}"
            courses.append({
                "university": "jhu",
                "academic_year": str(year),
                "academic_year_label": label,
                "department_code": dept_code,
                "course_number": course_num,
                "title": title,
                "description": desc,
                "broad_area": "Other",
                "level": classify_level(course_num),
                "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
                "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
                "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
                "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
                "cross_listed": False,
                "deduplicated": True,
            })
        return url, courses, None
    except Exception as e:
        return url, [], str(e)


def scrape_year(cfg):
    year = cfg["year"]
    label = cfg["label"]
    archive_slug = cfg["archive_slug"]
    print(f"  JHU {label} (archive={archive_slug or 'live'})...")
    links = get_dept_links(archive_slug)
    if not links:
        # fallback: use live links but replace base URL with archive prefix
        live_links = get_dept_links(None)
        if archive_slug and live_links:
            links = [l.replace("/course-descriptions/", f"/archive/{archive_slug}/course-descriptions/") for l in live_links]
        else:
            links = live_links
    print(f"    {len(links)} dept URLs")

    all_courses = []
    seen = set()
    failed = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(scrape_dept, url, year, label): url for url in links}
        for fut in as_completed(futs):
            url, courses, err = fut.result()
            dept = url.rstrip("/").split("/")[-1]
            if err and "404" in str(err):
                pass
            elif err:
                failed.append(dept)
            else:
                for c in courses:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
        time.sleep(0.05)

    total = len(all_courses)
    if total == 0:
        print(f"    No courses found for {label}")
        return None

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    prog_pct = round(100 * prog / total, 2)
    canon_pct = round(100 * canon / total, 2)
    print(f"    {total} courses | prog {prog_pct}% | canon {canon_pct}%")
    if failed:
        print(f"    Failed: {failed[:5]}")

    csv_path = f"{OUTPUT_DIR}/jhu_{year}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_courses)

    return {
        "academic_year": str(year),
        "academic_year_label": label,
        "total_courses": total,
        "progressive_pct": prog_pct,
        "canon_pct": canon_pct,
        "climate_narrow_pct": round(100 * cn / total, 2),
        "climate_broad_pct": round(100 * cb / total, 2),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("=== JHU Time Series ===")
    per_year = []
    for cfg in YEAR_CONFIGS:
        result = scrape_year(cfg)
        if result:
            per_year.append(result)
    ts = {
        "university": "jhu",
        "source": "e-catalogue.jhu.edu (archive + live)",
        "years": per_year,
    }
    with open(f"{OUTPUT_DIR}/jhu_timeseries.json", "w") as f:
        json.dump(ts, f, indent=2)
    print("\nSummary:")
    for y in per_year:
        print(f"  {y['academic_year_label']}: {y['total_courses']:,} courses, prog={y['progressive_pct']}%")


if __name__ == "__main__":
    main()
