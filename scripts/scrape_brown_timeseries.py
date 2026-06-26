#!/usr/bin/env python3
"""
Brown University course catalog time-series scraper.
Scrapes 2020-21, 2025-26, and 2026-27 (current) catalogs.
Archive URL pattern: bulletin.brown.edu/archive/{YY-YY}/{dept_path}/
Current URL pattern: bulletin.brown.edu/{dept_path}/
"""

import csv, json, os, re, time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

VERIFY = "/root/.ccr/ca-bundle.crt"
BASE = "https://bulletin.brown.edu"
OUTPUT_DIR = "/home/user/routine/data/brown"

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
    {"year": 2026, "label": "2026-2027", "archive_slug": None},  # live catalog
]


def check_kw(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def classify_level(course_code):
    m = re.search(r"\d+", course_code.split()[-1] if " " in course_code else course_code)
    if m:
        try:
            return "graduate" if int(m.group()) >= 2000 else "undergraduate"
        except Exception:
            pass
    return "undergraduate"


def get_dept_paths(archive_slug=None):
    """Get department paths from either live or archive departments index."""
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    paths = set()
    if archive_slug:
        index_urls = [
            f"{BASE}/archive/{archive_slug}/departments-centers-programs-institutes/",
            f"{BASE}/archive/{archive_slug}/",
        ]
    else:
        index_urls = [
            f"{BASE}/departments-centers-programs-institutes/",
            f"{BASE}/universitycourses/",
        ]
    for url in index_urls:
        try:
            r = s.get(url, timeout=15, verify=VERIFY)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            content = soup.find("div", id="textcontainer") or soup.body
            if not content:
                continue
            for a in content.find_all("a", href=True):
                h = a["href"]
                # Extract the base path (strip archive prefix if present)
                if archive_slug and f"/archive/{archive_slug}/" in h:
                    h = h.replace(f"/archive/{archive_slug}", "")
                if (h.startswith("/") and h != "/" and not h.startswith("/#")
                        and not h.startswith("/azindex") and not h.startswith("/pdf")
                        and "." not in h.split("/")[-1]):
                    paths.add(h)
        except Exception:
            pass
    return sorted(paths)


def scrape_path(path, archive_slug, year, label):
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120"
    if archive_slug:
        url = f"{BASE}/archive/{archive_slug}{path}"
    else:
        url = f"{BASE}{path}"
    try:
        r = s.get(url, timeout=20, verify=VERIFY)
        if r.status_code != 200:
            return path, {}, f"HTTP {r.status_code}"
        soup = BeautifulSoup(r.text, "html.parser")
        courses = {}
        for block in soup.find_all("div", class_="courseblock"):
            title_p = block.find("p", class_="courseblocktitle")
            if not title_p:
                continue
            code = title_p.get("data-code", "").strip()
            if not code:
                txt = title_p.get_text(strip=True)
                m = re.match(r"^([A-Z]+\s+[\d]+[A-Z]?)[.\s]", txt)
                code = m.group(1).strip() if m else ""
            if not code:
                continue
            title_text = title_p.get_text(strip=True)
            m = re.match(r"^[A-Z]+\s+[\dA-Z]+[.]\s*(.+)$", title_text)
            title = m.group(1).rstrip(".").strip() if m else title_text
            desc_p = block.find("p", class_="courseblockdesc")
            desc = desc_p.get_text(" ", strip=True) if desc_p else ""
            parts = code.split()
            dept_code = parts[0] if parts else code
            course_num = parts[1] if len(parts) > 1 else ""
            full_text = f"{title} {desc}"
            courses[code] = {
                "university": "brown",
                "academic_year": str(year),
                "academic_year_label": label,
                "department_code": dept_code,
                "course_number": course_num,
                "title": title,
                "description": desc,
                "broad_area": "Other",
                "level": classify_level(code),
                "progressive_signal": check_kw(full_text, PROGRESSIVE_KEYWORDS),
                "western_canon_signal": check_kw(full_text, WESTERN_CANON_KEYWORDS),
                "climate_narrow_signal": check_kw(full_text, CLIMATE_NARROW),
                "climate_broad_signal": check_kw(full_text, CLIMATE_BROAD),
                "cross_listed": False,
                "deduplicated": True,
            }
        return path, courses, None
    except Exception as e:
        return path, {}, str(e)


def scrape_year(cfg):
    year = cfg["year"]
    label = cfg["label"]
    archive_slug = cfg["archive_slug"]
    print(f"  Brown {label} (archive={archive_slug or 'live'})...")
    paths = get_dept_paths(archive_slug)
    if not paths:
        # fallback: use live dept paths but prepend archive prefix
        paths = get_dept_paths(None)
    print(f"    {len(paths)} paths")

    all_courses = {}
    failed = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(scrape_path, p, archive_slug, year, label): p for p in paths}
        for fut in as_completed(futs):
            p, courses, err = fut.result()
            if err and "404" in str(err):
                pass  # silently skip 404 (dept didn't exist in that year)
            elif err:
                failed.append(p)
            else:
                for code, c in courses.items():
                    if code not in all_courses:
                        all_courses[code] = c
        time.sleep(0.05)

    course_list = list(all_courses.values())
    total = len(course_list)
    if total == 0:
        print(f"    No courses found for {label}")
        return None

    prog = sum(1 for c in course_list if c["progressive_signal"])
    canon = sum(1 for c in course_list if c["western_canon_signal"])
    cn = sum(1 for c in course_list if c["climate_narrow_signal"])
    cb = sum(1 for c in course_list if c["climate_broad_signal"])
    prog_pct = round(100 * prog / total, 2)
    canon_pct = round(100 * canon / total, 2)
    print(f"    {total} courses | prog {prog_pct}% | canon {canon_pct}%")
    if failed:
        print(f"    Failed: {failed[:5]}")

    csv_path = f"{OUTPUT_DIR}/brown_{year}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(course_list)

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
    print("=== Brown University Time Series ===")
    per_year = []
    for cfg in YEAR_CONFIGS:
        result = scrape_year(cfg)
        if result:
            per_year.append(result)
    ts = {
        "university": "brown",
        "source": "bulletin.brown.edu (archive + live)",
        "years": per_year,
    }
    with open(f"{OUTPUT_DIR}/brown_timeseries.json", "w") as f:
        json.dump(ts, f, indent=2)
    print("\nSummary:")
    for y in per_year:
        print(f"  {y['academic_year_label']}: {y['total_courses']:,} courses, prog={y['progressive_pct']}%")


if __name__ == "__main__":
    main()
