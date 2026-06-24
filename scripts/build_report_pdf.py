#!/usr/bin/env python3
"""Render the comprehensive report to PDF using fpdf2."""
import json, statistics, re
from fpdf import FPDF

with open('/tmp/agg.json') as f:
    R = json.load(f)
scraped = [r for r in R if r['source'] == 'scraped']

def area_count(n):
    return n['courses'] if isinstance(n, dict) else n

tot = sum(r['total'] for r in scraped)
cw_prog = sum(r['prog'] * r['total'] for r in scraped) / tot
cw_canon = sum(r['canon'] * r['total'] for r in scraped) / tot
mean_prog = statistics.mean(r['prog'] for r in R)
mean_canon = statistics.mean(r['canon'] for r in R)
med_prog = statistics.median(r['prog'] for r in R)
med_canon = statistics.median(r['canon'] for r in R)
above = sum(1 for r in R if r['prog'] > r['canon'])
area_tot = {}
for r in scraped:
    for a, n in r['by_area'].items():
        area_tot[a] = area_tot.get(a, 0) + area_count(n)
grand = sum(area_tot.values())

def clean(s):
    # fpdf core fonts are latin-1; replace unicode dashes/quotes
    return (s.replace('–', '-').replace('—', '-').replace('’', "'")
             .replace('“', '"').replace('”', '"').replace('…', '...')
             .replace('×', 'x').replace(' ', ' '))

