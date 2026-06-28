#!/usr/bin/env python3
"""
Generic Acalog CMS Playwright scraper for universities that return 202 with JS-only content.
Handles UNLV, RPI, UTK, LSU, TTU, UDel, UVA, and others.

Usage: python3 scrape_acalog_playwright_batch.py <university_short_name>
"""

import csv
import json
import os
import re
import sys
import time

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("Playwright not installed. Run: pip install playwright")
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


def classify_level(num_str):
    nums = re.findall(r'\d+', str(num_str))
    if nums:
        try:
            n = int(nums[0])
            return "graduate" if n >= 500 else "undergraduate"
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
        "area_map": {
            "ACT": "Professional", "ANTH": "Social Sciences", "ARC": "Humanities",
            "AST": "STEM", "BIO": "STEM", "BCH": "STEM", "CHE": "STEM",
            "CHEM": "STEM", "CIS": "STEM", "COM": "Social Sciences",
            "CRJU": "Social Sciences", "CS": "STEM", "EAB": "Social Sciences",
            "ECO": "Social Sciences", "EDS": "Professional", "EE": "STEM",
            "EGL": "Humanities", "ENG": "STEM", "ENST": "STEM",
            "FAR": "Humanities", "FIN": "Professional", "GEO": "STEM",
            "HCA": "Professional", "HIST": "Humanities", "HMD": "Professional",
            "HON": "Other", "HPS": "Social Sciences", "IS": "Professional",
            "KIN": "Medical Sciences", "MATH": "STEM", "MGT": "Professional",
            "MKT": "Professional", "MUS": "Humanities", "NSC": "STEM",
            "NV": "Social Sciences", "POLS": "Social Sciences", "PSY": "Social Sciences",
            "PHY": "STEM", "RHS": "Medical Sciences", "SOC": "Social Sciences",
            "SWK": "Professional", "THTR": "Humanities", "WS": "Social Sciences",
        },
    },
    "rpi": {
        "name": "Rensselaer Polytechnic Institute",
        "base": "https://catalog.rpi.edu",
        "catoid": 33,
        "courses_navoid": 891,
        "grad_threshold": 4000,
        "area_map": {
            "ARCH": "Humanities", "ARTS": "Humanities", "BIOL": "STEM",
            "BMGT": "Professional", "CHBE": "STEM", "CHEM": "STEM",
            "CIVL": "STEM", "COMM": "Social Sciences", "CSCI": "STEM",
            "ECON": "Social Sciences", "ECSE": "STEM", "ENGR": "STEM",
            "ENVE": "STEM", "ERTH": "STEM", "GAME": "STEM",
            "GSAS": "Other", "HASS": "Humanities", "ISSS": "Social Sciences",
            "IENV": "STEM", "ISES": "Social Sciences", "ITWS": "STEM",
            "LGHT": "STEM", "MATP": "STEM", "MANE": "STEM",
            "MATH": "STEM", "MGMT": "Professional", "MTLE": "STEM",
            "NEUR": "STEM", "NUCL": "STEM", "PHIL": "Humanities",
            "PHYS": "STEM", "PSYC": "Social Sciences", "STSO": "Social Sciences",
        },
    },
    "utk": {
        "name": "University of Tennessee Knoxville",
        "base": "https://catalog.utk.edu",
        "catoid": 56,
        "courses_navoid": 12117,
        "grad_threshold": 500,
        "area_map": {
            "ACCT": "Professional", "ADV": "Professional", "AEM": "STEM",
            "AFAM": "Humanities", "AGST": "Professional", "AMST": "Humanities",
            "ANTH": "Social Sciences", "ARCH": "Humanities", "ART": "Humanities",
            "ARTH": "Humanities", "AST": "STEM", "BIOL": "STEM",
            "BME": "STEM", "BUAD": "Professional", "CBE": "STEM",
            "CHEM": "STEM", "CE": "STEM", "COSC": "STEM",
            "CRWT": "Humanities", "ECE": "STEM", "ECON": "Social Sciences",
            "EDUC": "Professional", "EF": "Professional", "ENG": "Humanities",
            "ENGL": "Humanities", "ENGR": "STEM", "ENTM": "STEM",
            "ES": "STEM", "FORS": "Professional", "FREN": "Humanities",
            "GEOG": "Social Sciences", "GEOL": "STEM", "GERM": "Humanities",
            "GRKL": "Humanities", "HIST": "Humanities", "HS": "Medical Sciences",
            "IE": "STEM", "INFS": "STEM", "ITAL": "Humanities",
            "JAPN": "Humanities", "JOUR": "Professional", "KIN": "Medical Sciences",
            "LAT": "Humanities", "LAW": "Professional", "LGBT": "Social Sciences",
            "LING": "Humanities", "MATH": "STEM", "ME": "STEM",
            "MSE": "STEM", "MUS": "Humanities", "NE": "STEM",
            "NURS": "Medical Sciences", "NUTR": "Medical Sciences", "PHIL": "Humanities",
            "PHYS": "STEM", "PLAN": "Professional", "POLS": "Social Sciences",
            "PSY": "Social Sciences", "PUBH": "Medical Sciences", "REL": "Humanities",
            "RNR": "STEM", "RSM": "Professional", "SOC": "Social Sciences",
            "SOWK": "Professional", "SPAN": "Humanities", "STAT": "STEM",
            "SWK": "Professional", "THTR": "Humanities", "WGST": "Social Sciences",
        },
    },
    "lsu": {
        "name": "Louisiana State University",
        "base": "https://catalog.lsu.edu",
        "catoid": 35,
        "courses_navoid": 3486,
        "grad_threshold": 4000,
        "area_map": {
            "AAS": "Social Sciences", "ACCT": "Professional", "ADE": "Professional",
            "AGEC": "Professional", "AGRO": "STEM", "ANTH": "Social Sciences",
            "ARCH": "Humanities", "ART": "Humanities", "ARTH": "Humanities",
            "ASSC": "Social Sciences", "ASTR": "STEM", "BIOL": "STEM",
            "CHE": "STEM", "CHEM": "STEM", "CIS": "STEM",
            "COMD": "Social Sciences", "CSC": "STEM", "ECON": "Social Sciences",
            "EE": "STEM", "ENGL": "Humanities", "ENGR": "STEM",
            "FREN": "Humanities", "GEOG": "Social Sciences", "GEOL": "STEM",
            "GERM": "Humanities", "HIST": "Humanities", "HNRS": "Other",
            "ISLA": "Social Sciences", "ITAL": "Humanities", "JOUR": "Professional",
            "KIN": "Medical Sciences", "LAW": "Professional", "MATH": "STEM",
            "ME": "STEM", "MUS": "Humanities", "PHIL": "Humanities",
            "PHYS": "STEM", "POLS": "Social Sciences", "PSYC": "Social Sciences",
            "REL": "Humanities", "SOC": "Social Sciences", "SOCW": "Professional",
            "SPAN": "Humanities", "STAT": "STEM", "THTR": "Humanities",
            "WMST": "Social Sciences",
        },
    },
    "ttu": {
        "name": "Texas Tech University",
        "base": "https://catalog.ttu.edu",
        "catoid": 26,
        "courses_navoid": 2326,
        "grad_threshold": 5000,
        "area_map": {
            "ACCT": "Professional", "ANTH": "Social Sciences", "ART": "Humanities",
            "ARTH": "Humanities", "BIOL": "STEM", "CE": "STEM",
            "CHEM": "STEM", "CHIN": "Humanities", "COMC": "Social Sciences",
            "CS": "STEM", "ECON": "Social Sciences", "ECE": "STEM",
            "EDHE": "Professional", "ENGL": "Humanities", "ENGR": "STEM",
            "FIN": "Professional", "GEOG": "Social Sciences", "GEOL": "STEM",
            "GERM": "Humanities", "HIST": "Humanities", "HS": "Social Sciences",
            "IE": "STEM", "ISQS": "STEM", "ITAL": "Humanities",
            "KIN": "Medical Sciences", "LATN": "Humanities", "LAW": "Professional",
            "LING": "Humanities", "MATH": "STEM", "ME": "STEM",
            "MGT": "Professional", "MKT": "Professional", "MUS": "Humanities",
            "POLS": "Social Sciences", "PHIL": "Humanities", "PHYS": "STEM",
            "PSYC": "Social Sciences", "REL": "Humanities", "SOC": "Social Sciences",
            "SPAN": "Humanities", "STAT": "STEM", "SWK": "Professional",
            "THEA": "Humanities", "WGST": "Social Sciences",
        },
    },
    "udel": {
        "name": "University of Delaware",
        "base": "https://catalog.udel.edu",
        "catoid": 97,
        "courses_navoid": 35898,
        "grad_threshold": 600,
        "area_map": {
            "ACCT": "Professional", "ANFS": "STEM", "ANTH": "Social Sciences",
            "ARSC": "Humanities", "ART": "Humanities", "ARTC": "Humanities",
            "ARTH": "Humanities", "BIOC": "STEM", "BIOL": "STEM",
            "BMSC": "STEM", "BUAD": "Professional", "CHEM": "STEM",
            "CHEG": "STEM", "CISC": "STEM", "CIVL": "STEM",
            "COMM": "Social Sciences", "CRIM": "Social Sciences", "DSST": "STEM",
            "ECON": "Social Sciences", "EDUC": "Professional", "EGGG": "STEM",
            "ENGL": "Humanities", "ENSC": "STEM", "ENWC": "STEM",
            "FASH": "Professional", "FINC": "Professional", "FREN": "Humanities",
            "GEOG": "Social Sciences", "GEOL": "STEM", "GERM": "Humanities",
            "GREK": "Humanities", "HDFS": "Social Sciences", "HIST": "Humanities",
            "HLPR": "Medical Sciences", "HRIM": "Professional", "ITAL": "Humanities",
            "JAPN": "Humanities", "JOUR": "Professional", "KAAP": "Medical Sciences",
            "LATN": "Humanities", "LEST": "Humanities", "LING": "Humanities",
            "MAST": "STEM", "MATH": "STEM", "MDTE": "Professional",
            "MEEG": "STEM", "MICR": "STEM", "MUSC": "Humanities",
            "NSCI": "STEM", "NURS": "Medical Sciences", "NTDT": "Medical Sciences",
            "PHIL": "Humanities", "PHYS": "STEM", "PLSC": "STEM",
            "POLS": "Social Sciences", "PSYC": "Social Sciences", "REES": "Humanities",
            "RELS": "Humanities", "SOCI": "Social Sciences", "SOWK": "Professional",
            "SPAN": "Humanities", "STAT": "STEM", "THEA": "Humanities",
            "WOMS": "Social Sciences",
        },
    },
    "uva": {
        "name": "University of Virginia",
        "base": "https://records.ureg.virginia.edu",
        "catoid": 72,
        "courses_navoid": 6679,
        "grad_threshold": 5000,
        "area_map": {
            "AASS": "Social Sciences", "ACCT": "Professional", "AM": "STEM",
            "AMST": "Humanities", "ANTH": "Social Sciences", "ARCY": "Humanities",
            "ARTH": "Humanities", "ARTS": "Humanities", "ASTR": "STEM",
            "BIOL": "STEM", "BME": "STEM", "CHEM": "STEM",
            "CHE": "STEM", "CHIN": "Humanities", "CHTR": "Humanities",
            "CLCS": "Humanities", "CLAS": "Humanities", "COGS": "Social Sciences",
            "COMM": "Professional", "CS": "STEM", "CYS": "STEM",
            "DRAM": "Humanities", "ECON": "Social Sciences", "ECE": "STEM",
            "EDHS": "Professional", "EDLF": "Professional", "EDSL": "Professional",
            "ENCW": "Humanities", "ENGR": "STEM", "ENGL": "Humanities",
            "ENTP": "Professional", "EVEC": "STEM", "EVSC": "STEM",
            "FREN": "Humanities", "GERM": "Humanities", "GREE": "Humanities",
            "HIST": "Humanities", "HIME": "Social Sciences", "ITAL": "Humanities",
            "JAPN": "Humanities", "KLPA": "Humanities", "KINE": "Medical Sciences",
            "LASE": "Social Sciences", "LATN": "Humanities", "LAW": "Professional",
            "LING": "Humanities", "MATH": "STEM", "MAE": "STEM",
            "MDST": "Humanities", "MED": "Medical Sciences", "MICR": "STEM",
            "MSE": "STEM", "MUS": "Humanities", "NCEL": "STEM",
            "NEUR": "Medical Sciences", "NIST": "Social Sciences", "NURS": "Medical Sciences",
            "PEAC": "Social Sciences", "PHIL": "Humanities", "PHYS": "STEM",
            "POLS": "Social Sciences", "PORT": "Humanities", "PSYC": "Social Sciences",
            "RELG": "Humanities", "RUSS": "Humanities", "SARC": "Humanities",
            "SLAV": "Humanities", "SOC": "Social Sciences", "SPAN": "Humanities",
            "STAT": "STEM", "STS": "Social Sciences", "SWK": "Professional",
            "TURK": "Humanities", "USEM": "Other", "WGSS": "Social Sciences",
        },
    },
    "osu": {
        "name": "Ohio State University",
        "base": "https://catalog.osu.edu",
        "catoid": None,  # Catalog is being rebuilt - will discover
        "courses_navoid": None,
        "grad_threshold": 5000,
        "area_map": {},
    },
    "ou": {
        "name": "University of Oklahoma",
        "base": "https://catalog.ou.edu",
        "catoid": 66,
        "courses_navoid": None,  # Will discover
        "grad_threshold": 5000,
        "area_map": {},
    },
    "usc": {
        "name": "University of Southern California",
        "base": "https://catalogue.usc.edu",
        "catoid": 22,
        "courses_navoid": None,  # Will discover
        "grad_threshold": 500,
        "area_map": {},
    },
    "pitt": {
        "name": "University of Pittsburgh",
        "base": "https://catalog.pitt.edu",
        "catoid": None,
        "courses_navoid": None,
        "grad_threshold": 2000,
        "area_map": {},
    },
}


