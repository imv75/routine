#!/usr/bin/env python3
"""
Coursedog catalog scraper - uses the public CSV export API.
Handles UCSB, UMN, Arizona, and Utah.
"""
import csv, io, json, os, re, sys
import requests

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

STEM_PREFIXES = (
    "math","stat","cs","cmpsc","cmpsc","cse","ece","ee","eecs","me","mae","chem","phys",
    "bio","biol","bioc","biom","bme","msci","esci","envs","envi","atms","atsc","geol",
    "earth","geo","geog_phys","gis","geop","geophysics","astr","astro","astron","phy",
    "physics","ener","engr","coe","cen","cbe","che","chm","cheme","matse","matsc","mse",
    "ese","ece","eee","eml","civl","civeng","ce","civil","mech","nucl","nuceng","aerosp",
    "aero","ae","asen","aero","astro","nre","nuc","nucl","oce","ocean","mar","marine",
    "ocen","mse","matrl","matl","mtle","mtle","envsc","envs","envst","envm","sust",
    "aps","apsc","apphys","aphy","math","stat","probability","operations","or","ie","ise",
    "indeng","inf","info","infosci","data","ds","datascience","compsci","cosc","cis",
    "it","itis","inftech","cpsc","csc","cit","csci","cis","is","mis","imse",
    "bioi","biol","biot","bios","bcmb","biochem","molbio","micro","mcb","microbio",
    "cell","cdb","nsci","neur","neuro","nbi","ns","neurosc","cogsc","cogs","cog","csci",
    "bioe","biomed","bmen","bien","bsen","bios","bs","botany","bot","zool","zoo",
    "ecol","evol","wildlife","wlf","wld","fres","fore","for","frsc","rangelab",
    "ansc","ansi","ans","agro","agr","agron","hort","plsc","plap","plant",
    "abe","bse","ag","ageng","age","aen","aes","cses","soil","soilsc","soilsci",
    "foodsc","foodsci","fst","nutr","fd","nutrition",
    "pubhlth","eph","esh","gph","hpm","hps","hsci","hlsc","nsg","nur","nurs","pt","ot",
    "mcdb","nchm","org","orgchem","analchem","pharm","pharmacology","pharmacol","phcol",
    "cmpsc","sct","sci",
)

HUMANITIES_PREFIXES = (
    "eng","engl","lit","writ","comp","rhet","wrst","lits","litr","wlc","cls","clas",
    "classics","grek","grk","latn","lat","germ","ger","fren","fre","span","spa","ital",
    "ita","port","por","rus","russ","chin","chns","jpn","japn","kor","kors","arb","arab",
    "heb","hebr","pers","prs","hin","hindi","tur","turk","afrl","afr","amh","viet","vtn",
    "hist","hst","hstm","hsts","mus","musi","musc","mued","mus","art","arth","arthist",
    "ahist","ahe","ahi","ah","artst","arh","artd","phil","philo","phi","reli","rel","rels",
    "rlst","thea","thtr","thr","ta","danc","dant","dan","mdia","med","media","film","flm",
    "cinema","cine","fms","sas","lat","ltnx","chic","eas","aas","ams","afam","afas","afs",
    "asc","asian","asam","afrc","afri","ethn","ethn","culs","cult","glst","glob","ids",
    "inter","ling","lng","anth","liba","libr",
)

SOCIAL_PREFIXES = (
    "econ","eco","ecn","pol","pols","polsc","poli","psci","plsc","psc","soc","socio",
    "socy","soci","psy","psyc","psych","anth","antr","geog","geog_soc","comm","cmm",
    "coms","com","mcom","jour","jrnl","journ","jou","sw","soc_wk","socwk","soswk",
    "crim","crjs","crj","cj","crim","crmj","wms","wgst","gndr","wmst","ws","wost",
    "ints","irdc","ir","intl","intst","lgls","lgst","gst","gend","gender",
    "uss","ura","urb","ups","pa","padm","pub","pubp","pub_adm","padm","puad","ppa",
    "gss","edp","edps","edq","edu_pol","edlp","eled",
)

