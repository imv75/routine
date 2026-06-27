#!/usr/bin/env python3
"""Parse University of Rochester course list PDF."""
import re, csv, json
from pathlib import Path

PROXY = 'http://127.0.0.1:43429'
CA = '/root/.ccr/ca-bundle.crt'
PDF_URL = 'https://www.rochester.edu/college/courses/ase-courses.pdf'
NAME = 'University of Rochester'
KEY = 'rochester'
AY = '2024_2025'
AY_LABEL = '2024-2025'

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / 'data' / KEY
OUT_DIR.mkdir(exist_ok=True)
OUT_FILE = OUT_DIR / f'{KEY}_{AY}.csv'
PDF_PATH = OUT_DIR / f'{KEY}_{AY}.pdf'

PROGRESSIVE_KEYWORDS = [
    'diversity','racial','racism','anti-racism','antiracism','equity','equitable',
    'inclusion','inclusive','belonging','systemic racism','white supremacy',
    'privilege','oppression','marginalized','colonialism','decolonize','decolonial',
    'indigenous knowledge','settler','intersectionality','social justice',
    'environmental justice','queer theory','queer studies','gender studies',
    'feminist','feminism','patriarchy','heteronormativity','transgender','latinx',
    'bipoc','positionality','lived experience','microaggression','implicit bias',
    'unconscious bias','allyship','critical race','whiteness','reparations',
    'abolition','anti-capitalist','land acknowledgment','liberation',
]
WESTERN_CANON_KEYWORDS = [
    'shakespeare','plato','aristotle','socrates','homer','virgil','dante','milton',
    'chaucer','cervantes','descartes','kant','hegel','nietzsche','locke','hobbes',
    'rousseau','voltaire','classical antiquity','ancient greece','ancient rome',
    'medieval philosophy','renaissance humanism','western civilization',
    'great books','socratic','platonic','stoicism','epicureanism','thomism',
    'scholasticism','classical literature','greek tragedy','roman history',
    'byzantine','augustine','aquinas',
]
CLIMATE_NARROW_KEYWORDS = [
    'climate change','global warming','greenhouse gas','carbon emission',
    'decarbonization','net zero','paris agreement','ipcc','sea level rise',
    'permafrost','carbon capture','carbon sequestration','climate model',
    'climate science','climate policy','climate adaptation','climate mitigation',
    'climate justice','climate refugee','climate crisis','fossil fuel',
]
CLIMATE_BROAD_KEYWORDS = [
    'sustainability','sustainable development','renewable energy','solar power',
    'wind energy','energy transition','clean energy','carbon footprint',
    'carbon neutral','environmental policy','environmental law','environmental science',
    'ecology','ecosystem','biodiversity','habitat loss','species extinction',
    'ocean acidification','air pollution','water scarcity','environmental degradation',
    'circular economy','environmental impact','environmental assessment',
    'sustainable agriculture','environmental ethics',
]

def sig(text, kws): return 1 if any(k in text.lower() for k in kws) else 0

HUMANITIES_D = {'AAS','AHC','AHI','AMS','ARC','ARH','ARW','CLA','CLT','COM','DAN',
    'ENG','FLM','FRN','GER','GRK','HIS','HST','ITA','JPN','LAT','LIN','MUS','PHI',
    'POR','REL','RUS','SPA','THE','WGS','WRT','HIST','PHIL','RUSS','THEA','ENGL',}
SOCIAL_D = {'ANT','ECO','EDU','ENV','GEO','IR','NES','POL','PSC','PSY','SOC',
    'URB','SXS','ANTH','ECON','PSYC',}
STEM_D = {'AST','BCS','BCH','BIO','BME','CHE','CHM','CSC','ECE','EDE','EES',
    'GEO','ISC','LGP','MTH','ME','OPT','PHY','QST','STA','STT','BSC',
    'CHEM','MATH','PHYS','STAT','CS',}
PROFESSIONAL_D = {'BUS','FIN','MGT','MKT','ACCT','HTH','NUR','SOM','SMB',}
MEDICAL_D = {'BME','MTH','NES',}

def broad_area(dept):
    d = dept.upper()
    if d in PROFESSIONAL_D: return 'Professional'
    if d in STEM_D: return 'STEM'
    if d in SOCIAL_D: return 'Social Sciences'
    if d in HUMANITIES_D: return 'Humanities'
    return 'Other'

def course_level(num):
    try:
        n = int(re.search(r'\d+', str(num)).group())
        if n < 200: return 'Lower'
        if n < 300: return 'Lower'
        if n < 500: return 'Upper'
        return 'Graduate'
    except: return 'Other'

CSV_FIELDS = ['university','academic_year','academic_year_label','department_code',
              'course_number','title','description','broad_area','level',
              'progressive_signal','western_canon_signal','climate_narrow_signal',
              'climate_broad_signal','cross_listed','deduplicated']


def download_pdf(url, path):
    import requests
    s = requests.Session()
    s.proxies = {'https': PROXY, 'http': PROXY}
    s.verify = CA
    s.headers.update({'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'})
    r = s.get(url, timeout=60, stream=True)
    r.raise_for_status()
    with open(path, 'wb') as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    return path


