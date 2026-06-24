#!/usr/bin/env python3
"""Assemble the comprehensive 100-university curriculum report (Markdown)."""
import json, statistics

with open('/tmp/agg.json') as f:
    R = json.load(f)
scraped = [r for r in R if r['source'] == 'scraped']

def area_count(n):
    return n['courses'] if isinstance(n, dict) else n

# Aggregates
tot_courses_scraped = sum(r['total'] for r in scraped)
cw_prog = sum(r['prog'] * r['total'] for r in scraped) / tot_courses_scraped
cw_canon = sum(r['canon'] * r['total'] for r in scraped) / tot_courses_scraped
mean_prog = statistics.mean(r['prog'] for r in R)
mean_canon = statistics.mean(r['canon'] for r in R)
med_prog = statistics.median(r['prog'] for r in R)
med_canon = statistics.median(r['canon'] for r in R)
sd_prog = statistics.pstdev(r['prog'] for r in R)

cn = [r['cn'] for r in scraped if r['cn'] is not None]
cb = [r['cb'] for r in scraped if r['cb'] is not None]
mean_cn = statistics.mean(cn); mean_cb = statistics.mean(cb)

area_tot = {}
for r in scraped:
    for a, n in r['by_area'].items():
        area_tot[a] = area_tot.get(a, 0) + area_count(n)
grand = sum(area_tot.values())

# Rankings
by_prog = sorted(R, key=lambda r: r['prog'], reverse=True)
by_ratio = sorted([r for r in R if r['ratio'] is not None], key=lambda r: r['ratio'], reverse=True)
above_diag = sum(1 for r in R if r['prog'] > r['canon'])

L = []
def w(s=''): L.append(s)

w('# What 100 Universities (Say They) Teach')
w()
w('### A cross-sectional extension of Marinovic (2026) to 100 U.S. institutions')
w()
w('*Generated automatically by the catalog-collection routine — June 2026*')
w()
w('---')
w()
w('## Abstract')
w()
w('This report extends the catalog-language analysis of Marinovic (2026), *What Universities '
  '(Say They) Teach*, from its original 16-university comparison set to **100 U.S. '
  'institutions**. Following the reference methodology exactly, each course title and '
  'description is searched for two keyword families: a **progressive signal** (race, gender, '
  'identity, diversity, equity, social justice, decolonial, and related themes) and a '
  '**Western-canon signal** (classical antiquity, the Western intellectual tradition, '
  'canonical authors and texts). For the 84 newly collected institutions the report uses the '
  'most recent published catalog (2026–2027); for the 16 reference institutions it cites the '
  'shares reported in Marinovic (2026). '
  f'Across the 84 freshly scraped catalogs — **{tot_courses_scraped:,} deduplicated courses** — '
  f'the course-weighted progressive signal is **{cw_prog:.1f}%** and the Western-canon signal is '
  f'**{cw_canon:.1f}%**. The central pattern of the original paper holds in the far larger sample: '
  f'the progressive signal exceeds the Western-canon signal at **{above_diag} of 100** '
  'institutions, typically by a factor of three to four. The signal is far from uniform, however — '
  f'progressive shares range from under 1% to over 34%, and the handful of institutions where the '
  'canon signal dominates are Christian colleges or low-signal outliers. '
  'These measures are mechanical keyword counts, not judgments about course quality or what is '
  'taught in classrooms.')
w()
w('---')
w()
w('## 1. Introduction')
w()
w('Marinovic (2026) measures how often U.S. university course catalogs use language associated '
  'with progressive themes versus the Western canon, documenting a steady rise in the progressive '
  'signal alongside a flat-to-declining canon signal. That study draws its cross-sectional '
  'comparisons from sixteen major research universities. This report keeps the method fixed and '
  'asks a simpler question: **what does the same measurement look like across a much wider slice '
  'of American higher education?**')
w()
w('The 100 institutions here are deliberately heterogeneous. They include private research '
  'universities, large public flagships, regional public universities, technical institutes, '
  'religious colleges, and community colleges. This breadth is the point: the original sample '
  'explicitly omitted "community colleges, regional public universities, and most liberal-arts '
  'colleges," and this extension fills in exactly those gaps. The cost is that catalog coverage '
  'and description quality vary more across this sample than within the original sixteen.')
