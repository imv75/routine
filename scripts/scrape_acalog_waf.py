#!/usr/bin/env python3
"""
Acalog CMS scraper that bypasses AWS WAF JavaScript challenge.

Strategy:
1. Use Playwright once to pass WAF challenge and get cookies
2. Use requests with those cookies for all subsequent page fetches
3. Parse courses from HTML

Usage: python3 scrape_acalog_waf.py <university_key>
"""

import csv
import json
import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed: pip install playwright")
    sys.exit(1)

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


def check_keywords(text, kws):
    t = text.lower()
    return any(k in t for k in kws)


def default_area(dept):
    d = dept.lower().strip().split()[0]
    STEM = {"math","phys","phy","chem","biol","bio","cs","cosc","csci","ece","ee","me",
            "ce","ae","engr","stat","astr","ast","geol","geog","bioc","biochem","micr",
            "neur","mbio","cbio","envs","enve","envsc","bmsc","mse","mtle","mae","che",
            "cheg","chbe","civl","cive","phy","sci","bme","ie","ise","itws","nucl",
            "nsc","csc","chm","nsci","mast","dsst","ensc","enwc","anfs","bmsc",}
    HUMANITIES = {"engl","hist","phil","art","arth","artc","mus","musc","thea","thtr",
                  "drama","dram","lit","clas","latn","gree","grek","fren","germ","span",
                  "ital","port","russ","slav","chin","japn","ling","lang","rel","rels",
                  "relg","reli","arch","comm","jou","jour","wrt","crit","hass","enc",
                  "lhp","egl","lest","rees","klpa","clcs","fst","mdv","arabk","arb",}
    SOCIAL = {"anth","econ","pols","pol","psyc","psy","soc","soci","wgss","wgst","woms",
              "afam","afst","aaas","amst","lase","isla","glst","socy","crju","crim","com",}
    MEDICAL = {"nurs","kine","kin","kaap","hlth","hlpr","ntdt","nutr","med","pharm","pubh",
               "mph","rhs","atr","hdfs","ntr",}
    PROFESSIONAL = {"acct","fin","mgt","mgmt","mkt","buad","bus","law","educ","edlf",
                    "edhe","swk","sowk","plan","hrim","fash","jour","journ","adv","hca",}
    if d in STEM: return "STEM"
    if d in HUMANITIES: return "Humanities"
    if d in SOCIAL: return "Social Sciences"
    if d in MEDICAL: return "Medical Sciences"
    if d in PROFESSIONAL: return "Professional"
    return "Other"


def classify_level(num_str, grad_threshold=500):
    nums = re.findall(r'\d+', str(num_str))
    if nums:
        try:
            n = int(nums[0])
            return "graduate" if n >= grad_threshold else "undergraduate"
        except Exception:
            pass
    return "undergraduate"


# University configurations
CONFIGS = {
    "unlv": {
        "name": "University of Nevada Las Vegas",
        "base": "https://catalog.unlv.edu",
        "catoid": 53,
        "courses_navoid": 17221,
        "grad_threshold": 700,
    },
    "rpi": {
        "name": "Rensselaer Polytechnic Institute",
        "base": "https://catalog.rpi.edu",
        "catoid": 33,
        "courses_navoid": 891,
        "grad_threshold": 4000,
    },
    "utk": {
        "name": "University of Tennessee Knoxville",
        "base": "https://catalog.utk.edu",
        "catoid": 56,
        "courses_navoid": 12117,
        "grad_threshold": 500,
    },
    "lsu": {
        "name": "Louisiana State University",
        "base": "https://catalog.lsu.edu",
        "catoid": 35,
        "courses_navoid": 3486,
        "grad_threshold": 4000,
    },
    "ttu": {
        "name": "Texas Tech University",
        "base": "https://catalog.ttu.edu",
        "catoid": 26,
        "courses_navoid": 2326,
        "grad_threshold": 5000,
    },
    "udel": {
        "name": "University of Delaware",
        "base": "https://catalog.udel.edu",
        "catoid": 97,
        "courses_navoid": 35898,
        "grad_threshold": 600,
    },
    "uva": {
        "name": "University of Virginia",
        "base": "https://records.ureg.virginia.edu",
        "catoid": 72,
        "courses_navoid": 6679,
        "grad_threshold": 5000,
    },
    "stonybrook": {
        "name": "Stony Brook University",
        "base": "https://catalog.stonybrook.edu",
        "catoid": None,  # Will discover
        "courses_navoid": None,
        "grad_threshold": 500,
    },
    "usc": {
        "name": "University of Southern California",
        "base": "https://catalogue.usc.edu",
        "catoid": 22,
        "courses_navoid": None,
        "grad_threshold": 500,
    },
}


