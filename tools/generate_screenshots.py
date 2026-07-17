#!/usr/bin/env python3
"""
README Screenshot Generator
============================
Generates professional screenshots for the GitHub README.
Outputs to docs/screenshots/ — ready to embed in markdown.

Usage:
  python tools/generate_screenshots.py
"""

import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Use publication-quality settings
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.size': 10,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'axes.labelsize': 11,
    'figure.dpi': 150,
    'savefig.dpi': 150,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.15,
    'figure.facecolor': 'white',
})


def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)


def generate_screenshots():
    """Generate all README screenshots."""
    out_dir = Path(__file__).parent.parent / 'docs' / 'screenshots'
    ensure_dir(out_dir)

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from tools.demo_data import generate_demo_dataset, get_demo_tic, get_demo_peaks

    df = generate_demo_dataset()
    t, tic = get_demo_tic()
    peaks = get_demo_peaks()

    print("Generating screenshots...")

    # 1. TIC Chromatogram
    gen_tic(t, tic, peaks, out_dir / '01_tic_chromatogram.png')

    # 2. OAV Ranking
    gen_oav_bar(df, out_dir / '02_oav_ranking.png')

    # 3. PCA Score Plot
    gen_pca(df, out_dir / '03_pca_plot.png')

    # 4. Flavor Wheel
    gen_flavor_wheel(df, out_dir / '04_flavor_wheel.png')

    # 5. Volcano Plot
    gen_volcano(df, out_dir / '05_volcano_plot.png')

    # 6. Heatmap
    gen_heatmap(df, out_dir / '06_heatmap.png')

    print(f"\nAll screenshots saved to: {out_dir}")

    # Generate HTML index for preview
    index_html = '<html><body style="font-family:sans-serif;max-width:800px;margin:auto;padding:2rem;">\n'
    index_html += '<h1>GC-MS AI Analyzer — Screenshots</h1>\n'
    for f in sorted(out_dir.glob('*.png')):
        index_html += f'<h3>{f.stem}</h3>\n'
        index_html += f'<img src="{f.name}" style="max-width:100%;border:1px solid #ddd;border-radius:8px;margin-bottom:1rem;">\n'
    index_html += '</body></html>'
    (out_dir / 'index.html').write_text(index_html)


# ================================================================
# Chart Generators
# ================================================================

def gen_tic(times, intensities, peaks, out_path):
    """TIC chromatogram with peak annotations."""
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.plot(times, intensities, color='#1a5276', linewidth=0.8)
    ax.fill_between(times, intensities, alpha=0.1, color='#1a5276')

    # Annotate top peaks
    major = [p for p in peaks if p['snr'] > 80][:8]
    for p in major:
        ax.annotate(p['compound'], (p['rt'], p['height']),
                     textcoords="offset points", xytext=(0, 10),
                     fontsize=6, ha='center', color='#c0392b',
                     arrowprops=dict(arrowstyle='->', color='#c0392b', lw=0.5))

    ax.set_xlabel('Retention Time (min)')
    ax.set_ylabel('Intensity')
    ax.set_title('GC-MS Total Ion Chromatogram — Coffee Aroma Profile')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  [OK] {out_path.name}")