def default_area(dept):
    dept = dept.lower()
    STEM = {"math", "phys", "chem", "biol", "cs", "cosc", "csci", "ece", "ee", "me",
             "ce", "ae", "engr", "stat", "astr", "geol", "geog", "bioc", "biochem",
            "micr", "neur", "mbio", "cbio", "envs", "enve", "envsc", "bmsc",
            "mse", "mtle", "mae", "che", "cheg", "chbe", "civl", "cive",
            "phy", "ast", "sci", "bme", "ie", "ise", "itws", "nucl",}
    HUMANITIES = {"engl", "hist", "phil", "art", "arth", "artc", "mus", "musc",
                  "thea", "thtr", "drama", "dram", "lit", "clas", "latn", "gree",
                  "grek", "fren", "germ", "span", "ital", "port", "russ", "slav",
                  "chin", "japn", "ling", "lang", "rel", "rels", "relg", "reli",
                  "arch", "comm", "jou", "jour", "wrt", "writing", "crit",}
    SOCIAL = {"anth", "econ", "pols", "psyc", "psy", "soc", "soci", "geog",
              "comm", "com", "crju", "crim", "wgss", "wgst", "woms", "afam",
              "afst", "aaas", "amst", "lase", "isla", "glst", "socy",}
    MEDICAL = {"nurs", "kine", "kin", "kaap", "hlth", "hlpr", "ntdt", "nutr",
               "mdst", "med", "pharm", "pub", "pubh",}
    PROFESSIONAL = {"acct", "fin", "mgt", "mgmt", "mkt", "buad", "bus", "law",
                    "educ", "edlf", "edhe", "swk", "sowk", "plan", "hrim",
                    "fash", "jour", "journ", "adv",}
    if dept in STEM: return "STEM"
    if dept in HUMANITIES: return "Humanities"
    if dept in SOCIAL: return "Social Sciences"
    if dept in MEDICAL: return "Medical Sciences"
    if dept in PROFESSIONAL: return "Professional"
    return "Other"


