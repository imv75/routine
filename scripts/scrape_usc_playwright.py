#!/usr/bin/env python3
"""
USC Course Catalog Scraper using Playwright.
catalogue.usc.edu uses Acalog/ACMS with JS rendering.
"""

import csv
import json
import os
import re
import time
from playwright.sync_api import sync_playwright

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

DEPT_TO_AREA = {
    # Humanities
    "CLAS": "Humanities", "ENGL": "Humanities", "FREN": "Humanities",
    "GERM": "Humanities", "SPAN": "Humanities", "ITAL": "Humanities",
    "HIST": "Humanities", "PHIL": "Humanities", "RELI": "Humanities",
    "ARLT": "Humanities", "ARTL": "Humanities", "CRIT": "Humanities",
    "MUSC": "Humanities", "THTR": "Humanities", "DNCE": "Humanities",
    "CINE": "Humanities", "SLAV": "Humanities", "PORT": "Humanities",
    "SWMS": "Humanities", "AHIS": "Humanities", "ART": "Humanities",
    "CTCS": "Humanities", "ARCH": "Humanities", "LING": "Humanities",
    "COMM": "Humanities", "JOUR": "Humanities", "ASC": "Humanities",
    "EAST": "Humanities", "ARAB": "Humanities", "HEBR": "Humanities",
    "CHIN": "Humanities", "JAPN": "Humanities", "KORE": "Humanities",
    "TURK": "Humanities", "PERS": "Humanities", "SWAH": "Humanities",
    # Social Sciences
    "ECON": "Social Sciences", "GEOG": "Social Sciences", "IR": "Social Sciences",
    "POSC": "Social Sciences", "PSYC": "Social Sciences", "SOC": "Social Sciences",
    "ANTH": "Social Sciences", "AFAM": "Social Sciences", "AMST": "Social Sciences",
    "GERO": "Social Sciences", "JOUR": "Social Sciences", "PPD": "Social Sciences",
    # STEM
    "BISC": "STEM", "BIOL": "STEM", "CHEM": "STEM", "CSCI": "STEM",
    "MATH": "STEM", "PHYS": "STEM", "ASTR": "STEM", "EE": "STEM",
    "CS": "STEM", "ENGR": "STEM", "AME": "STEM", "CE": "STEM",
    "CHE": "STEM", "ISE": "STEM", "MASC": "STEM", "ENGR": "STEM",
    "ECE": "STEM", "MEET": "STEM", "GENE": "STEM", "NEPR": "STEM",
    "NEUR": "STEM", "MEDB": "STEM",
    # Medical
    "PM": "Medical Sciences", "PT": "Medical Sciences", "OT": "Medical Sciences",
    "PHAR": "Medical Sciences", "NURS": "Medical Sciences", "DENT": "Medical Sciences",
    "MED": "Medical Sciences", "DERM": "Medical Sciences", "IMED": "Medical Sciences",
    "PATH": "Medical Sciences", "MICB": "Medical Sciences", "BIOC": "Medical Sciences",
    "ANAT": "Medical Sciences", "RADIOL": "Medical Sciences", "OPSC": "Medical Sciences",
    # Professional
    "BUAD": "Professional", "ACCT": "Professional", "BAEP": "Professional",
    "BUSE": "Professional", "FBE": "Professional", "MKT": "Professional",
    "MOR": "Professional", "GSBA": "Professional", "DSCI": "Professional",
    "LAW": "Professional", "LAW": "Professional", "LLAW": "Professional",
    "PA": "Professional", "PPDE": "Professional", "PUAD": "Professional",
    "SWK": "Professional", "EDUC": "Professional", "CDEV": "Professional",
    "PLAN": "Professional", "SSCI": "Professional",
}


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def classify_dept(dept):
    dept_upper = dept.upper().split()[0]
    return DEPT_TO_AREA.get(dept_upper, "Other")


def classify_level(num):
    try:
        n = int(re.sub(r"[^0-9]", "", str(num))[:5])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def scrape_usc():
    output_dir = "/home/user/routine/data/usc"
    os.makedirs(output_dir, exist_ok=True)

    all_courses = []
    seen = set()
    failed_depts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        print("=== USC Course Catalog Scraper ===")
        print("Navigating to Courses of Instruction index...")

        # USC Acalog: catoid=22, navoid=9384 is Courses of Instruction
        page.goto("https://catalogue.usc.edu/content.php?catoid=22&navoid=9384", wait_until="networkidle")
        time.sleep(2)

        # Get all department links from the courses page
        content = page.content()
        print(f"Loaded courses index: {len(content)} bytes")

        # Find links to individual department pages
        links = page.query_selector_all("a[href*='preview_course_nopop'], a[href*='content.php?catoid']")
        print(f"Found {len(links)} links on index page")

        # Extract department content links
        dept_links = []
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "content.php" in href and "catoid=22" in href and "navoid" in href:
                dept_links.append((text, href))

        print(f"Department/section links: {len(dept_links)}")
        for t, h in dept_links[:10]:
            print(f"  {t[:50]} -> {h}")

        # If no dept links found, look at page structure
        if not dept_links:
            print("\nPage content preview:")
            text_content = page.query_selector("body")
            if text_content:
                print(text_content.inner_text()[:2000])

        browser.close()

    print(f"\nTotal courses: {len(all_courses)}")
    return all_courses


if __name__ == "__main__":
    courses = scrape_usc()
    print(f"Done: {len(courses)} courses")