def gen_oav_bar(df, out_path):
    """OAV ranking bar chart."""
    from flavor_tools import calculate_oav, ODOR_THRESHOLDS

    df_oav = calculate_oav(df)
    top = df_oav.groupby('compound')['oav'].mean().sort_values(ascending=False).head(10)

    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ['#c0392b' if v > 100 else '#e67e22' if v > 10 else '#1a5276'
              for v in top.values]
    bars = ax.barh(range(len(top)), top.values, color=colors, height=0.6)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top.index, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel('Odor Activity Value (OAV)')
    ax.set_title('Top 10 Aroma-Impact Compounds (OAV)')
    ax.axvline(x=1, color='gray', linestyle='--', alpha=0.5, label='OAV=1 (threshold)')
    ax.legend(fontsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  [OK] {out_path.name}")


def gen_pca(df, out_path):
    """PCA score plot with group separation."""
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    pivot = df.pivot_table(values='area', index='sample', columns='compound', aggfunc='mean').fillna(0)
    X = StandardScaler().fit_transform(pivot)
    pca = PCA(n_components=2)
    scores = pca.fit_transform(X)
    groups = df.groupby('sample')['group'].first().values

    fig, ax = plt.subplots(figsize=(7, 5))
    for g, c, m in [('Roasted', '#c0392b', 'o'), ('Green', '#2980b9', 's')]:
        mask = groups == g
        ax.scatter(scores[mask, 0], scores[mask, 1], c=c, marker=m, s=80,
                   label=g, edgecolors='white', linewidth=0.5, zorder=5)

    ax.set_xlabel(f'PC1 ({pca.explained_variance_ratio_[0]:.1%})')
    ax.set_ylabel(f'PC2 ({pca.explained_variance_ratio_[1]:.1%})')
    ax.set_title('PCA Score Plot — Roasted vs Green Coffee')
    ax.legend()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  [OK] {out_path.name}")


def gen_flavor_wheel(df, out_path):
    """Simplified flavor wheel radar chart."""
    categories = df.groupby('category')['area'].sum().sort_values(ascending=False)
    cats = categories.index.tolist()
    vals = categories.values.tolist()

    angles = np.linspace(0, 2 * np.pi, len(cats), endpoint=False).tolist()
    angles += angles[:1]
    vals += vals[:1]

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    colors = ['#c0392b', '#e67e22', '#2980b9', '#27ae60', '#8e44ad',
              '#2c3e50', '#d35400', '#16a085'][:len(cats)]
    ax.fill(angles, vals, alpha=0.25, color='#1a5276')
    ax.plot(angles, vals, color='#1a5276', linewidth=2)
    for a, v, c, l in zip(angles, vals[:-1], colors, cats):
        ax.plot([a, a], [0, v], color=c, linewidth=2, alpha=0.6)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(cats, fontsize=7)
    ax.set_title('Coffee Aroma Profile by Compound Category', pad=20)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  [OK] {out_path.name}")


def gen_volcano(df, out_path):
    """Volcano plot: Roasted vs Green."""
    from scipy.stats import ttest_ind

    pivot = df.pivot_table(values='area', index='compound', columns='sample', aggfunc='mean').fillna(0)
    roasted_cols = [c for c in pivot.columns if 'Roasted' in c]
    green_cols = [c for c in pivot.columns if 'Green' in c]

    log2fc = []
    neg_log10p = []
    names = []
    for compound in pivot.index:
        r_vals = pivot.loc[compound, roasted_cols].values
        g_vals = pivot.loc[compound, green_cols].values
        if r_vals.mean() > 0 and g_vals.mean() > 0:
            fc = r_vals.mean() / g_vals.mean()
            log2fc.append(np.log2(fc))
            try:
                _, p = ttest_ind(r_vals, g_vals)
                neg_log10p.append(-np.log10(max(p, 1e-10)))
            except:
                neg_log10p.append(0)
            names.append(compound)

    log2fc = np.array(log2fc)
    neg_log10p = np.array(neg_log10p)

    fig, ax = plt.subplots(figsize=(8, 5))
    significant = neg_log10p > 1.3  # p < 0.05
    up = (log2fc > 1) & significant
    down = (log2fc < -1) & significant

    ax.scatter(log2fc[~significant], neg_log10p[~significant],
               c='#bdc3c7', s=20, alpha=0.5, label='Not significant')
    ax.scatter(log2fc[up], neg_log10p[up], c='#c0392b', s=40, label='Higher in Roasted')
    ax.scatter(log2fc[down], neg_log10p[down], c='#2980b9', s=40, label='Higher in Green')

    # Label top hits
    for i in np.argsort(neg_log10p)[-5:]:
        ax.annotate(names[i], (log2fc[i], neg_log10p[i]),
                     fontsize=7, xytext=(5, 5), textcoords='offset points')

    ax.axhline(-np.log10(0.05), color='gray', linestyle='--', alpha=0.5)
    ax.set_xlabel('log2 Fold Change (Roasted / Green)')
    ax.set_ylabel('-log10(p-value)')
    ax.set_title('Volcano Plot: Roasted vs Green Coffee Beans')
    ax.legend(fontsize=8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  [OK] {out_path.name}")


def gen_heatmap(df, out_path):
    """Top 20 compounds heatmap."""
    pivot = df.pivot_table(values='area', index='compound', columns='sample', aggfunc='mean').fillna(0)
    # Top 20 by variance
    top = pivot.var(axis=1).sort_values(ascending=False).head(20).index
    data = pivot.loc[top]

    # Normalize by row
    data_norm = data.apply(lambda x: (x - x.min()) / (x.max() - x.min() + 1e-10), axis=1)

    fig, ax = plt.subplots(figsize=(10, 5))
    im = ax.imshow(data_norm.values, aspect='auto', cmap='RdBu_r')
    ax.set_xticks(range(len(data_norm.columns)))
    ax.set_xticklabels(data_norm.columns, rotation=45, ha='right', fontsize=7)
    ax.set_yticks(range(len(data_norm.index)))
    ax.set_yticklabels(data_norm.index, fontsize=8)
    ax.set_title('Top 20 Discriminating Compounds — Heatmap')
    plt.colorbar(im, ax=ax, shrink=0.8, label='Normalized Area')
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  [OK] {out_path.name}")


if __name__ == '__main__':
    generate_screenshots()