def get_waf_cookies(base_url, catoid, courses_navoid):
    """Use Playwright to pass AWS WAF challenge and return cookies."""
    print(f"Getting WAF cookies for {base_url}...")
    chromium_path = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

    cookies_dict = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--single-process", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        # First, hit the home page to warm up WAF
        try:
            home_url = f"{base_url}/index.php?catoid={catoid}" if catoid else base_url + "/"
            print(f"  Warming up at {home_url}...")
            page.goto(home_url, wait_until="networkidle")
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  Warning on home page: {e}")

        # Now navigate to the courses page
        try:
            courses_url = f"{base_url}/content.php?catoid={catoid}&navoid={courses_navoid}"
            print(f"  Loading courses page: {courses_url}")
            page.goto(courses_url, wait_until="networkidle")
            page.wait_for_timeout(4000)

            page_size = len(page.content())
            print(f"  Courses page loaded: {page_size} bytes")

            # Get all cookies
            all_cookies = context.cookies()
            for c in all_cookies:
                cookies_dict[c["name"]] = c["value"]
            print(f"  Got {len(cookies_dict)} cookies: {list(cookies_dict.keys())}")

            # Get department links from the rendered page
            dept_links = get_dept_links_from_page(page, base_url, catoid)
            print(f"  Found {len(dept_links)} department links")

        except Exception as e:
            print(f"  Error on courses page: {e}")
            dept_links = []

        browser.close()

    return cookies_dict, dept_links


def get_dept_links_from_page(page, base_url, catoid):
    """Extract department/subject links from Acalog courses listing page."""
    dept_links = []

    try:
        # Get all links on the page
        links = page.query_selector_all("a[href*='navoid'], a[href*='catoid']")
        print(f"    Total acalog links on page: {len(links)}")

        seen_navoids = set()
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()[:60]

            # Skip obvious navigation links
            if any(skip in text.lower() for skip in [
                'search', 'home', 'calendar', 'policy', 'about', 'information',
                'index', 'advanced', 'welcome', 'general information', 'tuition',
                'programs', 'degrees', 'schedule', 'registration', 'advising',
            ]):
                continue

            # Get navoid
            navoid_m = re.search(r'navoid=(\d+)', href)
            if navoid_m:
                navoid = navoid_m.group(1)
                if navoid not in seen_navoids and catoid and f"catoid={catoid}" in href:
                    seen_navoids.add(navoid)
                    full_href = href.replace("&amp;", "&")
                    if not full_href.startswith("http"):
                        full_href = base_url + full_href
                    dept_links.append((full_href, text))

    except Exception as e:
        print(f"    Error getting dept links: {e}")

    return dept_links


def fetch_with_cookies(session, url, retries=2):
    """Fetch URL with requests session (containing WAF cookies)."""
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=20)
            if r.status_code == 200 and len(r.text) > 100:
                return r.text
            if r.status_code == 202:
                # WAF challenge again - cookies expired
                return None
            return r.text if r.status_code == 200 else None
        except Exception as e:
            if attempt == retries:
                return None
            time.sleep(1)
    return None


