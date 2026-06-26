#!/usr/bin/env python3
"""Build 2020-2026 time series for reference universities with native multi-year sources.

Native historical sources:
  - Stanford : ExploreCourses XML API (academicYear param, every year)
  - Cornell  : Class Roster API (Fall roster per year, FA20..FA26)
  - MIT      : catalog.mit.edu/archive/{YYYY-YYYY}/ for 2020-2024, live catalog for 2025

Writes data/<uni>/<uni>_<startyear>.csv per year and data/<uni>/<uni>_timeseries.json.
The Wayback-only schools (uiuc, uiowa, northwestern, nyu) are handled separately.
"""
import os, re, csv, json, time, requests
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup

CA = os.environ.get('REQUESTS_CA_BUNDLE', '/root/.ccr/ca-bundle.crt')

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
CLIMATE_NARROW = ["climate change","global warming","greenhouse gas","carbon emission","fossil fuel",
                  "sea level rise","climate crisis"]
CLIMATE_BROAD = ["climate","sustainability","sustainable","renewable energy","environmental justice",
                 "carbon","decarbonization","net zero","clean energy","green energy","ecological",
                 "ecosystem","biodiversity"]
BROAD_AREA_MAP = {
    "Social Sciences": ["sociology","psychology","political","economics","anthropology","geography","social work","criminal justice","criminology","public policy","communication"],
    "Humanities": ["english","literature","history","philosophy","religious","theology","art history","music","theater","theatre","linguistics","classics","french","spanish","german","chinese","japanese","arabic","latin","language"],
    "STEM": ["mathematics","statistics","physics","chemistry","biology","computer","engineering","geology","astronomy","neuroscience","data science"],
    "Medical Sciences": ["nursing","medicine","health science","pharmacy","dentistry","kinesiology","public health","nutrition","occupational therapy","physical therapy"],
    "Professional": ["business","accounting","finance","management","marketing","law","education","social work","architecture"],
}

def classify_area(dept, title, desc):
    text = (dept + " " + title + " " + desc).lower()
    for area, kws in BROAD_AREA_MAP.items():
        if any(kw in text for kw in kws): return area
    return "Other"
def has_kw(text, kws):
    tl = text.lower(); return any(k in tl for k in kws)
def level_from_num(num):
    m = re.search(r'\d+', num or '');
    if not m: return "unknown"
    n = int(m.group()); return "lower" if n < 100 else ("upper" if n < 500 else "graduate")
def make_session():
    s = requests.Session(); s.verify = CA
    s.headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120'
    return s
def get(session, url, retries=3, timeout=40):
    for a in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 200: return r.text
            return None
        except Exception:
            if a < retries-1: time.sleep(0.8*(a+1)); session = make_session()
    return None