def get_area(config, dept):
    dept_upper = dept.upper().split()[0]
    area_map = config.get("area_map", {})
    if dept_upper in area_map:
        return area_map[dept_upper]
    return default_area(dept.lower())


def parse_course_from_text(text_block):
    """Parse course info from Acalog rendered text."""
    # Try to find course code pattern: DEPT NUM Title
    m = re.match(r"([A-Z][A-Z0-9_&/]*(?:\s[A-Z][A-Z0-9]*)?)\s+([\dA-Z]+[A-Za-z]?)\s+(.+?)(?:\s*\([\d\-]+\s*(?:credit|hour|unit|cr)s?\))?$",
                 text_block.strip(), re.IGNORECASE)
    return m


def scrape_acalog_playwright(university_key):
    config = CONFIGS.get(university_key)
    if not config:
        print(f"Unknown university: {university_key}. Available: {list(CONFIGS.keys())}")
        sys.exit(1)

    university = university_key
    year = "2026"
    label = "2026-2027"
    base = config["base"]
    catoid = config["catoid"]
    courses_navoid = config["courses_navoid"]
    output_dir = f"/home/user/routine/data/{university}"
    os.makedirs(output_dir, exist_ok=True)

    all_courses = []
    seen = set()
    failed_depts = []

    print(f"=== {config['name']} Course Catalog Scraper (Playwright) ===")
    print(f"Base URL: {base}, catoid: {catoid}, navoid: {courses_navoid}")

    chromium_path = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chromium_path,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-setuid-sandbox", "--single-process"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()
        page.set_default_timeout(45000)

        # Step 1: Navigate to the catalog home to get catoid if not set
        if catoid is None:
            print("Discovering catalog structure...")
            try:
                page.goto(f"{base}/", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                content = page.content()
                # Find catoid from navigation links
                m = re.search(r'catoid=(\d+)', content)
                if m:
                    catoid = int(m.group(1))
                    print(f"  Discovered catoid: {catoid}")
                else:
                    print("  Could not discover catoid!")
                    browser.close()
                    return None
            except Exception as e:
                print(f"  Error navigating to home: {e}")
                browser.close()
                return None

        # Step 2: Navigate to courses listing page to find department links
        if courses_navoid is None:
            print("Discovering courses navoid...")
            try:
                page.goto(f"{base}/index.php?catoid={catoid}", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                content = page.content()
                # Look for "Courses" in navigation links with navoid
                matches = re.findall(r'navoid=(\d+)[^>]*>[^<]*(?:Courses?|Course Descriptions?|Instruction)[^<]*<', content, re.IGNORECASE)
                if not matches:
                    # Try another pattern
                    matches = re.findall(r'(?:Courses?|Course Descriptions?)[^"]*navoid=(\d+)', content, re.IGNORECASE)
                if matches:
                    courses_navoid = int(matches[0])
                    print(f"  Discovered courses navoid: {courses_navoid}")
                else:
                    print("  Could not discover courses navoid!")
                    # Print nav links for debugging
                    links = re.findall(r'href="([^"]*navoid[^"]*)"[^>]*>([^<]+)<', content)
                    for href, text in links[:10]:
                        print(f"    {text.strip()!r} -> {href}")
                    browser.close()
                    return None
            except Exception as e:
                print(f"  Error navigating to catalog index: {e}")
                browser.close()
                return None

        courses_url = f"{base}/content.php?catoid={catoid}&navoid={courses_navoid}"
        print(f"\nStep 2: Loading courses listing page...")
        print(f"  URL: {courses_url}")

        try:
            page.goto(courses_url, wait_until="networkidle")
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  Warning loading courses page: {e}")
            try:
                page.wait_for_timeout(5000)
            except Exception:
                pass

        content = page.content()
        print(f"  Page size: {len(content)} bytes")

        # Step 3: Find all department links
        dept_links = []

        # Pattern 1: Direct course preview links (courses listed on this page)
        preview_links = re.findall(r'href="([^"]*preview_course_nopop\.php[^"]*)"', content)

        # Pattern 2: Department/subject navigation links
        # These link to other navoid pages that show courses for that dept
        nav_links = re.findall(r'href="([^"]*content\.php\?catoid=\d+&(?:amp;)?navoid=\d+[^"]*)"', content)
        nav_links_raw = re.findall(r'content\.php\?catoid=\d+&(?:amp;)?navoid=(\d+)', content)

        print(f"  Preview course links: {len(preview_links)}")
        print(f"  Nav links: {len(nav_links)}")

        # Get department links from page navigation
        # Find all <a> tags with course-related text
        from_soup_pattern = r'<a[^>]+href="([^"]*catoid=\d+[^"]*)"[^>]*>([^<]{1,60})</a>'
        all_a_tags = re.findall(from_soup_pattern, content)

        # Filter for department/subject links
        dept_nav_links = []
        for href, text in all_a_tags:
            text = text.strip()
            # Skip common nav links
            if any(skip in text.lower() for skip in ['search', 'home', 'calendar', 'policy', 'about', 'general', 'index']):
                continue
            if 'navoid' in href and 'catoid' in href:
                href_clean = href.replace("&amp;", "&")
                if href_clean not in [d[0] for d in dept_nav_links]:
                    dept_nav_links.append((href_clean, text))

        print(f"  Department nav links found: {len(dept_nav_links)}")
        for href, text in dept_nav_links[:5]:
            print(f"    {text!r} -> {href}")

        if not dept_nav_links and not preview_links:
            print("  No department links found. Trying to find courses directly on page...")
            # Check if courses are listed directly
            course_blocks = re.findall(r'<div[^>]+class="[^"]*courseblock[^"]*"', content)
            print(f"  Direct course blocks: {len(course_blocks)}")

            # Show page content for debugging
            page_text = page.evaluate("document.body.innerText")
            print(f"  Page text (first 1000): {page_text[:1000]}")
            browser.close()
            return None

        # Step 4: Process department pages
        def extract_courses_from_page(page_content, university, year, label, config):
            """Extract courses from a rendered Acalog department page."""
            courses = []

            # Try CourseleafCMS format first (detail-code/detail-title)
            courseleaf_pattern = r'detail-code[^>]*>([^<]+)</span>.*?detail-title[^>]*>([^<]+)</span>.*?(?:courseblockdesc|courseblockextra)[^>]*>(.*?)</(?:p|div)>'

            # Standard Acalog courseblock format
            # Look for courseblock divs
            blocks_pattern = re.compile(
                r'<div[^>]+class="[^"]*courseblock[^"]*">(.*?)</div>\s*</div>',
                re.DOTALL
            )

            # Most common Acalog course pattern from rendered HTML:
            # Find course entries with code + title + description
            # Pattern: "DEPT NUM  Title   N credits  description"

            # Try to find strong-tagged course codes (common in Acalog)
            strong_codes = re.findall(
                r'<(?:strong|b)>([A-Z][A-Z0-9_&/\s]*\d+[A-Za-z]?)</(?:strong|b)>\s*(?:<[^>]+>)*\s*([^<]{5,100})',
                page_content
            )

            # Try table-based course listings
            table_rows = re.findall(
                r'<tr[^>]*>.*?<td[^>]*>([A-Z]{2,10}\s*\d{3,4}[A-Za-z]?)</td>.*?<td[^>]*>([^<]{5,100})</td>.*?</tr>',
                page_content, re.DOTALL
            )

            return courses

        # Process each department
        if preview_links:
            # Courses are directly listed on the page - extract them
            print(f"\nCourses listed directly on page ({len(preview_links)} courses)...")
            # Navigate to each course preview
            for i, href in enumerate(preview_links[:5], 1):  # Test first 5
                course_url = base + "/" + href.lstrip("/")
                try:
                    page.goto(course_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1000)
                    # Extract course info
                    course_content = page.content()
                    print(f"  Course {i}: {len(course_content)} bytes")
                except Exception as e:
                    print(f"  Error: {e}")

        elif dept_nav_links:
            print(f"\nScraping {len(dept_nav_links)} department pages...")

            for i, (href, dept_name) in enumerate(dept_nav_links, 1):
                dept_url = base + href if href.startswith("/") else href
                if not dept_url.startswith("http"):
                    dept_url = base + "/" + href.lstrip("/")

                try:
                    page.goto(dept_url, wait_until="networkidle")
                    page.wait_for_timeout(2000)

                    dept_content = page.content()

                    # Parse courses from the rendered HTML
                    # Look for courseblock divs
                    new_courses = parse_acalog_page(dept_content, university, year, label, config)

                    new = 0
                    for c in new_courses:
                        key = f"{c['department_code']}_{c['course_number']}"
                        if key not in seen:
                            seen.add(key)
                            all_courses.append(c)
                            new += 1

                    dept_short = dept_name[:20]
                    if new:
                        print(f"  [{i}/{len(dept_nav_links)}] {dept_short}: {new} courses")
                    else:
                        # Check if page has ANY content
                        page_text_preview = page.evaluate("document.body.innerText")[:200]
                        if i <= 3 or not all_courses:
                            print(f"  [{i}/{len(dept_nav_links)}] {dept_short}: 0 courses (preview: {page_text_preview[:100]!r})")

                except Exception as e:
                    print(f"  [{i}/{len(dept_nav_links)}] ERROR {dept_name[:20]}: {e}")
                    failed_depts.append(dept_name)

        browser.close()

    total = len(all_courses)
    print(f"\nTotal unique courses: {total}")

    if total == 0:
        print("No courses collected! Check the scraping approach.")
        return None

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
        "source": f"{base} (Acalog CMS, Playwright)",
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
        "failed_depts": failed_depts,
    }
    with open(f"{output_dir}/{university}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n=== Summary ===")
    print(f"Total: {total} | Progressive: {prog} ({summary['progressive_pct']}%) | Canon: {canon} ({summary['canon_pct']}%)")
    return summary


def parse_acalog_page(html_content, university, year, label, config):
    """Parse courses from a rendered Acalog department page."""
    import re
    courses = []

    # Method 1: CourseleafCMS format (detail-code, detail-title)
    # Look for blocks with class "courseblock"
    courseblock_pattern = re.compile(
        r'class="[^"]*courseblock[^"]*"[^>]*>(.*?)(?=class="[^"]*courseblock[^"]*"|$)',
        re.DOTALL
    )
    blocks = courseblock_pattern.findall(html_content)

    for block in blocks:
        # Try detail-code/detail-title format
        code_m = re.search(r'detail-code[^>]*>(?:<[^>]+>)*([A-Z][A-Z0-9\s&/]*\d+[A-Za-z]?)(?:</[^>]+>)*', block)
        title_m = re.search(r'detail-title[^>]*>(?:<[^>]+>)*([^<]{3,100})(?:</[^>]+>)*', block)

        if not (code_m and title_m):
            # Try strong/b tag format
            code_m = re.search(r'<(?:strong|b)>([A-Z]{2,8}[\s\d][A-Z0-9\s]{1,10})</(?:strong|b)>', block)
            title_m = re.search(r'</(?:strong|b)>\s*(?:<[^>]*>)*([^<]{5,100})', block)

        if not (code_m and title_m):
            continue

        raw_code = re.sub(r'\s+', ' ', code_m.group(1).strip())
        title = re.sub(r'\s+', ' ', title_m.group(1).strip())
        title = re.sub(r'\s*\.\s*\d+[\-\d]*\s*(?:Credit|Hour|Unit)s?\.?$', '', title, flags=re.IGNORECASE).strip()
        title = re.sub(r'\s*\(\d[\d\-]*\)$', '', title).strip()

        # Parse dept + num from raw_code
        m = re.match(r'([A-Z][A-Z0-9_&/]*(?:\s[A-Z][A-Z0-9]*)?)\s+([\d][A-Z0-9]*[A-Za-z]?)', raw_code)
        if not m:
            continue
        dept = m.group(1).strip()
        num = m.group(2).strip()

        # Get description
        desc = ""
        desc_m = re.search(r'(?:courseblockdesc|courseblockextra|coursedesc)[^>]*>(?:<[^>]+>)*([^<]{10,})', block)
        if desc_m:
            desc = re.sub(r'<[^>]+>', ' ', desc_m.group(1))
            desc = re.sub(r'\s+', ' ', desc).strip()
            desc = re.sub(r'^(Description|Course Description|Overview):?\s*', '', desc, flags=re.IGNORECASE)

        full = f"{title} {desc}"
        threshold = config.get("grad_threshold", 500)

        course = {
            "university": university,
            "academic_year": year,
            "academic_year_label": label,
            "department_code": dept,
            "course_number": num,
            "title": title,
            "description": desc,
            "broad_area": get_area(config, dept),
            "level": classify_level_with_threshold(num, threshold),
            "progressive_signal": int(check_keywords(full, PROGRESSIVE_KEYWORDS)),
            "western_canon_signal": int(check_keywords(full, WESTERN_CANON_KEYWORDS)),
            "climate_narrow_signal": int(check_keywords(full, CLIMATE_NARROW_KEYWORDS)),
            "climate_broad_signal": int(check_keywords(full, CLIMATE_BROAD_KEYWORDS)),
            "cross_listed": False,
            "deduplicated": True,
        }
        courses.append(course)

    return courses


def classify_level_with_threshold(num_str, threshold=500):
    nums = re.findall(r'\d+', str(num_str))
    if nums:
        try:
            n = int(nums[0])
            return "graduate" if n >= threshold else "undergraduate"
        except Exception:
            pass
    return "undergraduate"


def get_area(config, dept):
    dept_upper = dept.upper().split()[0]
    area_map = config.get("area_map", {})
    if dept_upper in area_map:
        return area_map[dept_upper]
    return default_area(dept.lower().split()[0])


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "unlv"
    result = scrape_acalog_playwright(target)
    if result:
        print(f"\nDone! {result['total_courses']} courses saved.")
    else:
        print("Scraping failed or produced no results.")