def parse_courseblock(block, university, year, label, grad_threshold):
    """Parse a single courseblock div."""
    # Try CourseleafCMS format (detail-code + detail-title)
    code_span = block.find("span", class_="detail-code")
    title_span = block.find("span", class_="detail-title")

    if code_span and title_span:
        raw_code = code_span.get_text(strip=True)
        title = title_span.get_text(strip=True)
    else:
        # Try courseblocktitle paragraph
        title_p = block.find("p", class_="courseblocktitle")
        if title_p:
            title_text = title_p.get_text(" ", strip=True)
            m = re.match(r'([A-Z][A-Z0-9_&/\s]*?)\s{2,}([^.]+)', title_text)
            if m:
                raw_code = m.group(1).strip()
                title = m.group(2).strip()
            else:
                m = re.match(r'([A-Z][A-Z0-9_&/]*\s+[\dA-Z]+[A-Za-z]?)[\s\.]+(.+)', title_text)
                if m:
                    raw_code = m.group(1).strip()
                    title = m.group(2).strip()
                else:
                    return None
        else:
            # Try strong tags
            strong = block.find("strong")
            if strong:
                text = strong.get_text(strip=True)
                m = re.match(r'([A-Z]{2,8})\s+([\dA-Z]+[A-Za-z]?)\s+(.+)', text)
                if m:
                    dept_c, num_c, title = m.group(1), m.group(2), m.group(3)
                    raw_code = f"{dept_c} {num_c}"
                else:
                    return None
            else:
                return None

    # Clean title
    title = re.sub(r'\s*\.\s*\d[\d\-]*\s*(?:Credit|Hour|Unit|Cr)s?\.?$', '', title, flags=re.IGNORECASE).strip()
    title = re.sub(r'\s*\(\d[\d\-]*\)$', '', title).strip()
    title = title.rstrip(".")

    # Parse dept + num from raw_code
    m = re.match(r'([A-Z][A-Z0-9_&/]*(?:\s[A-Z][A-Z0-9]*)?)\s+([\d][A-Z0-9]*[A-Za-z]?)', raw_code)
    if not m:
        m = re.match(r'([A-Z]+)\s*([\d]+[A-Za-z]?)', raw_code)
    if not m:
        return None
    dept = m.group(1).strip()
    num = m.group(2).strip()

    # Get description
    desc = ""
    desc_p = (block.find("p", class_="courseblockdesc") or
              block.find("div", class_="courseblockdesc") or
              block.find("div", class_="courseblockextra"))
    if desc_p:
        desc = desc_p.get_text(" ", strip=True)
        desc = re.sub(r'^(Description|Course Description|Overview|Details?):?\s*', '', desc, flags=re.IGNORECASE)

    full = f"{title} {desc}"

    return {
        "university": university,
        "academic_year": year,
        "academic_year_label": label,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": default_area(dept),
        "level": classify_level(num, grad_threshold),
        "progressive_signal": int(check_keywords(full, PROGRESSIVE_KEYWORDS)),
        "western_canon_signal": int(check_keywords(full, WESTERN_CANON_KEYWORDS)),
        "climate_narrow_signal": int(check_keywords(full, CLIMATE_NARROW_KEYWORDS)),
        "climate_broad_signal": int(check_keywords(full, CLIMATE_BROAD_KEYWORDS)),
        "cross_listed": False,
        "deduplicated": True,
    }