def write_year(uni, year, courses):
    """year = start year int. courses: list of (dept,num,title,desc). Returns summary dict."""
    out = f"/home/user/routine/data/{uni}"; os.makedirs(out, exist_ok=True)
    label = f"{year}-{year+1}"
    rows = []; seen = set()
    for dept,num,title,desc in courses:
        dept=(dept or '').strip(); num=(num or '').strip(); title=(title or '').strip(); desc=(desc or '').strip()
        if not dept or not title: continue
        key=(dept,num,title); dedup="yes" if key in seen else "no"; seen.add(key)
        text=title+" "+desc
        rows.append({"university":uni,"academic_year":str(year),"academic_year_label":label,
            "department_code":dept,"course_number":num,"title":title,"description":desc,
            "broad_area":classify_area(dept,title,desc),"level":level_from_num(num),
            "progressive_signal":"yes" if has_kw(text,PROGRESSIVE_KEYWORDS) else "no",
            "western_canon_signal":"yes" if has_kw(text,WESTERN_CANON_KEYWORDS) else "no",
            "climate_narrow_signal":"yes" if has_kw(text,CLIMATE_NARROW) else "no",
            "climate_broad_signal":"yes" if has_kw(text,CLIMATE_BROAD) else "no",
            "cross_listed":"no","deduplicated":dedup})
    fields=["university","academic_year","academic_year_label","department_code","course_number","title","description","broad_area","level","progressive_signal","western_canon_signal","climate_narrow_signal","climate_broad_signal","cross_listed","deduplicated"]
    with open(f"{out}/{uni}_{year}.csv",'w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    uniq=[r for r in rows if r['deduplicated']=='no']; tot=len(uniq)
    def pct(sig): return round(100*sum(1 for r in uniq if r[sig]=='yes')/tot,2) if tot else 0
    s={"academic_year":str(year),"academic_year_label":label,"total_courses":tot,
       "progressive_pct":pct('progressive_signal'),"canon_pct":pct('western_canon_signal'),
       "climate_narrow_pct":pct('climate_narrow_signal'),"climate_broad_pct":pct('climate_broad_signal')}
    print(f"    {uni} {label}: {tot} courses, prog {s['progressive_pct']}%, canon {s['canon_pct']}%")
    return s

def finalize(uni, per_year, source):
    ts={"university":uni,"source":source,"years":per_year}
    with open(f"/home/user/routine/data/{uni}/{uni}_timeseries.json",'w') as f:
        json.dump(ts,f,indent=2)

# ---------------- Stanford ----------------
def stanford(years):
    print("Stanford time series...")
    s=make_session()
    root=get(s,'https://explorecourses.stanford.edu/?view=xml-20200810')
    depts=sorted(set(re.findall(r'<department[^>]*name="([^"]+)"',root)))
    print(f"  {len(depts)} departments x {len(years)} years")
    per_year=[]
    for y in years:
        ay=f"{y}{y+1}"
        courses=[]
        for d in depts:
            url=(f'https://explorecourses.stanford.edu/search?view=xml-20200810&academicYear={ay}'
                 f'&q={d}&filter-coursestatus-Active=on&filter-departmentcode-{d}=on')
            xml=get(s,url,timeout=60)
            if not xml: time.sleep(0.2); continue
            try: r=ET.fromstring(xml)
            except Exception: time.sleep(0.2); continue
            for c in r.findall('.//course'):
                subj=(c.findtext('subject') or '').strip()
                if subj!=d: continue
                courses.append((subj,(c.findtext('code') or '').strip(),
                                (c.findtext('title') or '').strip(),(c.findtext('description') or '').strip()))
            time.sleep(0.12)
        per_year.append(write_year('stanford',y,courses))
    finalize('stanford',per_year,'explorecourses.stanford.edu XML API')

# ---------------- Cornell ----------------
def cornell(years):
    print("Cornell time series...")
    s=make_session()
    per_year=[]
    for y in years:
        roster=f"FA{str(y)[2:]}"
        try:
            subs=s.get(f'https://classes.cornell.edu/api/2.0/config/subjects.json?roster={roster}',timeout=30).json()
            codes=[x['value'] for x in subs['data']['subjects']]
        except Exception as e:
            print(f"    {roster}: no roster ({str(e)[:30]})"); continue
        courses=[]
        for sub in codes:
            try:
                resp=s.get(f'https://classes.cornell.edu/api/2.0/search/classes.json?roster={roster}&subject={sub}',timeout=30)
                j=resp.json() if resp.content else None
            except Exception:
                time.sleep(0.3); s=make_session(); continue
            if not j:
                continue
            for c in (j.get('data') or {}).get('classes',[]):
                courses.append((c.get('subject',''),str(c.get('catalogNbr','')),
                                c.get('titleLong') or c.get('titleShort') or '',c.get('description') or ''))
            time.sleep(0.1)
        per_year.append(write_year('cornell',y,courses))
    finalize('cornell',per_year,'classes.cornell.edu Class Roster API (Fall roster)')

# ---------------- MIT ----------------
def mit_parse(html):
    soup=BeautifulSoup(html,"html.parser"); out=[]
    for b in soup.find_all(class_="courseblock"):
        tp=b.find(class_='courseblocktitle')
        if not tp: continue
        for sp in tp.find_all('span'):
            cls=' '.join(sp.get('class',[])).lower()
            if 'credit' in cls or 'hour' in cls: sp.decompose()
        txt=re.sub(r'\s+',' ',tp.get_text(' ',strip=True).replace('\xa0',' '))
        m=re.match(r'([A-Z0-9.]+?)\.(\d+[A-Z]*)\s+(.+)',txt) or re.match(r'(\S+)\s+(.+)',txt)
        dept=num=title=''
        if m and m.lastindex==3: dept,num,title=m.group(1),m.group(2),m.group(3)
        elif m:
            code,title=m.group(1),m.group(2); pm=code.split('.'); dept,num=pm[0],(pm[1] if len(pm)>1 else '')
        if not dept or not title: continue
        d=b.find(class_='courseblockdesc') or b.find(class_='courseblockextra')
        out.append((dept,num,title,d.get_text(' ',strip=True) if d else ''))
    return out

def mit(years):
    print("MIT time series...")
    s=make_session()
    per_year=[]
    for y in years:
        label=f"{y}-{y+1}"
        # archive for <=2024-2025; live catalog is the current year (2025-2026). No 2026-2027 yet.
        if y<=2024:
            base=f'https://catalog.mit.edu/archive/{label}/subjects/'
        elif y==2025:
            base='https://catalog.mit.edu/subjects/'
        else:
            continue  # MIT has no published 2026-2027 catalog
        idx=get(s,base)
        if not idx: print(f"    {label}: index unavailable"); continue
        slugs=sorted(set(re.findall(r'/subjects/([a-z0-9]+)/',idx)))
        courses=[]
        for slug in slugs:
            html=get(s,f"{base}{slug}/")
            if not html: time.sleep(0.3); continue
            courses+=mit_parse(html); time.sleep(0.15)
        per_year.append(write_year('mit',y,courses))
    finalize('mit',per_year,'catalog.mit.edu archive + live')

if __name__=="__main__":
    import sys
    YEARS=list(range(2020,2027))  # 2020-21 ... 2026-27
    targets=sys.argv[1:] or ['stanford','cornell','mit']
    if 'stanford' in targets: stanford(YEARS)
    if 'cornell' in targets: cornell(YEARS)
    if 'mit' in targets: mit(YEARS)
    print("DONE")
