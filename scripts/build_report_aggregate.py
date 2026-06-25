#!/usr/bin/env python3
"""Aggregate all 100 universities' catalog signals for the comprehensive report."""
import json, os, statistics

with open('progress.json') as f:
    prog = json.load(f)
unis = prog['universities']
completed = {k: v for k, v in unis.items() if v.get('status') == 'completed'}

# Published Table 6 values from Marinovic (2026) for the 16 reference-paper universities.
PAPER = {
    'stanford':    (14.3, 4.2, 2025, 'Stanford'),
    'berkeley':    (10.0, 4.1, 2025, 'UC Berkeley'),
    'harvard':     (9.5,  5.3, 2025, 'Harvard'),
    'yale':        (21.7, 8.7, 2025, 'Yale'),
    'princeton':   (12.2, 10.7, 2025, 'Princeton'),
    'mit':         (7.8,  3.7, 2024, 'MIT'),
    'uchicago':    (28.3, 11.9, 2024, 'U. Chicago'),
    'columbia':    (15.5, 8.1, 2025, 'Columbia'),
    'cornell':     (15.3, 4.4, 2025, 'Cornell'),
    'northwestern':(9.1,  3.2, 2025, 'Northwestern'),
    'nyu':         (15.7, 11.9, 2025, 'NYU'),
    'vanderbilt':  (11.8, 4.9, 2025, 'Vanderbilt'),
    'uiuc':        (6.5,  1.9, 2024, 'UIUC'),
    'utaustin':    (6.6,  3.1, 2025, 'UT Austin'),
    'tamu':        (5.8,  2.2, 2024, 'Texas A&M'),
    'uiowa':       (8.3,  2.4, 2025, 'U. Iowa'),
}

DISPLAY = {
    'stanford':'Stanford','mit':'MIT','cornell':'Cornell','northwestern':'Northwestern',
    'nyu':'NYU','uiuc':'UIUC','uiowa':'U. Iowa',
    'upenn':'U. Penn','wisc':'U. Wisconsin–Madison','uw':'U. Washington','gatech':'Georgia Tech',
    'dartmouth':'Dartmouth','rice':'Rice','notredame':'Notre Dame','psu':'Penn State',
    'unc':'UNC Chapel Hill','bu':'Boston University','cwru':'Case Western','tulane':'Tulane',
    'northeastern':'Northeastern','gwu':'George Washington','umd':'U. Maryland','uf':'U. Florida',
    'colorado':'CU Boulder','uoregon':'U. Oregon','oregonstate':'Oregon State','vt':'Virginia Tech',
    'uconn':'UConn','temple':'Temple','drexel':'Drexel','ua':'U. Alabama','okstate':'Oklahoma State',
    'unl':'U. Nebraska–Lincoln','iastate':'Iowa State','ku':'U. Kansas','missouri':'U. Missouri',
    'msstate':'Mississippi State','colostate':'Colorado State','louisville':'U. Louisville',
    'miami':'U. Miami','uta':'UT Arlington','gmu':'George Mason','idaho':'U. Idaho','utd':'UT Dallas',
    'utsa':'UT San Antonio','montanastate':'Montana State','odu':'Old Dominion','txstate':'Texas State',
    'uncg':'UNC Greensboro','calpoly':'Cal Poly SLO','utahtech':'Utah Tech','uvu':'Utah Valley',
    'uaf':'U. Alaska Fairbanks','umt':'U. Montana','ysu':'Youngstown State','uwec':'UW–Eau Claire',
    'atu':'Arkansas Tech','unk':'U. Nebraska–Kearney','uwm':'UW–Milwaukee','neiu':'Northeastern Illinois',
    'uidaho':'U. Idaho (UG)','vsu':'Virginia State','worcester':'Worcester State','une':'U. New England',
    'uni':'U. Northern Iowa','iit':'Illinois Tech','fairfield':'Fairfield','alverno':'Alverno',
    'vanguard':'Vanguard','biola':'Biola','unco':'U. Northern Colorado','ndsu':'North Dakota State',
    'shsu':'Sam Houston State','uab':'UAB','ncsu':'NC State','uwgb':'UW–Green Bay','uwplatt':'UW–Platteville',
    'coloradomesa':'Colorado Mesa','cornerstone':'Cornerstone','csp':'Concordia–St. Paul',
    'csub':'CSU Bakersfield','keene':'Keene State','lamar':'Lamar','mwcc':'Mt. Wachusett CC',
    'snow':'Snow College','tamiu':'Texas A&M International','washburn':'Washburn',
    'tamucc':'Texas A&M–Corpus Christi','wku':'Western Kentucky','marshall':'Marshall','tsu':'Texas Southern',
}