PROFESSIONAL_PREFIXES = (
    "bus","busi","bsad","mgmt","mgt","mgt","acct","acctg","acc","fin","fina",
    "fnce","mktg","mkt","ibus","intb","mgmt","man","mgmt","mgmt","obhr","ohr",
    "re","real","reale","ream","retl","scm","scm","supplch","sm","ent","entre",
    "law","lwco","lwcr","lwge","jwlw","jlaw","ls","lsp","lsoc","par","para","legl",
    "educ","edu","ed","edc","educ","educ","edsp","edco","edcr","edel","edes","edhs",
    "edl","edlp","edse","edps","edy","educ","tedu","tch","tched","tche","te","ted",
    "arch","archt","arc","aarch","cdes","plan","urpl","cplanning","larch","lar",
    "la","land","intd","indes","ids_pro","des","fash","fashd","textil","txmi",
    "nurs","nsg","nur","nur","pt","dpt","ot","mot","pa","pasc","pamdi",
    "pubh","sph","hsa","has","hca","hcm","hcs","ham","hlt_ad","hlth","hpm",
    "kin","kine","kines","hper","pe","peh","pei","hpe","pew","spsc","exsc",
    "lib","libr","lbsc","info","lis","sis",
)

MEDICAL_PREFIXES = (
    "md","med","medx","clsc","clin","surg","anat","physio","phys_med","immu","immun",
    "micro","micr","path","path","pharm","pharmacol","radiol","rad","radio","oph",
    "peds","pediatric","obgyn","psyc","psych_med","nrsc","neur_med","card","cardiol",
    "dent","derm","endo","gastro","ger_med","hema","hematol","neph","oncol","ortho",
    "pulm","rheum","uro","vet","vets","vetm","vetsc","vmd","vmb","vme",
)


def classify_dept(dept_code):
    d = dept_code.lower().rstrip("0123456789").strip("_")
    # Exact prefix checks
    for prefix in STEM_PREFIXES:
        if d == prefix or d.startswith(prefix + "_"):
            return "STEM"
    for prefix in HUMANITIES_PREFIXES:
        if d == prefix or d.startswith(prefix + "_"):
            return "Humanities"
    for prefix in SOCIAL_PREFIXES:
        if d == prefix or d.startswith(prefix + "_"):
            return "Social Sciences"
    for prefix in MEDICAL_PREFIXES:
        if d == prefix or d.startswith(prefix + "_"):
            return "Medical Sciences"
    for prefix in PROFESSIONAL_PREFIXES:
        if d == prefix or d.startswith(prefix + "_"):
            return "Professional"

    # Fallback: substring check on known patterns
    if any(x in d for x in ("chem","biol","phys","math","stat","comp","engin","geo","sci","tech","data")):
        return "STEM"
    if any(x in d for x in ("hist","lit","phil","art","music","theater","reli","lang","ling","writ")):
        return "Humanities"
    if any(x in d for x in ("econ","psych","soc","anth","pols","comm","journ","geog")):
        return "Social Sciences"
    if any(x in d for x in ("nurs","med","pharm","dent","vet","clinical","health","pub_h")):
        return "Medical Sciences"
    if any(x in d for x in ("bus","acct","mgmt","law","educ","arch","soc_wk","nurs","plan")):
        return "Professional"
    return "Other"


def classify_level(course_num_str, grad_threshold=500):
    try:
        digits = re.sub(r"[^0-9]", "", str(course_num_str))
        if not digits:
            return "undergraduate"
        n = int(digits[:5])
        return "graduate" if n >= grad_threshold else "undergraduate"
    except Exception:
        return "undergraduate"


def check_keywords(text, keywords):
    t = text.lower()
    return any(kw in t for kw in keywords)


def make_record(university, year, year_label, dept, num, title, desc):
    full_text = f"{title} {desc}"
    return {
        "university": university,
        "academic_year": year,
        "academic_year_label": year_label,
        "department_code": dept,
        "course_number": num,
        "title": title,
        "description": desc,
        "broad_area": classify_dept(dept),
        "level": classify_level(num, 500),
        "progressive_signal": check_keywords(full_text, PROGRESSIVE_KEYWORDS),
        "western_canon_signal": check_keywords(full_text, WESTERN_CANON_KEYWORDS),
        "climate_narrow_signal": check_keywords(full_text, CLIMATE_NARROW_KEYWORDS),
        "climate_broad_signal": check_keywords(full_text, CLIMATE_BROAD_KEYWORDS),
        "cross_listed": False,
        "deduplicated": True,
    }


