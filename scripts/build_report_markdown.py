#!/usr/bin/env python3
"""Assemble the comprehensive multi-university curriculum report (Markdown)."""
import json, statistics

with open('/tmp/agg.json') as f:
    R = json.load(f)
# "collected" = freshly scraped catalogs (original scrapes + re-scraped reference universities)
collected = [r for r in R if r['source'] in ('scraped', 'rescraped')]
rescraped = [r for r in R if r['source'] == 'rescraped']
paper = [r for r in R if r['source'] == 'Marinovic (2026)']
N_COLLECTED, N_RESCRAPED, N_PAPER = len(collected), len(rescraped), len(paper)
N_TOTAL = len(R)

def area_count(n):
    return n['courses'] if isinstance(n, dict) else n

tot_courses = sum(r['total'] for r in collected)
cw_prog = sum(r['prog'] * r['total'] for r in collected) / tot_courses
cw_canon = sum(r['canon'] * r['total'] for r in collected) / tot_courses
mean_prog = statistics.mean(r['prog'] for r in R)
mean_canon = statistics.mean(r['canon'] for r in R)
med_prog = statistics.median(r['prog'] for r in R)
med_canon = statistics.median(r['canon'] for r in R)
sd_prog = statistics.pstdev(r['prog'] for r in R)
min_prog = min(r['prog'] for r in R)
max_prog = max(r['prog'] for r in R)

canon_wins = sorted([r for r in R if r['canon'] > r['prog']], key=lambda r: r['name'])
canon_wins_names = ', '.join(r['name'] for r in canon_wins)

cn = [r['cn'] for r in collected if r['cn'] is not None]
cb = [r['cb'] for r in collected if r['cb'] is not None]
mean_cn = statistics.mean(cn); mean_cb = statistics.mean(cb)

area_tot = {}
for r in collected:
    for a, n in r['by_area'].items():
        area_tot[a] = area_tot.get(a, 0) + area_count(n)
grand = sum(area_tot.values())

above_diag = sum(1 for r in R if r['prog'] > r['canon'])

L = []
def w(s=''): L.append(s)

w(f'# What {N_TOTAL} Universities (Say They) Teach')
w()
w(f'### A cross-sectional extension of Marinovic (2026) to {N_TOTAL} U.S. institutions')
w()
w('*Generated automatically by the catalog-collection routine — July 2026*')
w()
w('---')
w()
w('## Abstract')
w()
w('This report extends the catalog-language analysis of Marinovic (2026), *What Universities '
  '(Say They) Teach*, from its original 16-university comparison set to '
  f'**{N_TOTAL} U.S. institutions**. Following the reference methodology, each course title and '
  'description is searched for two keyword families: a **progressive signal** (race, gender, '
  'identity, diversity, equity, social justice, decolonial, and related themes) and a '
  '**Western-canon signal** (classical antiquity, the Western intellectual tradition, canonical '
  f'authors and texts). The sample combines **{N_COLLECTED} freshly collected catalogs** — '
  f'{N_COLLECTED - N_RESCRAPED} regional, public, and private institutions plus **{N_RESCRAPED} '
  'of the original reference universities re-scraped from their current 2026 catalogs** '
  '(Stanford, MIT, Cornell, Northwestern, NYU, UIUC, U. Iowa) — with the remaining '
  f'**{N_PAPER}** reference universities cited from Marinovic (2026) because their catalogs are '
  f'dynamic-JS or proxy-blocked. Across the {N_COLLECTED} collected catalogs — '
  f'**{tot_courses:,} deduplicated courses** — the course-weighted progressive signal is '
  f'**{cw_prog:.1f}%** and the Western-canon signal is **{cw_canon:.1f}%**. The central pattern '
  f'of the original paper holds: the progressive signal exceeds the Western-canon signal at '
  f'**{above_diag} of {N_TOTAL}** institutions, typically by a factor of three to four. The '
  f'signal is far from uniform — progressive shares range from {min_prog:.1f}% to over '
  f'{max_prog:.0f}% — and the few institutions where the canon signal dominates are Christian '
  'colleges or low-signal outliers. These measures are mechanical keyword counts, not judgments '
  'about course quality or what is taught in classrooms.')
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
w(f'The {N_TOTAL} institutions here are deliberately heterogeneous. They include private research '
  'universities, large public flagships, regional public universities, technical institutes, '
  'religious colleges, and community colleges. This breadth is the point: the original sample '
  'explicitly omitted "community colleges, regional public universities, and most liberal-arts '
  'colleges," and this extension fills in exactly those gaps. Where the original reference '
  'catalogs could be reached, they were re-scraped directly (§4.4); where they could not, the '
  'published figures are carried over.')