w()
w('As in the reference report, this is a descriptive exercise. It does not judge the quality of '
  'individual courses or the seriousness of any field. It asks only how often certain themes '
  'appear in the official language by which universities describe their courses.')
w()
w('---')
w()
w('## 2. Data and Method')
w()
w('**Coverage.** The report combines two sources:')
w()
w(f'- **84 newly collected catalogs** (this project), each scraped from the institution\'s '
  f'current public catalog — almost all 2026–2027 — and parsed into the common schema below. '
  f'Together these contain **{tot_courses_scraped:,} deduplicated courses**.')
w('- **16 reference catalogs** from Marinovic (2026), whose latest-year progressive and '
  'Western-canon shares are reproduced from Table 6 of that paper (2024 or 2025 catalogs).')
w()
w('**Schema.** Every course record carries: university, academic year, department code, course '
  'number, title, description, broad academic area, level, and four binary keyword signals '
  '(progressive, Western-canon, narrow-climate, broad-climate). Cross-listed duplicates are '
  'collapsed to one course-year before any share is computed.')
w()
w('**Keyword matching.** Matching is case-insensitive and uses the same progressive and '
  'Western-canon keyword lists as the reference paper (reproduced in `schema.md`). A course '
  'carries a signal if its combined title-plus-description contains at least one keyword from '
  'the corresponding list. The two signals are not mutually exclusive.')
w()
w('**Three caveats specific to this extension:**')
w()
w('1. **Single-year snapshot.** Unlike the Stanford time series in the reference paper, the 84 '
  'new institutions are observed in a single recent catalog year. This report is therefore a '
  'cross-section, not a panel; it cannot speak to trends over time at these schools.')
w('2. **Coarser area classification.** Broad academic areas here are assigned by a mechanical '
  'department/title keyword map rather than institution-specific academic-group fields. The '
  'residual **"Other"** category is correspondingly large and should be read as "unclassified," '
  'not as a substantive grouping.')
w('3. **No enrollment weights.** Comparable enrollment data are not available, so all shares are '
  'unweighted course counts — the same basis the reference paper uses for its cross-university '
  'comparisons.')
w()
w('---')
w()
w('## 3. Headline Findings')
w()
w(f'- **The progressive signal dominates the canon signal almost everywhere.** At '
  f'**{above_diag} of 100** institutions the progressive share exceeds the Western-canon share. '
  f'Across the 84 scraped catalogs the course-weighted progressive signal ({cw_prog:.1f}%) is '
  f'about **{cw_prog/cw_canon:.1f}×** the canon signal ({cw_canon:.1f}%).')
w(f'- **Typical magnitudes are lower than the elite sample.** The median institution carries the '
  f'progressive signal on **{med_prog:.1f}%** of courses and the canon signal on **{med_canon:.1f}%**. '
  f'The simple mean across all 100 is **{mean_prog:.1f}%** progressive and **{mean_canon:.1f}%** '
  f'canon. The highly progressive elite catalogs in the reference paper (Yale 21.7%, U. Chicago '
  f'28.3%) sit in the upper tail of the full distribution, not at its center.')
w(f'- **Enormous dispersion.** Progressive shares span roughly **0.6% to 34%** (standard '
  f'deviation {sd_prog:.1f} points). The spread is institutional, not just disciplinary: regional '
  f'and technical schools cluster low, while research universities and several small private '
  f'colleges cluster high.')
w('- **Where the canon wins, it is usually religious.** Only three institutions carry more '
  'canonical than progressive language: Biola and Cornerstone — both Christian colleges where '
  'biblical and classical-author keywords are common — and Marshall, an outlier whose unusually '
  'low progressive share (0.6%) reflects short, sparse catalog descriptions rather than a '
  'canon-heavy curriculum.')