def extract_pdf_text(path):
    from pdfminer.high_level import extract_text
    return extract_text(str(path))


def parse_courses(text):
    # Remove page headers/footers
    text = re.sub(r'Arts Sciences and Engineering Courses\s*', '', text)
    text = re.sub(r'University of Rochester\s*', '', text)
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE)

    courses = []
    # Split into lines
    lines = text.split('\n')

    # Pattern: DEPT NNN TITLE (all-caps header)
    COURSE_HDR = re.compile(r'^([A-Z]{2,6})\s+(\d{3}[A-Z]?)\s+(.+)$')

    current_dept = None
    current_num = None
    current_title = None
    current_desc_lines = []

    def flush():
        if current_dept:
            desc = ' '.join(current_desc_lines).strip()
            desc = re.sub(r'\s+', ' ', desc)
            # Remove "Offered: ..." from desc
            desc = re.sub(r'\s*Offered:.*$', '', desc, flags=re.IGNORECASE).strip()
            desc = desc[:2000]
            combined = f'{current_title} {desc}'
            courses.append({
                'dept_code': current_dept,
                'course_number': current_num,
                'title': current_title,
                'description': desc,
                'broad_area': broad_area(current_dept),
                'level': course_level(current_num),
                'progressive_signal': sig(combined, PROGRESSIVE_KEYWORDS),
                'western_canon_signal': sig(combined, WESTERN_CANON_KEYWORDS),
                'climate_narrow_signal': sig(combined, CLIMATE_NARROW_KEYWORDS),
                'climate_broad_signal': sig(combined, CLIMATE_BROAD_KEYWORDS),
                'cross_listed': 0,
                'deduplicated': 0,
            })

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m = COURSE_HDR.match(line)
        if m:
            # Check if it looks like a course header
            # (Department codes are uppercase, course numbers are 3-digit)
            flush()
            current_dept = m.group(1)
            current_num = m.group(2)
            # Title is Title Case or all caps
            current_title = m.group(3).strip()
            # Clean up title - convert from ALL CAPS to Title Case
            if current_title == current_title.upper():
                current_title = current_title.title()
            current_desc_lines = []
        elif current_dept:
            # Skip "Offered:" lines for desc (but keep for context)
            if not line.startswith('Offered:'):
                current_desc_lines.append(line)

    flush()
    return courses


def main():
    if OUT_FILE.exists():
        print(f'Already exists: {OUT_FILE}')
        return

    if not PDF_PATH.exists():
        print(f'Downloading PDF from {PDF_URL}...')
        download_pdf(PDF_URL, PDF_PATH)
        print(f'Downloaded: {PDF_PATH} ({PDF_PATH.stat().st_size:,} bytes)')
    else:
        print(f'Using existing PDF: {PDF_PATH}')

    print('Extracting text from PDF...')
    text = extract_pdf_text(PDF_PATH)
    print(f'Extracted {len(text):,} characters')

    print('Parsing courses...')
    courses = parse_courses(text)
    print(f'Found {len(courses)} courses')

    rows = []
    for course in courses:
        if course['dept_code'] and course['title']:
            rows.append({
                'university': NAME,
                'academic_year': AY,
                'academic_year_label': AY_LABEL,
                'department_code': course['dept_code'],
                'course_number': course['course_number'],
                'title': course['title'],
                'description': course['description'],
                'broad_area': course['broad_area'],
                'level': course['level'],
                'progressive_signal': course['progressive_signal'],
                'western_canon_signal': course['western_canon_signal'],
                'climate_narrow_signal': course['climate_narrow_signal'],
                'climate_broad_signal': course['climate_broad_signal'],
                'cross_listed': 0, 'deduplicated': 0,
            })

    with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()
        csv.DictWriter(f, fieldnames=CSV_FIELDS).writerows(rows)
    print(f'Saved: {OUT_FILE} ({len(rows)} courses)')

    prog = json.loads((ROOT / 'progress.json').read_text())
    if KEY in prog.get('dynamic_js_only', []):
        prog['dynamic_js_only'].remove(KEY)
    if KEY in prog.get('blocked_by_network', []):
        prog['blocked_by_network'].remove(KEY)
    prog['universities'][KEY] = {
        **prog['universities'].get(KEY, {}),
        'status': 'completed',
        'name': NAME,
        'data_files': [str(OUT_FILE)],
        'courses_count': len(rows),
        'progressive_pct': round(sum(1 for r in rows if r['progressive_signal']) / len(rows) * 100, 2) if rows else 0,
        'canon_pct': round(sum(1 for r in rows if r['western_canon_signal']) / len(rows) * 100, 2) if rows else 0,
        'notes': f'PDF course list (AS&E). AY={AY_LABEL}.',
    }
    prog['completed'] = sum(1 for v in prog['universities'].values() if v.get('status') == 'completed')
    import datetime
    prog['last_updated'] = datetime.datetime.utcnow().isoformat() + 'Z'
    (ROOT / 'progress.json').write_text(json.dumps(prog, indent=2))
    print(f'progress.json: {KEY} → completed ({prog["completed"]} total)')


if __name__ == '__main__':
    main()