def save_courses(university, year, year_label, courses, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    fields = [
        "university", "academic_year", "academic_year_label",
        "department_code", "course_number", "title", "description",
        "broad_area", "level", "progressive_signal", "western_canon_signal",
        "climate_narrow_signal", "climate_broad_signal",
        "cross_listed", "deduplicated",
    ]
    csv_path = os.path.join(output_dir, f"{university}_{year}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(courses)

    total = len(courses)
    prog = sum(1 for c in courses if c["progressive_signal"])
    canon = sum(1 for c in courses if c["western_canon_signal"])
    cn = sum(1 for c in courses if c["climate_narrow_signal"])
    cb = sum(1 for c in courses if c["climate_broad_signal"])
    area_counts = {}
    for c in courses:
        area_counts[c["broad_area"]] = area_counts.get(c["broad_area"], 0) + 1

    summary = {
        "university": university,
        "academic_year": year,
        "academic_year_label": year_label,
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
    json_path = os.path.join(output_dir, f"{university}_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"  Saved {total} courses to {csv_path}")
    print(f"  Progressive: {prog} ({summary['progressive_pct']}%)")
    print(f"  Canon: {canon} ({summary['canon_pct']}%)")
    print(f"  Climate narrow: {cn} ({summary['climate_narrow_pct']}%)")
    print(f"  By area: {area_counts}")
    return summary


API_BASE = "https://app.coursedog.com/api/v1"

CONFIGS = {
    "ucsb": {
        "school": "ucsb",
        "catalog_id": "mZXlGvYb30h2fSq3aYLn",
        "year": "2025",
        "year_label": "2025-2026",
        "col_dept": "Subject & Prefix",
        "col_num": "Course Number",
        "col_title": "Full Course Title",
        "col_desc": "Course Description",
        "grad_threshold": 200,
    },
    "umn": {
        "school": "umn_umntc_peoplesoft",
        "catalog_id": "QEPaNgPjyzEkVlRYv42S",
        "year": "2026",
        "year_label": "2026-2027",
        "col_dept": "Course subject code",
        "col_num": "Course number",
        "col_title": "Course name",
        "col_desc": "Course description",
        "grad_threshold": 5000,
    },
    "uarizona": {
        "school": "arizona_peoplesoft",
        "catalog_id": "Xljz5tlVNVzrbyreNRaI",
        "year": "2026",
        "year_label": "2026-2027",
        "col_dept": "Subject code",
        "col_num": "Catalog Number",
        "col_title": "Course Title",
        "col_desc": "Course Description",
        "grad_threshold": 500,
    },
}


def scrape_university(name, cfg):
    print(f"\n=== Scraping {name.upper()} ({cfg['year_label']}) ===")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) academic research crawler",
        "X-Requested-With": "catalog",
    })

    url = f"{API_BASE}/ca/{cfg['school']}/catalogs/{cfg['catalog_id']}/courses/csv/%24filters?orderBy=code"
    filter_body = {"condition": "and", "filters": []}

    print(f"  Downloading CSV from Coursedog API...")
    r = session.post(url, json=filter_body, timeout=120)
    if r.status_code != 200:
        print(f"  ERROR: {r.status_code} - {r.text[:200]}")
        return None

    print(f"  Downloaded {len(r.text):,} bytes ({r.text.count(chr(10)):,} rows)")
    reader = csv.DictReader(io.StringIO(r.text))

    courses = []
    seen = set()
    skipped = 0

    for row in reader:
        dept = row.get(cfg["col_dept"], "").strip()
        num = row.get(cfg["col_num"], "").strip()
        title = row.get(cfg["col_title"], "").strip()
        desc = row.get(cfg["col_desc"], "").strip()

        if not dept or not num or not title:
            skipped += 1
            continue

        key = f"{dept}_{num}"
        if key in seen:
            continue
        seen.add(key)

        record = make_record(name, cfg["year"], cfg["year_label"], dept, num, title, desc)
        record["level"] = classify_level(num, cfg["grad_threshold"])
        courses.append(record)

    print(f"  Parsed {len(courses)} unique courses (skipped {skipped} incomplete rows)")
    output_dir = f"/home/user/routine/data/{name}"
    summary = save_courses(name, cfg["year"], cfg["year_label"], courses, output_dir)
    return summary


def main():
    targets = sys.argv[1:] if len(sys.argv) > 1 else list(CONFIGS.keys())
    results = {}
    for name in targets:
        if name not in CONFIGS:
            print(f"Unknown university: {name}")
            continue
        summary = scrape_university(name, CONFIGS[name])
        if summary:
            results[name] = summary

    print(f"\n=== Summary ===")
    for name, s in results.items():
        print(f"  {name}: {s['total_courses']} courses, {s['progressive_pct']}% progressive")


if __name__ == "__main__":
    main()