w()
w('As in the reference report, this is a descriptive exercise. It does not judge the quality of '
  'individual courses or the seriousness of any field. It asks only how often certain themes '
  'appear in the official language by which universities describe their courses.')
w()
w('---')
w()
w('## 2. Data and Method')
w()
w('**Coverage.** The report combines two kinds of evidence:')
w()
w(f'- **{N_COLLECTED} freshly collected catalogs** scraped from each institution\'s current '
  f'public catalog (almost all 2026–2027) and parsed into the common schema below. This includes '
  f'{N_COLLECTED - N_RESCRAPED} regional/public/private institutions plus **{N_RESCRAPED} of the '
  'original reference universities** (Stanford via the ExploreCourses XML API; MIT, Northwestern, '
  'NYU, UIUC, and U. Iowa via their CourseleafCMS catalogs; Cornell via the Class Roster API). '
  f'Together these contain **{tot_courses:,} deduplicated courses**.')
w(f'- **{N_PAPER} reference catalogs** carried over from Marinovic (2026) — UC Berkeley, Harvard, '
  'Yale, Princeton, U. Chicago, Columbia, Vanderbilt, UT Austin, and Texas A&M — whose public '
  'catalogs are dynamic-JS single-page apps or are blocked from the collection environment and '
  'could not be re-scraped. Their latest-year shares are reproduced from Table 6 of that paper.')
w()
w('**Keyword matching.** Matching is case-insensitive substring matching against the same '
  'progressive and Western-canon keyword lists used throughout this project (reproduced in '
  '`schema.md`, and themselves drawn from Tables 2–3 of the reference paper). A course carries a '
  'signal if its combined title-plus-description contains at least one keyword from the '
  'corresponding list. Cross-listed duplicates are collapsed to one course-year before any share '
  'is computed. The two signals are not mutually exclusive.')
w()
w('**Caveats specific to this extension:**')
w()
w('1. **Single-year snapshot.** The collected catalogs are observed in a single recent catalog '
  'year, so this is a cross-section, not a panel; it cannot speak to trends over time.')
w('2. **Coarser area classification.** Broad academic areas are assigned by a mechanical '
  'department/title keyword map, so the residual **"Other"** category is large and should be read '
  'as "unclassified."')
w('3. **Full catalog, no enrollment weights.** All shares are unweighted course counts over the '
  'full published catalog. The reference paper\'s headline figures instead restrict to *offered '
  'and enrollment-observed* courses and use word-boundary matching, so re-scraped values here run '
  'systematically higher than the paper\'s published numbers (quantified in §4.4).')
w()
w('---')
w()
w('## 3. Headline Findings')
w()
w(f'- **The progressive signal dominates the canon signal almost everywhere.** At **{above_diag} '
  f'of {N_TOTAL}** institutions the progressive share exceeds the Western-canon share. Across the '
  f'{N_COLLECTED} collected catalogs the course-weighted progressive signal ({cw_prog:.1f}%) is '
  f'about **{cw_prog/cw_canon:.1f}×** the canon signal ({cw_canon:.1f}%).')
w(f'- **Typical magnitudes are well below the elite tail.** The median institution carries the '
  f'progressive signal on **{med_prog:.1f}%** of courses and the canon signal on **{med_canon:.1f}%**. '
  f'The simple mean across all {N_TOTAL} is **{mean_prog:.1f}%** progressive and **{mean_canon:.1f}%** '
  'canon. The most progressive catalogs — Stanford and the elite privates — sit in the upper '
  'tail, not at the center.')
w(f'- **Enormous dispersion.** Progressive shares span roughly **{min_prog:.1f}% to {max_prog:.0f}%** '
  f'(standard deviation {sd_prog:.1f} points). The spread is institutional, not just disciplinary: '
  f'regional and technical schools cluster low, while research universities and several small '
  f'private colleges cluster high.')
w(f'- **Where the canon wins, it is usually religious.** Only {len(canon_wins)} institutions carry '
  f'more canonical than progressive language: {canon_wins_names}. Biola and Cornerstone are '
  'Christian colleges where biblical and classical-author keywords are common; Marshall is an '
  'outlier whose unusually low progressive share reflects short, sparse catalog descriptions.')
w(f'- **Climate language is modest but pervasive.** Across collected catalogs the narrow climate '
  f'signal averages **{mean_cn:.1f}%** of courses and the broad climate-or-sustainability signal '
  f'**{mean_cb:.1f}%**.')