w(f'- **Climate language is modest but pervasive.** Across scraped catalogs the narrow climate '
  f'signal averages **{mean_cn:.1f}%** of courses and the broad climate-or-sustainability signal '
  f'**{mean_cb:.1f}%**.')
w()
w('![Progressive vs. Western-canon signal across 100 universities](figures/fig1_scatter.png)')
w()
w('*Figure 1. Each point is one institution\'s latest catalog. Points above the dashed line '
  'carry more progressive than canonical language. Red points are the 16 reference institutions '
  'from Marinovic (2026); blue points are the 84 newly collected catalogs.*')
w()
w('![Distribution of signal shares](figures/fig3_distribution.png)')
w()
w('*Figure 2. Distribution of progressive and Western-canon shares across all 100 institutions. '
  'Dashed lines mark the means.*')
w()
w('---')
w()
w('## 4. Cross-Sectional Comparison (all 100 institutions)')
w()
w('Table 1 reports every institution\'s latest-catalog progressive and Western-canon shares, the '
  'ratio between them, and the number of courses analyzed. As in Table 6 of the reference paper, '
  'institutions are sorted from the highest progressive-to-canon ratio to the lowest. A high '
  'ratio means progressive language is many times more common than canonical language; a ratio '
  'below 1 (the canon-dominant institutions) appears at the bottom.')
w()
w('| # | University | Year | Courses | Progressive % | Canon % | Prog./Canon | Source |')
w('|--:|------------|:----:|--------:|:------------:|:-------:|:-----------:|--------|')
# canon-dominant (ratio<1 or None) go last; sort by ratio desc, None at end
rated = [r for r in R if r['ratio'] is not None]
unrated = [r for r in R if r['ratio'] is None]
ordered = sorted(rated, key=lambda r: r['ratio'], reverse=True) + unrated
for i, r in enumerate(ordered, 1):
    src = 'scraped' if r['source'] == 'scraped' else 'paper'
    ratio = f"{r['ratio']:.2f}" if r['ratio'] is not None else '—'
    tot = f"{r['total']:,}" if r['source']=='scraped' else f"{r['total']:,}*"
    w(f"| {i} | {r['name']} | {r['year']} | {tot} | {r['prog']:.1f} | {r['canon']:.1f} | {ratio} | {src} |")
w()
w('*\\* For the 16 reference institutions the course count is the total course-years in '
  'Marinovic (2026), not a single-year count; their shares are latest-year (2024/2025) values '
  'from that paper. Scraped course counts are deduplicated single-year (mostly 2026–2027).*')
w()
w('![Progressive ranking](figures/fig2_ranking.png)')
w()
w('*Figure 3. The twenty highest and twenty lowest institutions by progressive share.*')
w()
w('---')
w()
w('## 5. Catalog Composition')
w()
w('Universities differ mechanically in the mix of courses they offer, which shapes baseline '
  'exposure to each keyword list. Table 2 aggregates the broad-area composition across the 84 '
  'scraped catalogs. The large **Other** share reflects the coarse, keyword-based area classifier '
  'used in this extension (see §2, caveat 2) and should be read as "unclassified."')
w()
w('| Broad area | Courses | Share of scraped catalog |')
w('|------------|--------:|:------------------------:|')
for a in ['Humanities','Social Sciences','STEM','Medical Sciences','Professional','Other']:
    n = area_tot.get(a, 0)
    w(f"| {a} | {n:,} | {100*n/grand:.1f}% |")
w(f"| **Total** | **{grand:,}** | **100.0%** |")
w()
w('In the reference paper the progressive signal is concentrated in the Social Sciences and '
  'Professional schools, the Western-canon signal in the Humanities, and both are lowest in STEM. '
  'The institution-level results below are consistent with that pattern: the catalogs with the '
  'highest progressive shares are the humanities- and social-science-heavy private colleges and '
  'flagships, while the lowest are the technical and applied institutions.')