records = []
for k, v in completed.items():
    sfile = f'data/{k}/{k}_summary.json'
    if os.path.exists(sfile):
        with open(sfile) as f:
            s = json.load(f)
        rescraped = s.get('source') == 'rescraped_2026'
        rec = {
            'key': k, 'name': DISPLAY.get(k, k),
            'source': 'rescraped' if rescraped else 'scraped',
            'year': int(s.get('academic_year', 2026)),
            'total': s.get('total_courses', 0),
            'prog': round(s.get('progressive_pct', 0.0), 1),
            'canon': round(s.get('canon_pct', 0.0), 1),
            'cn': s.get('climate_narrow_pct', 0.0),
            'cb': s.get('climate_broad_pct', 0.0),
            'by_area': s.get('by_area', {}),
            'paper': PAPER.get(k, (None, None, None, None))[:2] if k in PAPER else None,
        }
    elif k in PAPER:
        p, c, yr, nm = PAPER[k]
        rec = {
            'key': k, 'name': nm, 'source': 'Marinovic (2026)',
            'year': yr, 'total': v.get('course_years', 0),
            'prog': p, 'canon': c, 'cn': None, 'cb': None, 'by_area': {},
        }
    else:
        continue
    rec['ratio'] = round(rec['prog'] / rec['canon'], 2) if rec['canon'] else None
    records.append(rec)

with open('/tmp/agg.json', 'w') as f:
    json.dump(records, f, indent=2)

# "scraped" aggregates include both the 84 original scrapes and the 7 re-scrapes
scraped = [r for r in records if r['source'] in ('scraped', 'rescraped')]
n_rescraped = sum(1 for r in records if r['source'] == 'rescraped')
n_paper = sum(1 for r in records if r['source'] == 'Marinovic (2026)')
tot_courses = sum(r['total'] for r in scraped)
cw_prog = sum(r['prog'] * r['total'] for r in scraped) / tot_courses
cw_canon = sum(r['canon'] * r['total'] for r in scraped) / tot_courses
all_courses = tot_courses

print(f'Total records: {len(records)}  (scraped {len(scraped)-n_rescraped} + rescraped {n_rescraped} + paper {n_paper})')
print(f'Scraped courses (latest-year, deduped): {tot_courses:,}')
print(f'Course-weighted progressive: {cw_prog:.2f}%, canon: {cw_canon:.2f}%')
print(f'Simple-mean progressive: {statistics.mean(r["prog"] for r in scraped):.2f}%, canon: {statistics.mean(r["canon"] for r in scraped):.2f}%')
print(f'Median progressive: {statistics.median(r["prog"] for r in scraped):.2f}%, canon: {statistics.median(r["canon"] for r in scraped):.2f}%')

# Climate aggregates (scraped only)
cn = [r['cn'] for r in scraped if r['cn'] is not None]
cb = [r['cb'] for r in scraped if r['cb'] is not None]
print(f'Climate narrow mean: {statistics.mean(cn):.2f}%, broad mean: {statistics.mean(cb):.2f}%')

# Area composition aggregate (scraped only)
def area_count(n):
    return n['courses'] if isinstance(n, dict) else n

area_tot = {}
for r in scraped:
    for a, n in r['by_area'].items():
        area_tot[a] = area_tot.get(a, 0) + area_count(n)
grand = sum(area_tot.values())
print('\nAggregate area composition (scraped):')
for a in ['Humanities','Social Sciences','STEM','Medical Sciences','Professional','Other']:
    n = area_tot.get(a, 0)
    print(f'  {a:18s} {n:7,d}  {100*n/grand:5.1f}%')