class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(120)
        self.cell(0, 8, 'What 100 Universities (Say They) Teach', align='L')
        self.cell(0, 8, f'p. {self.page_no()}', align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_text_color(0)
    def footer(self):
        pass

pdf = PDF(format='A4')
pdf.set_auto_page_break(True, margin=18)
pdf.add_page()
W = pdf.epw  # effective page width

def h1(t):
    pdf.ln(2); pdf.set_font('Helvetica', 'B', 15); pdf.set_text_color(20,40,90)
    pdf.multi_cell(W, 7, clean(t)); pdf.set_text_color(0); pdf.ln(1)
def h2(t):
    pdf.ln(1); pdf.set_font('Helvetica', 'B', 11.5); pdf.set_text_color(20,40,90)
    pdf.multi_cell(W, 6, clean(t)); pdf.set_text_color(0); pdf.ln(0.5)
def para(t):
    pdf.set_font('Helvetica', '', 10); pdf.multi_cell(W, 5, clean(t)); pdf.ln(1)
def bullet(t):
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(4); pdf.multi_cell(W-4, 5, clean('- ' + t)); pdf.ln(0.3)
def img(path, w=None):
    pdf.ln(1)
    if w is None: w = W
    x = pdf.l_margin + (W - w) / 2
    pdf.image(path, x=x, w=w); pdf.ln(2)
def caption(t):
    pdf.set_font('Helvetica', 'I', 8.5); pdf.set_text_color(90)
    pdf.multi_cell(W, 4.2, clean(t)); pdf.set_text_color(0); pdf.ln(1.5)

# Title block
pdf.set_font('Helvetica', 'B', 20); pdf.set_text_color(20,40,90)
pdf.multi_cell(W, 9, clean('What 100 Universities (Say They) Teach'))
pdf.set_text_color(0)
pdf.set_font('Helvetica', '', 12)
pdf.multi_cell(W, 6, clean('A cross-sectional extension of Marinovic (2026) to 100 U.S. institutions'))
pdf.set_font('Helvetica', 'I', 9.5); pdf.set_text_color(110)
pdf.multi_cell(W, 5, clean('Generated automatically by the catalog-collection routine - June 2026'))
pdf.set_text_color(0); pdf.ln(3)

h2('Abstract')
para(f'This report extends the catalog-language analysis of Marinovic (2026), "What Universities '
     f'(Say They) Teach," from its original 16-university comparison set to 100 U.S. institutions. '
     f'Following the reference methodology, each course title and description is searched for two '
     f'keyword families: a progressive signal (race, gender, identity, diversity, equity, social '
     f'justice, decolonial, and related themes) and a Western-canon signal (classical antiquity, '
     f'the Western intellectual tradition, canonical authors and texts). For the 84 newly '
     f'collected institutions the report uses the most recent published catalog (mostly '
     f'2026-2027); for the 16 reference institutions it cites the shares reported in Marinovic '
     f'(2026). Across the 84 freshly scraped catalogs - {tot:,} deduplicated courses - the '
     f'course-weighted progressive signal is {cw_prog:.1f}% and the Western-canon signal is '
     f'{cw_canon:.1f}%. The central pattern of the original paper holds in the far larger sample: '
     f'the progressive signal exceeds the Western-canon signal at {above} of 100 institutions, '
     f'typically by a factor of three to four. The signal is far from uniform - progressive '
     f'shares range from under 1% to over 34% - and the few institutions where the canon signal '
     f'dominates are Christian colleges or low-signal outliers. These measures are mechanical '
     f'keyword counts, not judgments about course quality or what is taught in classrooms.')

h1('1. Introduction')
para('Marinovic (2026) measures how often U.S. university course catalogs use language associated '
     'with progressive themes versus the Western canon, documenting a steady rise in the '
     'progressive signal alongside a flat-to-declining canon signal, drawing its cross-sectional '
     'comparisons from sixteen major research universities. This report keeps the method fixed '
     'and asks a simpler question: what does the same measurement look like across a much wider '
     'slice of American higher education?')
para('The 100 institutions here are deliberately heterogeneous - private research universities, '
     'large public flagships, regional public universities, technical institutes, religious '
     'colleges, and community colleges. The original sample explicitly omitted community '
     'colleges, regional public universities, and most liberal-arts colleges; this extension '
     'fills in exactly those gaps. The cost is that catalog coverage and description quality vary '
     'more across this sample than within the original sixteen. As in the reference report, this '
     'is a descriptive exercise: it asks only how often certain themes appear in the official '
     'language by which universities describe their courses.')

h1('2. Data and Method')
para('Coverage. The report combines (i) 84 newly collected catalogs scraped from each '
     f"institution's current public catalog - almost all 2026-2027 - parsed into a common schema "
     f'and containing {tot:,} deduplicated courses; and (ii) 16 reference catalogs from Marinovic '
     '(2026), whose latest-year progressive and Western-canon shares are reproduced from Table 6 '
     'of that paper (2024 or 2025 catalogs).')
para('Keyword matching. Matching is case-insensitive and uses the same progressive and '
     'Western-canon keyword lists as the reference paper. A course carries a signal if its '
     'combined title-plus-description contains at least one keyword from the corresponding list. '
     'Cross-listed duplicates are collapsed to one course-year before any share is computed. The '
     'two signals are not mutually exclusive.')
para('Three caveats specific to this extension: (1) Single-year snapshot - the 84 new '
     'institutions are observed in one recent catalog year, so this is a cross-section, not a '
     'panel, and cannot speak to trends over time. (2) Coarser area classification - broad areas '
     'are assigned by a mechanical department/title keyword map, so the residual "Other" category '
     'is large and should be read as "unclassified." (3) No enrollment weights - all shares are '
     'unweighted course counts, the same basis the reference paper uses for cross-university '
     'comparison.')

h1('3. Headline Findings')
bullet(f'The progressive signal dominates the canon signal almost everywhere. At {above} of 100 '
       f'institutions the progressive share exceeds the Western-canon share. Across the 84 '
       f'scraped catalogs the course-weighted progressive signal ({cw_prog:.1f}%) is about '
       f'{cw_prog/cw_canon:.1f}x the canon signal ({cw_canon:.1f}%).')
bullet(f'Typical magnitudes are lower than the elite sample. The median institution carries the '
       f'progressive signal on {med_prog:.1f}% of courses and the canon signal on {med_canon:.1f}%. '
       f'The most progressive elite catalogs (Yale 21.7%, U. Chicago 28.3%) sit in the upper tail '
       f'of the full distribution, not at its center.')
bullet('Enormous dispersion. Progressive shares span roughly 0.6% to 34%. The spread is '
       'institutional, not just disciplinary: regional and technical schools cluster low, while '
       'research universities and several small private colleges cluster high.')
bullet('Where the canon wins, it is usually religious. Only three institutions carry more '
       'canonical than progressive language: Biola and Cornerstone (Christian colleges), and '
       'Marshall, an outlier whose 0.6% progressive share reflects short, sparse catalog '
       'descriptions rather than a canon-heavy curriculum.')
bullet(f'Climate language is modest but pervasive. Across scraped catalogs the narrow climate '
       f'signal averages {statistics.mean([r["cn"] for r in scraped if r["cn"] is not None]):.1f}% '
       f'of courses and the broad climate-or-sustainability signal '
       f'{statistics.mean([r["cb"] for r in scraped if r["cb"] is not None]):.1f}%.')

img('reports/figures/fig1_scatter.png', w=W*0.92)
caption('Figure 1. Each point is one institution\'s latest catalog. Points above the dashed line '
        'carry more progressive than canonical language. Red = 16 reference institutions '
        '(Marinovic 2026); blue = 84 newly collected catalogs.')
img('reports/figures/fig3_distribution.png', w=W*0.8)
caption('Figure 2. Distribution of progressive and Western-canon shares across all 100 '
        'institutions. Dashed lines mark the means.')

# ---- Cross-sectional table ----
pdf.add_page()
h1('4. Cross-Sectional Comparison (all 100 institutions)')
para('Table 1 reports every institution\'s latest-catalog progressive and Western-canon shares, '
     'the ratio between them, and the number of courses analyzed. As in Table 6 of the reference '
     'paper, institutions are sorted from the highest progressive-to-canon ratio to the lowest.')

rated = [r for r in R if r['ratio'] is not None]
unrated = [r for r in R if r['ratio'] is None]
ordered = sorted(rated, key=lambda r: r['ratio'], reverse=True) + unrated

# table header
cols = [(10,'#'), (52,'University'), (12,'Year'), (24,'Courses'),
        (24,'Prog. %'), (20,'Canon %'), (22,'P/C'), (16,'Src')]
def row(cells, header=False, fill=False):
    pdf.set_font('Helvetica', 'B' if header else '', 8)
    if header:
        pdf.set_fill_color(20,40,90); pdf.set_text_color(255)
    else:
        pdf.set_fill_color(238,242,248) if fill else pdf.set_fill_color(255,255,255)
        pdf.set_text_color(0)
    for (wd, _), val in zip(cols, cells):
        align = 'L' if _ in ('University',) else ('C' if _ in ('#','Year','Src') else 'R')
        pdf.cell(wd, 5, clean(str(val)), border=0, align=align, fill=True)
    pdf.ln(5)
row([c[1] for c in cols], header=True)
for i, r in enumerate(ordered, 1):
    src = 'sc' if r['source'] == 'scraped' else 'pap'
    ratio = f"{r['ratio']:.2f}" if r['ratio'] is not None else '-'
    totc = f"{r['total']:,}" + ('' if r['source']=='scraped' else '*')
    row([i, r['name'], r['year'], totc, f"{r['prog']:.1f}", f"{r['canon']:.1f}", ratio, src],
        fill=(i % 2 == 0))
pdf.ln(1)
pdf.set_font('Helvetica', 'I', 7.5); pdf.set_text_color(110)
pdf.multi_cell(W, 4, clean('* For the 16 reference institutions (src=pap) the course count is the '
    'total course-years in Marinovic (2026), not a single-year count; shares are latest-year '
    '(2024/2025) values from that paper. Scraped counts (src=sc) are deduplicated single-year '
    '(mostly 2026-2027).'))
pdf.set_text_color(0)

img('reports/figures/fig2_ranking.png', w=W*0.95)
caption('Figure 3. The twenty highest and twenty lowest institutions by progressive share.')

# ---- Composition + climate ----
pdf.add_page()
h1('5. Catalog Composition')
para('Universities differ in the mix of courses they offer, which shapes baseline exposure to '
     'each keyword list. The table below aggregates broad-area composition across the 84 scraped '
     'catalogs. The large "Other" share reflects the coarse keyword-based area classifier used in '
     'this extension and should be read as "unclassified."')
crow = [(70,'Broad area'), (45,'Courses'), (55,'Share of catalog')]
pdf.set_font('Helvetica','B',9); pdf.set_fill_color(20,40,90); pdf.set_text_color(255)
for wd,t in crow: pdf.cell(wd,6,t,align='L' if t=='Broad area' else 'R',fill=True)
pdf.ln(6); pdf.set_text_color(0)
for j,a in enumerate(['Humanities','Social Sciences','STEM','Medical Sciences','Professional','Other']):
    n = area_tot.get(a,0)
    pdf.set_font('Helvetica','',9)
    pdf.set_fill_color(238,242,248) if j%2==0 else pdf.set_fill_color(255,255,255)
    pdf.cell(70,5.5,a,fill=True); pdf.cell(45,5.5,f"{n:,}",align='R',fill=True)
    pdf.cell(55,5.5,f"{100*n/grand:.1f}%",align='R',fill=True); pdf.ln(5.5)
pdf.set_font('Helvetica','B',9); pdf.set_fill_color(225,230,240)
pdf.cell(70,5.5,'Total',fill=True); pdf.cell(45,5.5,f"{grand:,}",align='R',fill=True)
pdf.cell(55,5.5,'100.0%',align='R',fill=True); pdf.ln(8)
para('In the reference paper the progressive signal concentrates in the Social Sciences and '
     'Professional schools, the canon signal in the Humanities, and both are lowest in STEM. The '
     'institution-level results are consistent with that pattern: the highest progressive shares '
     'are humanities- and social-science-heavy private colleges and flagships, the lowest are '
     'technical and applied institutions.')

h1('6. Climate-Related Language')
para('Following Appendix C of the reference paper, climate language is measured separately. A '
     'narrow signal captures climate change, global warming, greenhouse gas, carbon emissions, '
     'and similar; a broad signal adds sustainability, renewable energy, and clean energy. The '
     'fifteen scraped institutions with the highest broad climate share are shown below.')
cl = sorted([r for r in scraped if r['cb'] is not None], key=lambda r: r['cb'], reverse=True)[:15]
pdf.set_font('Helvetica','B',9); pdf.set_fill_color(20,40,90); pdf.set_text_color(255)
pdf.cell(12,6,'#',align='C',fill=True); pdf.cell(78,6,'University',fill=True)
pdf.cell(40,6,'Narrow %',align='R',fill=True); pdf.cell(40,6,'Broad %',align='R',fill=True); pdf.ln(6)
pdf.set_text_color(0)
for i,r in enumerate(cl,1):
    pdf.set_font('Helvetica','',9)
    pdf.set_fill_color(238,242,248) if i%2==0 else pdf.set_fill_color(255,255,255)
    pdf.cell(12,5.5,str(i),align='C',fill=True); pdf.cell(78,5.5,clean(r['name']),fill=True)
    pdf.cell(40,5.5,f"{r['cn']:.1f}",align='R',fill=True); pdf.cell(40,5.5,f"{r['cb']:.1f}",align='R',fill=True); pdf.ln(5.5)
pdf.ln(2)
img('reports/figures/fig4_climate.png', w=W*0.85)
caption('Figure 4. Top 20 scraped institutions by broad climate-or-sustainability share; dark '
        'bars show the narrow climate-change signal within each.')

h1('7. Limitations and Conclusion')
para('Catalogs are not classrooms: keyword counts on public descriptions do not reveal what is '
     'assigned, how a course is taught, or what students learn. Keyword lists produce false '
     'positives (equity in finance, diversity in biology, classical in physics) and false '
     'negatives (themes discussed without the listed words). These institutions are observed once '
     'and weighted by course count, not student seats. Coverage is uneven - some catalogs omit '
     'departments that failed to scrape, recorded per-institution in each summary file.')
para(f'Extending the measurement from 16 to 100 institutions does not overturn the central '
     f'finding of Marinovic (2026): progressive language is far more common than Western-canon '
     f'language in the stated curriculum, dominating at {above} of 100 schools. What the wider '
     f'sample adds is context for magnitude. The very high progressive shares of the '
     f'most-discussed elite catalogs are not representative of American higher education as a '
     f'whole; the median institution sits near {med_prog:.0f}%, with a long tail of regional, '
     f'technical, and religious institutions below that. The institutions where the canon still '
     f'leads are a small, distinctive group - Christian colleges, plus one low-signal outlier. '
     f'As in the original, these are rough, comparable signals offered for transparency and '
     f'replication, not verdicts on any institution.')
pdf.ln(2)
pdf.set_font('Helvetica','I',8.5); pdf.set_text_color(110)
pdf.multi_cell(W,4.5, clean('Reference: Ivan Marinovic, "What Universities (Say They) Teach," '
    'Stanford University, June 2026. Per-institution data: data/<uni>/<uni>_<year>.csv and '
    '<uni>_summary.json. Keyword lists and schema: schema.md. Catalog status of all targets: '
    'progress.json.'))
pdf.set_text_color(0)

pdf.output('reports/curriculum_report_100_universities.pdf')
print('PDF written: reports/curriculum_report_100_universities.pdf')