w()
w('---')
w()
w('## 6. Climate-Related Language')
w()
w('Following Appendix C of the reference paper, climate language is measured separately from the '
  'progressive signal because it is not a synonym for it. Two definitions are used: a **narrow** '
  'signal (climate change, global warming, greenhouse gas, carbon emissions, decarbonization, '
  'and similar) and a **broad** signal that adds sustainability, renewable energy, and clean '
  'energy. Across the scraped catalogs the narrow signal averages '
  f'**{mean_cn:.1f}%** of courses and the broad signal **{mean_cb:.1f}%**.')
w()
w('![Climate language top 20](figures/fig4_climate.png)')
w()
w('*Figure 4. The twenty scraped institutions with the highest broad climate-or-sustainability '
  'share. Dark bars show the narrow climate-change signal within each.*')
w()
cl = sorted([r for r in scraped if r['cb'] is not None], key=lambda r: r['cb'], reverse=True)[:15]
w('| # | University | Narrow climate % | Broad climate % |')
w('|--:|------------|:----------------:|:---------------:|')
for i, r in enumerate(cl, 1):
    w(f"| {i} | {r['name']} | {r['cn']:.1f} | {r['cb']:.1f} |")
w()
w('---')
w()
w('## 7. Limitations')
w()
w('- **Catalogs are not classrooms.** Keyword counts on public course descriptions do not reveal '
  'what is assigned, how a course is taught, or what students learn.')
w('- **Keyword lists are imperfect.** They produce false positives (e.g. *equity* in finance, '
  '*diversity* in biology, *classical* in physics) and false negatives (themes discussed without '
  'the listed words). The reference paper\'s false-positive audit estimated roughly 6% obvious '
  'false positives in the progressive signal; no comparable audit has been run on the 84 new '
  'catalogs.')
w('- **Single year, no enrollment weights.** Unlike Stanford in the reference paper, these '
  'institutions are observed once and weighted by course count, not student seats. Catalog '
  'availability overstates proportional student exposure.')
w('- **Uneven coverage.** Some catalogs omit departments that failed to scrape; per-institution '
  'failure counts are recorded in each `data/<uni>/<uni>_summary.json`. Constituent-college vs. '
  'university-wide coverage also varies.')
w()
w('---')
w()
w('## 8. Conclusion')
w()
w('Extending the catalog-language measurement from 16 to 100 institutions does not overturn the '
  'central finding of Marinovic (2026): progressive language is far more common than '
  f'Western-canon language in the stated curriculum, dominating at {above_diag} of 100 schools. '
  'What the wider sample adds is **context for magnitude**. The very high progressive shares that '
  'characterize the most-discussed elite catalogs are not representative of American higher '
  f'education as a whole; the median institution sits near {med_prog:.0f}%, and a long tail of '
  'regional, technical, and religious institutions sits well below that. The institutions where '
  'the canon still leads are a small and distinctive group — Christian colleges, plus one '
  'low-signal outlier. As in the original, these are rough, comparable signals rather than '
  'precise estimates, and they are offered for transparency and replication rather than as '
  'verdicts on any institution.')
w()
w('---')
w()
w('## Appendix: Data and Reproduction')
w()
w(f'- **Institutions:** 100 completed (84 scraped in this project + 16 from Marinovic 2026).')
w(f'- **Courses analyzed (scraped):** {tot_courses_scraped:,} deduplicated course records.')
w('- **Per-institution data:** `data/<uni>/<uni>_<year>.csv` (full records) and '
  '`data/<uni>/<uni>_summary.json` (signal shares, area composition, failed departments).')
w('- **Catalog status of all targeted institutions:** `progress.json`.')
w('- **Keyword lists and schema:** `schema.md`.')
w('- **Figures:** `reports/figures/`.')
w()
w('*Reference: Ivan Marinovic, "What Universities (Say They) Teach," Stanford University, '
  'June 2026.*')
w()

text = '\n'.join(L)
with open('reports/curriculum_report_100_universities.md', 'w') as f:
    f.write(text)
print(f'Report written: reports/curriculum_report_100_universities.md ({len(text):,} chars)')
print(f'Institutions in table: {len(ordered)}')
print(f'Progressive > canon at {above_diag}/100')
print(f'Course-weighted prog {cw_prog:.1f}% canon {cw_canon:.1f}%')
