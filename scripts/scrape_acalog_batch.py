#!/usr/bin/env python3
"""
Acalog CMS batch scraper for remaining target universities.
Uses the Acalog server-side filter API (works without JS).
Covers: OSU, Pitt, LSU, OU, UNLV, Baylor, TTU, UH, UC, UDel,
        RPI, UTK, USC, Stony Brook, UVA
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
    try:
        n = int(re.sub(r"[^0-9]", "", str(num_str))[:5])
        return "graduate" if n >= 500 else "undergraduate"
    except Exception:
        return "undergraduate"


def generic_area(dept):
    dept = dept.upper()
    STEM_PREFIXES = {"MATH", "STAT", "PHYS", "CHEM", "BIOL", "CS", "CSE", "CSC",
                     "EE", "ECE", "EECS", "CE", "ME", "CHE", "CIVE", "ENGR",
                     "AERO", "ASTRO", "GEOL", "GEOG", "ENVS", "ENV", "BIOC",
                     "GENE", "MICRO", "NEURO", "NEUROS", "PSYB"}
    HUMANITIES_PREFIXES = {"ENGL", "HIST", "PHIL", "ART", "ARTHI", "ARTH",
                           "MUSC", "MUS", "THTR", "DANC", "RELI", "REL",
                           "SPAN", "FREN", "GERM", "CHIN", "JAPN", "ITAL",
                           "PORT", "RUSS", "LING", "CLAS", "CLASS"}
    SOCIAL_PREFIXES = {"ECON", "SOC", "SOCL", "PSYC", "POLS", "POLSC",
                       "ANTH", "ANTHRO", "GEOG", "COMM", "JOUR", "AFAM",
                       "WGST", "WGS", "GWS", "AMST", "INTL", "IR"}
    MEDICAL_PREFIXES = {"MED", "NURS", "PHAR", "DENT", "PT", "OT",
                        "PH", "HLTH", "HPER", "KIN", "ANAT", "PATH"}
    PROF_PREFIXES = {"ACCT", "FIN", "MGMT", "MKT", "BUS", "BUSN",
                     "LAW", "EDUC", "SW", "SWK", "PLAN", "ARCH",
                     "PA", "PUAD", "AGRI", "ARCH"}
    for prefix in STEM_PREFIXES:
        if dept.startswith(prefix):
            return "STEM"
    for prefix in HUMANITIES_PREFIXES:
        if dept.startswith(prefix):
            return "Humanities"
    for prefix in SOCIAL_PREFIXES:
        if dept.startswith(prefix):
            return "Social Sciences"
    for prefix in MEDICAL_PREFIXES:
        if dept.startswith(prefix):
            return "Medical Sciences"
    for prefix in PROF_PREFIXES:
        if dept.startswith(prefix):
            return "Professional"
    return "Other"


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return s


def detect_catoid(session, base_url, timeout=20):
    """Try to auto-detect the current catoid from the catalog homepage."""
    try:
        r = session.get(base_url + "/", timeout=timeout)
        if r.status_code not in (200, 202):
            return None
        # Look for catoid in URLs
        matches = re.findall(r'catoid=(\d+)', r.text)
        if matches:
            from collections import Counter
            counts = Counter(matches)
            return int(counts.most_common(1)[0][0])
    except Exception:
        pass
    return None


def get_course_ids_via_filter(session, base_url, catoid, limit=40, timeout=20):
    """
    Use Acalog's server-side course filter to get all course IDs.
    Returns list of (coid, title_text) tuples.
    """
    all_items = []
    page = 1

    while True:
        url = (f"{base_url}/content.php?catoid={catoid}"
               f"&filter[item_type]=3&filter[only_active]=1"
               f"&filter[3]=1&filter[cpage]={page}&filter[limit]={limit}")
        try:
            r = session.get(url, timeout=timeout)
        except Exception as e:
            print(f"    Filter page {page} error: {e}")
            break

        if r.status_code == 202:
            print(f"    Filter page {page}: got 202 (JS-only), filter API not working")
            return None
        if r.status_code != 200:
            print(f"    Filter page {page}: got {r.status_code}")
            break

        soup = BeautifulSoup(r.text, "html.parser")

        # Find course links: href contains preview_course_nopop.php or catoid
        links = soup.find_all("a", href=re.compile(r"preview_course_nopop|coid="))
        new_items = []
        for a in links:
            href = a.get("href", "")
            m = re.search(r"coid=(\d+)", href)
            if m:
                coid = m.group(1)
                text = a.get_text(" ", strip=True)
                new_items.append((coid, text))

        if not new_items:
            # Also check if we've reached the end
            total_text = soup.get_text()
            if "no courses" in total_text.lower() or "0 results" in total_text.lower():
                break
            # Try to find total count
            total_match = re.search(r"(\d+)\s+(?:to\s+\d+\s+of\s+)?(\d+)\s+results", total_text)
            if not total_match:
                # No results indication, we might be done
                if page > 1:
                    break
                # On page 1 with no links - filter API might not work
                print(f"    No course links found on page {page}")
                print(f"    Response status: {r.status_code}, size: {len(r.text)}")
                return None

        seen_coids = {coid for coid, _ in all_items}
        new_count = 0
        for item in new_items:
            if item[0] not in seen_coids:
                all_items.append(item)
                seen_coids.add(item[0])
                new_count += 1

        if not new_count:
            break

        print(f"    Page {page}: {len(new_items)} courses (total so far: {len(all_items)})")

        # Check if there's a next page link
        next_link = soup.find("a", string=re.compile(r"Next", re.I))
        if not next_link:
            # Check total count
            total_match = re.search(r"of\s+(\d+)\s+results", r.text)
            if total_match:
                total = int(total_match.group(1))
                if len(all_items) >= total:
                    break
            else:
                break

        page += 1
        time.sleep(0.3)

    return all_items


def fetch_course_detail(session, base_url, catoid, coid, timeout=20):
    """Fetch individual course detail page and parse it."""
    url = f"{base_url}/preview_course_nopop.php?catoid={catoid}&coid={coid}"
    try:
        r = session.get(url, timeout=timeout)
        if r.status_code != 200:
            return None
        return r.text
    except Exception:
        return None


def parse_course_detail(html, university, catoid_str, title_hint=""):
    """Parse Acalog course detail page into a course record dict."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    # Remove nav, header, footer
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()

    # Try to get the main course block
    # Acalog format 1: <h1>DEPT NUM - Title</h1>
    # Acalog format 2: <td class="block_content"><h1>...</h1>
    # Acalog format 3: Preview popup format

    # Get all text content
    text = soup.get_text(" ", strip=True)

    # The title_hint has the basic format: "DEPT NUM Title" or "DEPT NUM - Title"
    # Try to parse from title_hint first
    dept, num, title = None, None, ""

    # Pattern: "ACCT 1101 - Introduction to Accounting"
    m = re.match(r"^([A-Z][A-Z0-9/_&\s]*?)\s+([\d]+[A-Z]?)\s*[-:\.]\s*(.+)$", title_hint.strip())
    if not m:
        # Pattern: "ACCT 1101  Introduction to Accounting"
        m = re.match(r"^([A-Z][A-Z0-9/_&\s]*?)\s+([\d]+[A-Z]?)\s+(.+)$", title_hint.strip())
    if m:
        dept = m.group(1).strip()
        num = m.group(2).strip()
        title = m.group(3).strip()

    # If we couldn't parse from hint, try from page
    if not dept:
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(" ", strip=True)
            m = re.match(r"^([A-Z][A-Z0-9/_&\s]*?)\s+([\d]+[A-Z]?)\s*[-:\.]\s*(.+)$", h1_text)
            if not m:
                m = re.match(r"^([A-Z][A-Z0-9/_&\s]*?)\s+([\d]+[A-Z]?)\s+(.+)$", h1_text)
            if m:
                dept = m.group(1).strip()
                num = m.group(2).strip()
                title = m.group(3).strip()

    if not dept or not num:
        return None

    # Clean up dept (take only the prefix letters)
    dept = re.sub(r'\s+', ' ', dept).strip()
    if len(dept) > 10:
        # Take first word
        dept = dept.split()[0]

    # Find description - usually a paragraph after the title
    # Look for the longest paragraph
    desc = ""
    paras = soup.find_all("p")
    for p in paras:
        ptext = p.get_text(" ", strip=True)
        if len(ptext) > len(desc) and len(ptext) > 20:
            # Skip credit/prereq lines
            if not re.match(r"^Credit|^Prerequisite|^Cross-listed", ptext, re.I):
                desc = ptext

    # Alternatively find td.block_content
    block = soup.find("td", class_="block_content")
    if block and not desc:
        # Get paragraphs within block
        block_paras = block.find_all("p")
        for p in block_paras:
            ptext = p.get_text(" ", strip=True)
            if len(ptext) > len(desc) and len(ptext) > 20:
                desc = ptext

    # If still no desc, get text after title
    if not desc:
        # Remove title from text
        title_pos = text.find(title[:30]) if title else -1
        if title_pos >= 0:
            after = text[title_pos + len(title):].strip()
            # Take first ~500 chars as description
            desc = after[:500].strip()

    full_text = f"{title} {desc}"
    area = generic_area(dept)
    level = classify_level(num)

    return {
        "university": university,
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


def scrape_acalog_university(config):
    """Main scraping function for a single Acalog university."""
    short = config["short"]
    name = config["name"]
    base_url = config["base_url"]
    catoid = config.get("catoid")
    max_workers = config.get("workers", 8)

    print(f"\n{'='*60}")
    print(f"Scraping: {name} ({short})")
    print(f"Base URL: {base_url}")

    session = make_session()

    # Auto-detect catoid if not provided
    if not catoid:
        print("  Auto-detecting catoid...")
        catoid = detect_catoid(session, base_url)
        if catoid:
            print(f"  Detected catoid: {catoid}")
        else:
            print(f"  Could not detect catoid for {name}!")
            return None

    # Get course list via filter API
    print(f"  Fetching course list via filter API (catoid={catoid})...")
    course_list = get_course_ids_via_filter(session, base_url, catoid)

    if course_list is None:
        print(f"  ⚠ Filter API not working for {name} - needs Playwright")
        return {"status": "needs_playwright", "short": short}

    if not course_list:
        print(f"  ⚠ No courses found for {name}")
        return None

    print(f"  Found {len(course_list)} courses in filter. Fetching details...")

    # Fetch course details in parallel
    all_courses = []
    seen = set()

    def fetch_one(item):
        coid, title_hint = item
        html = fetch_course_detail(session, base_url, catoid, coid)
        record = parse_course_detail(html, short, str(catoid), title_hint)
        return record

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, item): item for item in course_list}
        done = 0
        for future in as_completed(futures):
            record = future.result()
            done += 1
            if record and isinstance(record, dict) and "department_code" in record:
                key = f"{record['department_code']}_{record['course_number']}"
                if key not in seen:
                    seen.add(key)
                    all_courses.append(record)
            if done % 200 == 0:
                print(f"    Processed {done}/{len(course_list)}, collected {len(all_courses)}...")
            time.sleep(0.05)

    total = len(all_courses)
    print(f"\n  Total unique courses: {total}")

    if total == 0:
        print(f"  ⚠ No courses parsed for {name}")
        return None

    # Save CSV
    output_dir = f"/home/user/routine/data/{short}"
    os.makedirs(output_dir, exist_ok=True)
    output_csv = f"{output_dir}/{short}_2026.csv"

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

    # Compute summary
    prog = sum(1 for c in all_courses if c["progressive_signal"])
    canon = sum(1 for c in all_courses if c["western_canon_signal"])
    cn = sum(1 for c in all_courses if c["climate_narrow_signal"])
    cb = sum(1 for c in all_courses if c["climate_broad_signal"])
    area_counts = {}
    for c in all_courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": short,
        "name": name,
        "academic_year": "2026",
        "academic_year_label": "2026-2027",
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
        "source": base_url,
        "catoid": catoid,
    }

    with open(f"{output_dir}/{short}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    prog_pct = summary["progressive_pct"]
    canon_pct = summary["canon_pct"]
    print(f"  ✓ {name}: {total} courses | {prog_pct}% progressive | {canon_pct}% canon")
    print(f"  Saved to {output_csv}")

    return summary


def update_progress(short, result):
    """Update progress.json with scrape result."""
    progress_file = "/home/user/routine/progress.json"
    with open(progress_file) as f:
        progress = json.load(f)

    if result and isinstance(result, dict) and "total_courses" in result:
        progress["universities"][short] = {
            "id": progress["universities"].get(short, {}).get("id"),
            "status": "completed",
            "source": result.get("source", ""),
            "years_covered": "2026",
            "catalog_years": 1,
            "course_years": result["total_courses"],
            "data_files": [
                f"data/{short}/{short}_2026.csv",
                f"data/{short}/{short}_summary.json",
            ],
            "progressive_pct": result["progressive_pct"],
            "canon_pct": result["canon_pct"],
            "notes": f"2026-27 catalog scraped via Acalog filter API. {result['total_courses']} courses.",
        }
        # Remove from dynamic_js_only / blocked lists if present
        for lst in ["dynamic_js_only", "blocked_by_network"]:
            if short in progress.get(lst, []):
                progress[lst].remove(short)
        # Update completed count
        completed = sum(
            1 for v in progress["universities"].values()
            if v.get("status") == "completed"
        )
        progress["completed"] = completed
        progress["last_updated"] = "2026-06-27"
    elif result and result.get("status") == "needs_playwright":
        if short not in progress.get("dynamic_js_only", []):
            progress.setdefault("dynamic_js_only", []).append(short)

    with open(progress_file, "w") as f:
        json.dump(progress, f, indent=2)


# ─── University configurations ───────────────────────────────────────────────

ACALOG_UNIVERSITIES = [
    {
        "short": "osu", "id": 24, "name": "Ohio State University",
        "base_url": "https://catalog.osu.edu",
        "catoid": None,  # auto-detect
    },
    {
        "short": "pitt", "id": 67, "name": "University of Pittsburgh",
        "base_url": "https://catalog.upp.pitt.edu",
        "catoid": 68,
    },
    {
        "short": "lsu", "id": 77, "name": "Louisiana State University",
        "base_url": "https://catalog.lsu.edu",
        "catoid": 26,
    },
    {
        "short": "ou", "id": 78, "name": "University of Oklahoma",
        "base_url": "https://catalog.ou.edu",
        "catoid": 66,
    },
    {
        "short": "unlv", "id": 92, "name": "University of Nevada Las Vegas",
        "base_url": "https://catalog.unlv.edu",
        "catoid": 35,
    },
    {
        "short": "baylor", "id": 93, "name": "Baylor University",
        "base_url": "https://catalog.baylor.edu",
        "catoid": 37,
    },
    {
        "short": "ttu", "id": 94, "name": "Texas Tech University",
        "base_url": "https://catalog.ttu.edu",
        "catoid": 26,
    },
    {
        "short": "uh", "id": 95, "name": "University of Houston",
        "base_url": "https://publications.uh.edu",
        "catoid": 56,
    },
    {
        "short": "uc", "id": 97, "name": "University of Cincinnati",
        "base_url": "https://catalog.uc.edu",
        "catoid": None,  # auto-detect
    },
    {
        "short": "udel", "id": 100, "name": "University of Delaware",
        "base_url": "https://catalog.udel.edu",
        "catoid": 67,
    },
    {
        "short": "stonybrook", "id": 99, "name": "Stony Brook University",
        "base_url": "https://www.stonybrook.edu/sb/bulletin",
        "catoid": None,  # auto-detect
    },
    {
        "short": "rpi", "id": 72, "name": "Rensselaer Polytechnic Institute",
        "base_url": "https://catalog.rpi.edu",
        "catoid": None,  # auto-detect
    },
    {
        "short": "utk", "id": 73, "name": "University of Tennessee Knoxville",
        "base_url": "https://catalog.utk.edu",
        "catoid": 2,
    },
    {
        "short": "uva", "id": 45, "name": "University of Virginia",
        "base_url": "https://records.ureg.virginia.edu",
        "catoid": None,  # auto-detect
    },
    {
        "short": "usc", "id": 27, "name": "University of Southern California",
        "base_url": "https://catalogue.usc.edu",
        "catoid": 22,
    },
]


def main(targets=None):
    """Scrape all (or specified) Acalog universities."""
    results = {}
    needs_playwright = []

    unis = ACALOG_UNIVERSITIES
    if targets:
        unis = [u for u in ACALOG_UNIVERSITIES if u["short"] in targets]

    for config in unis:
        short = config["short"]
        result = scrape_acalog_university(config)
        results[short] = result

        if result and isinstance(result, dict) and "total_courses" in result:
            update_progress(short, result)
        elif result and result.get("status") == "needs_playwright":
            needs_playwright.append(short)
            update_progress(short, result)
        else:
            print(f"  ✗ {short}: failed or no data")

        time.sleep(1)

    print(f"\n{'='*60}")
    print("BATCH SCRAPE COMPLETE")
    print(f"Successful: {[k for k, v in results.items() if v and 'total_courses' in v]}")
    print(f"Needs Playwright: {needs_playwright}")
    print(f"Failed: {[k for k, v in results.items() if not v]}")

    return results


if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else None
    main(targets)