w()
w(f'![Progressive vs. Western-canon signal across {N_TOTAL} universities](figures/fig1_scatter.png)')
w()
w('*Figure 1. Each point is one institution\'s latest catalog. Points above the dashed line '
  f'carry more progressive than canonical language. Blue = the {N_COLLECTED - N_RESCRAPED} '
  f'regional/public/private catalogs; green = the {N_RESCRAPED} re-scraped 2026 reference '
  f'catalogs; red = the {N_PAPER} reference catalogs still cited from Marinovic (2026).*')
w()
w('![Distribution of signal shares](figures/fig3_distribution.png)')
w()
w(f'*Figure 2. Distribution of progressive and Western-canon shares across all {N_TOTAL} '
  'institutions. Dashed lines mark the means.*')
w()
w('---')
w()
w(f'## 4. Cross-Sectional Comparison (all {N_TOTAL} institutions)')
w()
w('Table 1 reports every institution\'s latest-catalog progressive and Western-canon shares, the '
  'ratio between them, and the number of courses analyzed. As in Table 6 of the reference paper, '
  'institutions are sorted from the highest progressive-to-canon ratio to the lowest. The Source '
  'column marks each row as `scraped` (this project), `re-scrape` (a reference university '
  're-scraped from its 2026 catalog), or `paper` (carried over from Marinovic 2026).')
w()
w('| # | University | Year | Courses | Progressive % | Canon % | Prog./Canon | Source |')
w('|--:|------------|:----:|--------:|:------------:|:-------:|:-----------:|--------|')
SRCLABEL = {'scraped': 'scraped', 'rescraped': 're-scrape', 'Marinovic (2026)': 'paper'}
rated = [r for r in R if r['ratio'] is not None]
unrated = [r for r in R if r['ratio'] is None]
ordered = sorted(rated, key=lambda r: r['ratio'], reverse=True) + unrated
for i, r in enumerate(ordered, 1):
    src = SRCLABEL[r['source']]
    ratio = f"{r['ratio']:.2f}" if r['ratio'] is not None else '—'
    star = '' if r['source'] in ('scraped', 'rescraped') else '*'
    tot = f"{r['total']:,}{star}"
    w(f"| {i} | {r['name']} | {r['year']} | {tot} | {r['prog']:.1f} | {r['canon']:.1f} | {ratio} | {src} |")
w()
w(f'*\\* For the {N_PAPER} paper-only institutions the course count is the total course-years in '
  'Marinovic (2026), not a single-year count; their shares are latest-year (2024/2025) values '
  'from that paper. Collected course counts are deduplicated single-year (mostly 2026–2027).*')
w()
w('![Progressive ranking](figures/fig2_ranking.png)')
w()
w('*Figure 3. The twenty highest and twenty lowest institutions by progressive share.*')
w()
# ---- 4.4 Re-scraped reference comparison ----
w('### 4.4 Re-scraped reference universities: 2026 catalog vs. published figures')
w()
w(f'{N_RESCRAPED} of the sixteen original reference universities could be re-scraped from their '
  'live 2026 '
  'catalogs. Table 2 places the freshly scraped shares next to the values Marinovic (2026) '
  'reported. The re-scraped numbers are consistently higher, for two structural reasons. First, '
  'this project scrapes the **entire published catalog**, whereas the paper restricts its '
  'headline shares to courses that were actually *offered and had observed enrollment* — a '
  'smaller, less seminar-heavy population. Second, this project uses **substring matching** while '
  'the paper uses **word-boundary matching**. Both effects push the same direction. The gap is '
  'therefore a methodological artifact, not evidence that these catalogs changed dramatically '
  'between the paper\'s year and 2026; the *relative ordering* is largely preserved.')
w()
w('| University | 2026 re-scrape Prog % | Paper Prog % | 2026 re-scrape Canon % | Paper Canon % | 2026 courses |')
w('|------------|:--------------------:|:------------:|:----------------------:|:-------------:|:------------:|')
order_rescrape = ['stanford', 'nyu', 'cornell', 'uiowa', 'northwestern', 'uiuc', 'mit']
byk = {r['key']: r for r in R}
for k in order_rescrape:
    r = byk[k]
    pp, pc = r.get('paper') or (None, None)
    pp = f"{pp:.1f}" if pp is not None else '—'
    pc = f"{pc:.1f}" if pc is not None else '—'
    w(f"| {r['name']} | {r['prog']:.1f} | {pp} | {r['canon']:.1f} | {pc} | {r['total']:,} |")
w()
w('Note: Northwestern is the undergraduate catalog only (the paper covers the full university); '
  'its course count is correspondingly smaller.')
