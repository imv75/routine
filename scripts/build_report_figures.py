#!/usr/bin/env python3
"""Generate figures for the 100-university comprehensive report."""
import json, os, statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

os.makedirs('reports/figures', exist_ok=True)
with open('/tmp/agg.json') as f:
    R = json.load(f)

scraped = [r for r in R if r['source'] == 'scraped']

# ---- Figure 1: Scatter prog vs canon, all 100 ----
fig, ax = plt.subplots(figsize=(8, 6))
xs = [r['canon'] for r in R]
ys = [r['prog'] for r in R]
colors = ['#c0392b' if r['source'] != 'scraped' else '#2c7fb8' for r in R]
ax.scatter(xs, ys, c=colors, alpha=0.7, s=40, edgecolors='white', linewidth=0.5)
# diagonal prog=canon
lim = max(max(xs), max(ys)) + 2
ax.plot([0, lim], [0, lim], '--', color='gray', linewidth=1, label='Progressive = Canon')
ax.set_xlabel('Western-canon signal (% of courses)')
ax.set_ylabel('Progressive signal (% of courses)')
ax.set_title('Progressive vs. Western-Canon Signal, 100 Universities (latest catalog)')
# annotate a few notable
notable = {'uchicago','yale','nyu','princeton','stanford','biola','csp','marshall','tamucc','mwcc'}
for r in R:
    if r['key'] in notable:
        ax.annotate(r['name'], (r['canon'], r['prog']), fontsize=7,
                    xytext=(3, 3), textcoords='offset points')
from matplotlib.lines import Line2D
leg = [Line2D([0],[0], marker='o', color='w', markerfacecolor='#2c7fb8', label='Scraped (this project, 84)', markersize=8),
       Line2D([0],[0], marker='o', color='w', markerfacecolor='#c0392b', label='Marinovic (2026) reference (16)', markersize=8),
       Line2D([0],[0], linestyle='--', color='gray', label='Progressive = Canon')]
ax.legend(handles=leg, loc='upper right', fontsize=8)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('reports/figures/fig1_scatter.png', dpi=130)
plt.close()

# ---- Figure 2: Top/bottom 20 by progressive share ----
ranked = sorted(R, key=lambda r: r['prog'], reverse=True)
top = ranked[:20]
bot = ranked[-20:]
fig, axes = plt.subplots(1, 2, figsize=(12, 7))
for ax, grp, title in [(axes[0], top, 'Highest progressive share'),
                        (axes[1], bot, 'Lowest progressive share')]:
    names = [r['name'] for r in grp][::-1]
    vals = [r['prog'] for r in grp][::-1]
    cols = ['#c0392b' if r['source'] != 'scraped' else '#2c7fb8' for r in grp][::-1]
    ax.barh(names, vals, color=cols)
    ax.set_xlabel('Progressive signal (%)')
    ax.set_title(title)
    ax.tick_params(axis='y', labelsize=7)
    ax.grid(True, axis='x', alpha=0.3)
plt.suptitle('Progressive Signal Ranking, 100 Universities', y=1.00)
plt.tight_layout()
plt.savefig('reports/figures/fig2_ranking.png', dpi=130)
plt.close()

# ---- Figure 3: Distribution histogram ----
fig, ax = plt.subplots(figsize=(8, 5))
ax.hist([r['prog'] for r in R], bins=20, color='#2c7fb8', alpha=0.8, edgecolor='white', label='Progressive')
ax.hist([r['canon'] for r in R], bins=20, color='#c0392b', alpha=0.6, edgecolor='white', label='Western canon')
ax.axvline(statistics.mean(r['prog'] for r in R), color='#2c7fb8', linestyle='--', linewidth=1.5)
ax.axvline(statistics.mean(r['canon'] for r in R), color='#c0392b', linestyle='--', linewidth=1.5)
ax.set_xlabel('Share of courses (%)')
ax.set_ylabel('Number of universities')
ax.set_title('Distribution of Signal Shares Across 100 Universities')
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('reports/figures/fig3_distribution.png', dpi=130)
plt.close()

# ---- Figure 4: Climate (broad) top 20, scraped only ----
cl = sorted([r for r in scraped if r['cb'] is not None], key=lambda r: r['cb'], reverse=True)[:20]
fig, ax = plt.subplots(figsize=(9, 7))
names = [r['name'] for r in cl][::-1]
broad = [r['cb'] for r in cl][::-1]
narrow = [r['cn'] for r in cl][::-1]
ax.barh(names, broad, color='#7fcdbb', label='Broad (incl. sustainability)')
ax.barh(names, narrow, color='#2c7fb8', label='Narrow (climate change)')
ax.set_xlabel('Share of courses (%)')
ax.set_title('Climate-Related Course Language, Top 20 (scraped universities)')
ax.tick_params(axis='y', labelsize=7)
ax.legend()
ax.grid(True, axis='x', alpha=0.3)
plt.tight_layout()
plt.savefig('reports/figures/fig4_climate.png', dpi=130)
plt.close()

print('Figures written to reports/figures/')
for f in sorted(os.listdir('reports/figures')):
    print(' ', f)