def scrape_university(university_key):
    config = CONFIGS.get(university_key)
    if not config:
        print(f"Unknown university key: {university_key}")
        print(f"Available: {list(CONFIGS.keys())}")
        sys.exit(1)

    university = university_key
    year = "2026"
    label = "2026-2027"
    base = config["base"]
    catoid = config["catoid"]
    courses_navoid = config["courses_navoid"]
    grad_threshold = config.get("grad_threshold", 500)
    output_dir = f"/home/user/routine/data/{university}"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Scraping {config['name']}")
    print(f"Base: {base}, catoid: {catoid}, navoid: {courses_navoid}")
    print(f"{'='*60}\n")

    # Step 1: Get WAF cookies via Playwright
    waf_cookies, dept_links = get_waf_cookies(base, catoid, courses_navoid)

    if not waf_cookies:
        print("Failed to get WAF cookies!")
        return None

    # Step 2: Set up requests session with WAF cookies
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": base + "/",
    })
    session.cookies.update(waf_cookies)

    # Step 3: Test if requests now work with WAF cookies
    test_url = f"{base}/content.php?catoid={catoid}&navoid={courses_navoid}"
    print(f"\nTesting requests with WAF cookies...")
    r = session.get(test_url, timeout=15)
    print(f"  Test result: {r.status_code}, {len(r.text)} bytes")

    if r.status_code == 202 or len(r.text) < 100:
        print("  WAF cookies not working with requests. Will use Playwright for all pages.")
        # Fall back to full Playwright approach for all dept pages
        return scrape_with_playwright_all(university, config)

    print(f"  WAF cookies working! Proceeding with requests...")

    # Step 4: If we don't have dept links yet, get them from the courses page
    if not dept_links:
        print("\nParsing courses page for department links...")
        soup = BeautifulSoup(r.text, "html.parser")

        # Look for department navigation links
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "navoid=" in href and "catoid=" in href:
                text = a.get_text(strip=True)
                if not any(skip in text.lower() for skip in [
                    'search', 'home', 'calendar', 'policy', 'about', 'information',
                    'advanced', 'welcome', 'general', 'index', 'tuition',
                ]):
                    full_url = base + href if href.startswith("/") else href
                    dept_links.append((full_url, text))

        print(f"  Found {len(dept_links)} department links from requests")

    if not dept_links:
        print("No department links found!")
        # Print page content for debugging
        print(f"Page content preview: {r.text[:500]}")
        return None

    # Step 5: Scrape each department page
    all_courses = []
    seen = set()
    failed = []

    print(f"\nScraping {len(dept_links)} department pages...")

    def scrape_dept(url_text):
        url, text = url_text
        html = fetch_with_cookies(session, url)
        if not html:
            return [], url, text

        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.find_all("div", class_="courseblock")
        courses = []
        for b in blocks:
            c = parse_courseblock(b, university, year, label, grad_threshold)
            if c:
                courses.append(c)
        return courses, None, text

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(scrape_dept, (url, text)): (url, text) for url, text in dept_links}
        for i, fut in enumerate(as_completed(futures), 1):
            courses, failed_url, text = fut.result()
            if failed_url:
                failed.append(text)
                if i <= 5:
                    print(f"  [{i}/{len(dept_links)}] FAIL: {text[:30]}")
            else:
                new = 0
                for c in courses:
                    key = f"{c['department_code']}_{c['course_number']}"
                    if key not in seen:
                        seen.add(key)
                        all_courses.append(c)
                        new += 1
                if new or i <= 5:
                    print(f"  [{i}/{len(dept_links)}] {text[:25]}: {new} courses")

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")
    if failed:
        print(f"Failed ({len(failed)}): {failed[:10]}")

    if total == 0:
        print("No courses! Trying full Playwright approach...")
        return scrape_with_playwright_all(university, config)

    # Save data
    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/{university}_{year}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
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
        "university": university,
        "academic_year": year,
        "academic_year_label": label,
        "source": f"{base} (Acalog/AWS-WAF bypass, Playwright cookies)",
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
        "failed_depts": failed,
    }
    with open(f"{output_dir}/{university}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    print(f"Climate narrow: {cn} ({summary['climate_narrow_pct']}%) | Broad: {cb} ({summary['climate_broad_pct']}%)")
    for area, cnt in sorted(area_counts.items(), key=lambda x: -x[1]):
        print(f"  {area}: {cnt}")

    return summary


def scrape_with_playwright_all(university, config):
    """Full Playwright scrape when WAF cookies don't transfer to requests."""
    print(f"\nFull Playwright scrape for {config['name']}...")
    base = config["base"]
    catoid = config["catoid"]
    courses_navoid = config["courses_navoid"]
    grad_threshold = config.get("grad_threshold", 500)
    year = "2026"
    label = "2026-2027"
    output_dir = f"/home/user/routine/data/{university}"
    os.makedirs(output_dir, exist_ok=True)

    chromium_path = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    all_courses = []
    seen = set()
    failed = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        # Warm up
        courses_url = f"{base}/content.php?catoid={catoid}&navoid={courses_navoid}"
        print(f"Loading courses page: {courses_url}")
        try:
            page.goto(courses_url, wait_until="networkidle")
            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"Warning: {e}")

        content = page.content()
        print(f"Courses page: {len(content)} bytes")

        # Get dept links
        dept_links = get_dept_links_from_page(page, base, catoid)
        print(f"Department links: {len(dept_links)}")

        if not dept_links:
            print("No department links found! Page content:")
            print(page.evaluate("document.body.innerText")[:1000])
            browser.close()
            return None

        # Navigate each dept
        for i, (url, text) in enumerate(dept_links, 1):
            try:
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(2000)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                blocks = soup.find_all("div", class_="courseblock")
                new = 0
                for b in blocks:
                    c = parse_courseblock(b, university, year, label, grad_threshold)
                    if c:
                        key = f"{c['department_code']}_{c['course_number']}"
                        if key not in seen:
                            seen.add(key)
                            all_courses.append(c)
                            new += 1
                if new:
                    print(f"  [{i}/{len(dept_links)}] {text[:25]}: {new} courses")
            except Exception as e:
                print(f"  [{i}/{len(dept_links)}] ERROR {text[:25]}: {e}")
                failed.append(text)

        browser.close()

    total = len(all_courses)
    if total == 0:
        return None

    # Save
    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal", "cross_listed", "deduplicated",
    ]
    csv_path = f"{output_dir}/{university}_{year}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_courses)

    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": university, "academic_year": year, "academic_year_label": label,
        "source": f"{base} (Acalog, full Playwright)",
        "total_courses": total,
        "progressive_pct": round(100 * prog / total, 2) if total else 0,
        "canon_pct": round(100 * canon / total, 2) if total else 0,
        "by_area": area_counts, "failed_depts": failed,
    }
    with open(f"{output_dir}/{university}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nTotal: {total} | Progressive: {summary['progressive_pct']}% | Canon: {summary['canon_pct']}%")
    return summary


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "unlv"
    result = scrape_university(target)
    if result:
        print(f"\nDone! {result.get('total_courses', 0)} courses saved.")
    else:
        print("Scraping produced no results.")