w()
w('---')
w()
w('## 5. Catalog Composition')
w()
w('Universities differ mechanically in the mix of courses they offer, which shapes baseline '
  f'exposure to each keyword list. Table 3 aggregates the broad-area composition across the '
  f'{N_COLLECTED} collected catalogs. The large **Other** share reflects the coarse, '
  'keyword-based area classifier used in this extension (see §2) and should be read as '
  '"unclassified."')
w()
w('| Broad area | Courses | Share of collected catalog |')
w('|------------|--------:|:--------------------------:|')
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
  'signal (climate change, global warming, greenhouse gas, carbon emissions, and similar) and a '
  '**broad** signal that adds sustainability, renewable energy, and clean energy. Across the '
  f'collected catalogs the narrow signal averages **{mean_cn:.1f}%** of courses and the broad '
  f'signal **{mean_cb:.1f}%**.')
w()
w('![Climate language top 20](figures/fig4_climate.png)')
w()
w('*Figure 4. The twenty collected institutions with the highest broad climate-or-sustainability '
  'share. Dark bars show the narrow climate-change signal within each.*')
w()
cl = sorted([r for r in collected if r['cb'] is not None], key=lambda r: r['cb'], reverse=True)[:15]
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
w('- **Keyword lists are imperfect.** Substring matching produces false positives (e.g. *race* '
  'in "race car," *equity* in finance, *classical* in physics) and false negatives (themes '
  'discussed without the listed words). This matters most for the full-catalog re-scrapes in §4.4.')
w('- **Population and matching differences.** The re-scraped reference values are not directly '
  'comparable to the paper\'s published figures (full catalog + substring here vs. offered-subset '
  '+ word-boundary there); they ARE comparable to the other collected catalogs in this report.')
w(f'- **Uneven coverage.** {N_PAPER} reference universities could not be re-scraped and retain '
  'paper values; Northwestern is undergraduate-only; per-institution scrape failures are '
  'recorded in each `data/<uni>/<uni>_summary.json`.')
w()
w('---')
w()
w('## 8. Conclusion')
w()
w(f'Extending the catalog-language measurement from 16 to {N_TOTAL} institutions — and '
  f're-scraping {N_RESCRAPED} of the original reference universities from their 2026 catalogs — '
  'does not overturn the central finding of Marinovic (2026): progressive language is far more '
  'common than Western-canon language in the stated curriculum, dominating at '
  f'{above_diag} of {N_TOTAL} schools. '
  'What the wider sample adds is **context for magnitude**. The very high progressive shares that '
  'characterize the most-discussed elite catalogs are not representative of American higher '
  f'education as a whole; the median institution sits near {med_prog:.0f}%, and a long tail of '
  'regional, technical, and religious institutions sits well below that. The institutions where '
  'the canon still leads are a small and distinctive group — Christian colleges, plus one '
  'low-signal outlier. As in the original, these are rough, comparable signals rather than '
  'precise estimates, offered for transparency and replication rather than as verdicts on any '
  'institution.')
w()
w('---')
w()
w('## Appendix: Data and Reproduction')
w()
w(f'- **Institutions:** {N_TOTAL} total — {N_COLLECTED} freshly collected ({N_COLLECTED - N_RESCRAPED} '
  f'this project + {N_RESCRAPED} re-scraped reference) and {N_PAPER} carried over from Marinovic '
  '(2026).')
w(f'- **Courses analyzed (collected):** {tot_courses:,} deduplicated course records.')
w('- **Per-institution data:** `data/<uni>/<uni>_<year>.csv` (full records) and '
  '`data/<uni>/<uni>_summary.json` (signal shares, area composition, failed departments).')
w('- **Re-scrape script:** `scripts/scrape_reference16.py`. **Report build:** '
  '`scripts/build_report_*.py`. **Catalog status of all targets:** `progress.json`. '
  '**Keyword lists and schema:** `schema.md`. **Figures:** `reports/figures/`.')
w()
w('*Reference: Ivan Marinovic, "What Universities (Say They) Teach," Stanford University, '
  'June 2026.*')
w()

text = '\n'.join(L)
with open('reports/curriculum_report_100_universities.md', 'w') as f:
    f.write(text)
print(f'Report written: reports/curriculum_report_100_universities.md ({len(text):,} chars)')
print(f'Collected {N_COLLECTED} (incl {N_RESCRAPED} re-scraped) + paper {N_PAPER} = {N_TOTAL} total')
print(f'Progressive > canon at {above_diag}/{N_TOTAL}; course-wt prog {cw_prog:.1f}% canon {cw_canon:.1f}%')
