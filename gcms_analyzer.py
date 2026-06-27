#!/usr/bin/env python3
"""
ChemStation .D Data Auto-Analyzer
==================================
Automated processing, plotting, and analysis of Agilent ChemStation .D data
for GC/MS, HPLC, GC-FID, and other chromatographic methods.

Scans all .D folders, parses REPORT01.CSV / Report.TXT files, and generates:
- Comparative bar charts, heatmaps, PCA plots, boxplots, volcano plots
- Statistical analysis with Excel summary workbook
- Publication-quality figures (300 dpi)

Usage:
    python gcms_analyzer.py
    python gcms_analyzer.py --data-dir "path/to/data"
    python gcms_analyzer.py --no-plots  # skip plotting, only Excel export
"""

import os
import sys
import re
import glob
import argparse
from pathlib import Path
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch
import seaborn as sns
from scipy import stats
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# ============================================================
# CONFIGURATION
# ============================================================

# Default data directory (set to None to require --data-dir argument)
DEFAULT_DATA_DIR = None

# Output directory
OUTPUT_DIR = Path(__file__).parent / "output"
PLOTS_DIR = OUTPUT_DIR / "plots"

# Plot settings
plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'Arial'],
    'axes.unicode_minus': False,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'figure.figsize': (14, 8),
})

# Color palette for groups
GROUP_COLORS = {
    '脱胆固醇 凝胶': '#3498db',
    '脱胆固醇 液体': '#2ecc71',
    '酶解蛋黄液 凝胶': '#e74c3c',
    '抗氧化剂 凝胶': '#f39c12',
    'Unknown': '#95a5a6',
}

# Compounds are auto-detected from data — no preset list needed.

# ============================================================
# DATA SCANNER & PARSER
# ============================================================

def scan_d_folders(data_dir):
    """Scan all .D folders and return list with metadata."""
    data_path = Path(data_dir)
    if not data_path.exists():
        print(f"[ERROR] Data directory not found: {data_dir}")
        return []

    all_dirs = sorted(data_path.rglob("*.D"))
    print(f"\n{'='*60}")
    print(f"  SCANNING: {data_dir}")
    print(f"{'='*60}")
    print(f"  Found {len(all_dirs)} .D folders total\n")

    results = []
    for d in all_dirs:
        group = d.parent.name if d.parent != data_path else "Root"
        sample_name = d.name

        # Find report files
        report_files = {
            'csv': list(d.glob("REPORT01.CSV")) + list(d.glob("Report*.CSV")),
            'txt': list(d.glob("Report*.TXT")),
            'xls': list(d.glob("Report*.XLS")),
        }

        has_reports = any(report_files.values())

        info = {
            'path': str(d),
            'name': sample_name,
            'group': group,
            'has_reports': has_reports,
            'reports': report_files,
        }

        if has_reports:
            print(f"  ✅ {sample_name:40s} [{group}] — {sum(len(v) for v in report_files.values())} reports")
        else:
            print(f"  ⚠️  {sample_name:40s} [{group}] — NO reports (raw data only)")

        results.append(info)

    return results


def parse_report_csv(filepath):
    """Parse a ChemStation REPORT01.CSV (UTF-16 LE, comma-delimited).

    Returns list of dicts with keys: rt, peak_type, area, amount, conc_g100g, compound
    """
    try:
        # Read UTF-16 LE with BOM
        with open(filepath, 'r', encoding='utf-16-le', errors='ignore') as f:
            raw = f.read()

        lines = raw.strip().split('\n')
        peaks = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Split by comma, respecting quoted fields
            parts = parse_csv_line(line)

            if len(parts) < 8:
                continue

            try:
                rt = float(parts[0].strip())
                peak_type = parts[1].strip().strip('"')
                area = float(parts[2].strip())
                amount = float(parts[3].strip())
                conc = float(parts[4].strip())
                compound = parts[7].strip().strip('"').lower()

                if compound and len(compound) <= 20:  # reasonable compound name
                    peaks.append({
                        'rt': rt,
                        'peak_type': peak_type,
                        'area': area,
                        'amount': amount,
                        'conc_g100g': conc,
                        'compound': compound,
                    })
            except (ValueError, IndexError):
                continue

        return peaks

    except Exception as e:
        print(f"    [WARN] Error parsing {filepath}: {e}")
        return []


def parse_csv_line(line):
    """Parse a CSV line handling quoted fields."""
    parts = []
    current = []
    in_quotes = False

    for char in line:
        if char == '"':
            in_quotes = not in_quotes
            current.append(char)
        elif char == ',' and not in_quotes:
            parts.append(''.join(current))
            current = []
        else:
            current.append(char)

    if current:
        parts.append(''.join(current))

    return parts


def extract_all_data(d_folders):
    """Extract chromatographic peak data from all .D folders with reports."""
    all_records = []
    skipped = []

    for info in d_folders:
        if not info['has_reports']:
            skipped.append(info)
            continue

        # Use REPORT01.CSV (most structured)
        csv_files = info['reports']['csv']
        if not csv_files:
            # Fall back to parsing TXT
            txt_files = info['reports']['txt']
            if txt_files:
                # For now skip TXT parsing (more complex format)
                print(f"  [WARN] {info['name']}: Only TXT reports, skipping")
            skipped.append(info)
            continue

        # Use the first CSV found
        csv_path = csv_files[0]
        peaks = parse_report_csv(csv_path)

        if not peaks:
            print(f"  [WARN] {info['name']}: No peaks parsed from {csv_path.name}")
            skipped.append(info)
            continue

        # Extract sample number for ordering
        sample_num = extract_sample_number(info['name'])

        # Detect sub-group from sample name
        sub_group = detect_sub_group(info['name'], info['group'])

        for peak in peaks:
            all_records.append({
                'group': info['group'],
                'sub_group': sub_group,
                'sample': info['name'],
                'sample_num': sample_num,
                'compound': peak['compound'],
                'rt': peak['rt'],
                'peak_type': peak['peak_type'],
                'area': peak['area'],
                'amount': peak['amount'],
                'conc_g100g': peak['conc_g100g'],
            })

    df = pd.DataFrame(all_records)
    print(f"\n  📊 Parsed {len(df)} peak records from {df['sample'].nunique()} samples")
    print(f"  ⚠️  Skipped {len(skipped)} samples (no reports)")

    return df, skipped


def extract_sample_number(sample_name):
    """Extract numeric sample number from folder name."""
    match = re.search(r'(\d+)\s*唐|(\d+)\s*\.D', sample_name)
    if match:
        return int(match.group(1) or match.group(2))
    return 999


def detect_sub_group(sample_name, group):
    """Detect sub-group from sample name (e.g., 蛋黄凝胶 vs 蛋黄液体)."""
    if '液体' in sample_name:
        return f"{group} - 液体"
    elif '凝胶' in sample_name:
        return f"{group} - 凝胶"
    elif '蛋黄' in sample_name:
        return f"{group} - 蛋黄"
    return group


# ============================================================
# ANALYSIS MODULE
# ============================================================

def analyze_data(df):
    """Perform statistical analysis on extracted data."""
    print(f"\n{'='*60}")
    print(f"  STATISTICAL ANALYSIS")
    print(f"{'='*60}")

    # Pivot: samples x compounds (concentration)
    pivot = df.pivot_table(
        values='conc_g100g',
        index=['group', 'sub_group', 'sample', 'sample_num'],
        columns='compound',
        aggfunc='mean'
    ).reset_index()

    # Sort by sample_num
    pivot = pivot.sort_values(['group', 'sample_num'])

    # Per-group statistics
    groups = df['group'].unique()
    stats_list = []

    for group_name in groups:
        group_df = df[df['group'] == group_name]
        compounds = group_df['compound'].unique()

        for comp in compounds:
            comp_data = group_df[group_df['compound'] == comp]['conc_g100g']
            stats_list.append({
                'group': group_name,
                'compound': comp,
                'mean': comp_data.mean(),
                'std': comp_data.std(),
                'cv_pct': (comp_data.std() / comp_data.mean() * 100) if comp_data.mean() > 0 else 0,
                'min': comp_data.min(),
                'max': comp_data.max(),
                'n': len(comp_data),
            })

    stats_df = pd.DataFrame(stats_list)

    # Between-group comparison (if 2+ groups with data)
    groups_with_data = [g for g in groups if len(df[df['group'] == g]) > 0]
    comparison = []

    if len(groups_with_data) >= 2:
        for comp in df['compound'].unique():
            group_data = {}
            for g in groups_with_data:
                vals = df[(df['group'] == g) & (df['compound'] == comp)]['conc_g100g'].dropna()
                if len(vals) >= 2:
                    group_data[g] = vals.values

            if len(group_data) >= 2:
                group_names = list(group_data.keys())
                # ANOVA-like: compare first two groups with t-test
                g1, g2 = group_names[0], group_names[1]
                try:
                    t_stat, p_val = stats.ttest_ind(group_data[g1], group_data[g2])
                    comparison.append({
                        'compound': comp,
                        'group_1': g1,
                        'group_2': g2,
                        f'mean_{g1[:8]}': np.mean(group_data[g1]),
                        f'mean_{g2[:8]}': np.mean(group_data[g2]),
                        't_statistic': t_stat,
                        'p_value': p_val,
                        'significant': '***' if p_val < 0.001 else ('**' if p_val < 0.01 else ('*' if p_val < 0.05 else 'ns')),
                    })
                except Exception as e:
                    print(f"  [WARN] t-test failed for {comp}: {e}")

    comparison_df = pd.DataFrame(comparison)

    # Composition ratio (% of total compounds per sample)
    comp_ratio = pivot.copy()
    # Exclude metadata columns
    meta_cols = {'group', 'sub_group', 'sample', 'sample_num', 'label'}
    pivot_aa_cols = [c for c in pivot.columns if c not in meta_cols]
    if pivot_aa_cols:
        sample_totals = pivot[pivot_aa_cols].sum(axis=1)
        for col in pivot_aa_cols:
            comp_ratio[col + '_pct'] = (pivot[col] / sample_totals * 100).round(2)

    # Print summary
    print(f"\n  Groups: {', '.join(groups)}")
    print(f"  Compounds detected: {df['compound'].nunique()}")
    if not comparison_df.empty:
        sig_count = (comparison_df['p_value'] < 0.05).sum()
        print(f"  Significant differences (p<0.05): {sig_count}/{len(comparison_df)}")

    return {
        'pivot': pivot,
        'stats': stats_df,
        'comparison': comparison_df,
        'composition_ratio': comp_ratio,
    }


# ============================================================
# VISUALIZATION MODULE
# ============================================================

def plot_grouped_bar(pivot, output_path, aa_cols):
    """Grouped bar chart: compound concentration by sample."""
    print(f"\n  📊 Plotting grouped bar chart...")

    # Prepare data
    plot_data = pivot.copy()
    plot_data['label'] = plot_data['sample'].str.replace(r'\.D$', '', regex=True)
    plot_data['label'] = plot_data['label'].str.replace(r'唐婷婷-', '', regex=True)
    plot_data = plot_data.sort_values(['group', 'sample_num'])

    n_samples = len(plot_data)
    n_compounds = len(aa_cols)

    fig, ax = plt.subplots(figsize=(max(16, n_samples * 0.8), 10))

    x = np.arange(n_samples)
    width = 0.8 / n_compounds
    colors = plt.cm.tab20(np.linspace(0, 1, n_compounds))

    for i, comp in enumerate(aa_cols):
        if comp not in plot_data.columns:
            continue
        offset = (i - n_compounds / 2 + 0.5) * width
        bars = ax.bar(x + offset, plot_data[comp].fillna(0), width,
                      label=comp, color=colors[i % len(colors)])

    ax.set_xticks(x)
    ax.set_xticklabels(plot_data['label'], rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Concentration [g/100g]', fontsize=13)
    ax.set_title('Compound Concentration by Sample', fontsize=16, fontweight='bold')
    ax.legend(loc='upper right', fontsize=7, ncol=2, framealpha=0.9)
    ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Color-code groups
    for i, (_, row) in enumerate(plot_data.iterrows()):
        group = row['group']
        if group in GROUP_COLORS:
            ax.axvspan(i - 0.4, i + 0.4, alpha=0.08, color=GROUP_COLORS[group], zorder=0)

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"     Saved: {output_path}")


def plot_heatmap(pivot, output_path, aa_cols):
    """Heatmap of compound profiles across samples."""
    print(f"\n  🔥 Plotting heatmap...")

    plot_data = pivot.copy()
    plot_data['label'] = plot_data['sample'].str.replace(r'\.D$', '', regex=True)
    plot_data['label'] = plot_data['label'].str.replace(r'唐婷婷-', '', regex=True)
    plot_data = plot_data.set_index('label')

    # Select only AA columns that exist
    available_cols = [c for c in aa_cols if c in plot_data.columns]
    heatmap_data = plot_data[available_cols].fillna(0)

    # Z-score normalize by column for better visualization
    heatmap_norm = (heatmap_data - heatmap_data.mean()) / heatmap_data.std()

    fig, ax = plt.subplots(figsize=(14, max(6, len(heatmap_data) * 0.5)))

    sns.heatmap(heatmap_norm, annot=heatmap_data.round(3), fmt='.3f',
                cmap='RdYlBu_r', center=0, ax=ax,
                cbar_kws={'label': 'Z-score (normalized concentration)',
                          'shrink': 0.6},
                annot_kws={'fontsize': 7},
                linewidths=0.5, linecolor='white')

    ax.set_title('Compound Profile Heatmap\n(Z-score normalized, original values in cells)',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Compound', fontsize=12)
    ax.set_ylabel('Sample', fontsize=12)
    ax.tick_params(axis='both', labelsize=8)

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"     Saved: {output_path}")


def plot_pca(pivot, output_path, aa_cols):
    """PCA plot for sample grouping visualization."""
    print(f"\n  📈 Plotting PCA...")

    plot_data = pivot.copy()
    available_cols = [c for c in aa_cols if c in plot_data.columns]
    X = plot_data[available_cols].fillna(0).values

    if X.shape[0] < 3 or X.shape[1] < 2:
        print(f"     [SKIP] Not enough data for PCA (n={X.shape[0]}, features={X.shape[1]})")
        return

    # Standardize
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # PCA
    n_components = min(3, X.shape[0], X.shape[1])
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X_scaled)

    # Explained variance
    evr = pca.explained_variance_ratio_

    fig, axes = plt.subplots(1, 2, figsize=(18, 8))

    # Score plot (PC1 vs PC2)
    ax = axes[0]
    unique_groups = plot_data['group'].unique()
    for group in unique_groups:
        mask = plot_data['group'] == group
        color = GROUP_COLORS.get(group, '#95a5a6')
        ax.scatter(X_pca[mask, 0], X_pca[mask, 1], s=120, c=color,
                   label=group, edgecolors='black', linewidth=0.5, alpha=0.85, zorder=5)

        # Label points
        mask_indices = np.where(mask)[0]
        for j, idx in enumerate(mask_indices):
            row = plot_data.iloc[idx]
            label = row['sample'].replace('.D', '').replace('唐婷婷-', '')
            ax.annotate(label, (X_pca[idx, 0], X_pca[idx, 1]),
                       fontsize=7, alpha=0.8, xytext=(5, 5), textcoords='offset points')

    ax.set_xlabel(f'PC1 ({evr[0]*100:.1f}%)', fontsize=12)
    ax.set_ylabel(f'PC2 ({evr[1]*100:.1f}%)', fontsize=12)
    ax.set_title('PCA Score Plot (PC1 vs PC2)', fontsize=14, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3, linestyle='--')
    ax.axhline(y=0, color='gray', alpha=0.3)
    ax.axvline(x=0, color='gray', alpha=0.3)

    # Loadings plot
    ax = axes[1]
    loadings = pca.components_.T
    for i, comp in enumerate(available_cols):
        ax.arrow(0, 0, loadings[i, 0] * 3, loadings[i, 1] * 3,
                head_width=0.08, head_length=0.12, fc='#e74c3c', ec='#c0392b', alpha=0.7)
        ax.text(loadings[i, 0] * 3.3, loadings[i, 1] * 3.3, comp,
                fontsize=9, ha='center', va='center', fontweight='bold')

    ax.set_xlabel(f'PC1 ({evr[0]*100:.1f}%)', fontsize=12)
    ax.set_ylabel(f'PC2 ({evr[1]*100:.1f}%)', fontsize=12)
    ax.set_title('PCA Loading Plot', fontsize=14, fontweight='bold')
    ax.grid(alpha=0.3, linestyle='--')
    ax.axhline(y=0, color='gray', alpha=0.3)
    ax.axvline(x=0, color='gray', alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"     Saved: {output_path}")


def plot_composition_ratio(pivot, output_path, aa_cols):
    """Stacked bar chart of compound composition ratios."""
    print(f"\n  🥧 Plotting composition ratios...")

    plot_data = pivot.copy()
    available_cols = [c for c in aa_cols if c in plot_data.columns]

    # Calculate percentages
    totals = plot_data[available_cols].sum(axis=1)
    ratio_data = plot_data[available_cols].div(totals, axis=0) * 100

    plot_data['label'] = plot_data['sample'].str.replace(r'\.D$', '', regex=True)
    plot_data['label'] = plot_data['label'].str.replace(r'唐婷婷-', '', regex=True)
    ratio_data.index = plot_data['label']

    fig, ax = plt.subplots(figsize=(14, 8))

    colors = plt.cm.tab20(np.linspace(0, 1, len(available_cols)))
    ratio_data.plot(kind='bar', stacked=True, ax=ax, color=colors)

    ax.set_ylabel('Composition Ratio [%]', fontsize=13)
    ax.set_title('Compound Composition Ratio by Sample', fontsize=16, fontweight='bold')
    ax.legend(loc='upper right', fontsize=8, ncol=2, framealpha=0.9)
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9)
    ax.set_ylim(0, 105)

    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"     Saved: {output_path}")


def plot_boxplots(df, output_path, aa_cols):
    """Box plots of compound distribution by group."""
    print(f"\n  📦 Plotting box plots...")

    available_cols = [c for c in aa_cols if c in df['compound'].unique()]
    n_cols = 5
    n_rows = (len(available_cols) + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, n_rows * 4))
    axes = axes.flatten()

    for i, comp in enumerate(available_cols):
        ax = axes[i]
        comp_data = df[df['compound'] == comp].dropna(subset=['conc_g100g'])

        if comp_data.empty:
            ax.set_visible(False)
            continue

        # Box plot grouped by 'group'
        groups = comp_data['group'].unique()
        plot_groups = [g for g in groups if len(comp_data[comp_data['group'] == g]) > 0]

        bp_data = [comp_data[comp_data['group'] == g]['conc_g100g'].values for g in plot_groups]
        bp = ax.boxplot(bp_data, tick_labels=plot_groups, patch_artist=True,
                        widths=0.5, showfliers=True)

        # Color boxes
        for patch, group in zip(bp['boxes'], plot_groups):
            patch.set_facecolor(GROUP_COLORS.get(group, '#95a5a6'))
            patch.set_alpha(0.6)

        # Add individual points
        for j, g in enumerate(plot_groups):
            vals = comp_data[comp_data['group'] == g]['conc_g100g'].values
            jitter = np.random.normal(0, 0.08, len(vals))
            ax.scatter(np.ones(len(vals)) * (j + 1) + jitter, vals,
                      alpha=0.6, s=30, c='black', zorder=5)

        ax.set_title(f'{comp}', fontsize=10)
        ax.set_ylabel('g/100g', fontsize=8)
        ax.tick_params(axis='x', rotation=20, labelsize=8)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

    # Hide unused axes
    for i in range(len(available_cols), len(axes)):
        axes[i].set_visible(False)

    fig.suptitle('Compound Distribution by Group', fontsize=16, fontweight='bold', y=1.01)
    plt.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"     Saved: {output_path}")


def plot_dashboard(pivot, df, output_path, aa_cols):
    """Multi-panel summary dashboard."""
    print(f"\n  🖼️  Plotting dashboard...")

    fig = plt.figure(figsize=(22, 16))
    gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)

    available_cols = [c for c in aa_cols if c in pivot.columns]

    # 1. Total concentration per sample (bar)
    ax1 = fig.add_subplot(gs[0, 0])
    plot_data = pivot.copy()
    plot_data['label'] = plot_data['sample'].str.replace(r'\.D$', '', regex=True)
    plot_data['label'] = plot_data['label'].str.replace(r'唐婷婷-', '', regex=True)
    plot_data['total'] = plot_data[available_cols].sum(axis=1)
    plot_data = plot_data.sort_values('total', ascending=False)
    bars = ax1.barh(range(len(plot_data)), plot_data['total'])
    for i, (_, row) in enumerate(plot_data.iterrows()):
        bars[i].set_color(GROUP_COLORS.get(row['group'], '#95a5a6'))
    ax1.set_yticks(range(len(plot_data)))
    ax1.set_yticklabels(plot_data['label'], fontsize=7)
    ax1.set_xlabel('Total [g/100g]', fontsize=9)
    ax1.set_title('Total Compounds per Sample', fontsize=11, fontweight='bold')

    # 2. Group comparison bar chart (top compounds)
    ax2 = fig.add_subplot(gs[0, 1:])
    group_means = df.groupby(['group', 'compound'])['conc_g100g'].mean().reset_index()
    top_aa = df.groupby('compound')['conc_g100g'].mean().nlargest(8).index
    plot_means = group_means[group_means['compound'].isin(top_aa)]
    pivot_means = plot_means.pivot(index='group', columns='compound', values='conc_g100g').fillna(0)
    pivot_means.plot(kind='bar', ax=ax2, colormap='Set2', edgecolor='black', linewidth=0.5)
    ax2.set_title('Major Compounds by Group (Mean)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Concentration [g/100g]', fontsize=9)
    ax2.legend(fontsize=8, ncol=2)
    ax2.tick_params(axis='x', rotation=20, labelsize=9)
    ax2.grid(axis='y', alpha=0.3, linestyle='--')

    # 3. Heatmap (simplified)
    ax3 = fig.add_subplot(gs[1, :2])
    heatmap_data = pivot.copy()
    heatmap_data['label'] = heatmap_data['sample'].str.replace(r'\.D$', '', regex=True)
    heatmap_data = heatmap_data.set_index('label')[available_cols].fillna(0)
    hm_norm = (heatmap_data - heatmap_data.mean()) / heatmap_data.std()
    sns.heatmap(hm_norm, cmap='RdYlBu_r', center=0, ax=ax3,
                cbar_kws={'label': 'Z-score', 'shrink': 0.8},
                linewidths=0.3)
    ax3.set_title('Compound Profiles (Z-score)', fontsize=11, fontweight='bold')
    ax3.tick_params(labelsize=7)

    # 4. CV% by compound
    ax4 = fig.add_subplot(gs[1, 2])
    cv_data = df.groupby('compound')['conc_g100g'].agg(['mean', 'std']).fillna(0)
    cv_data['cv_pct'] = (cv_data['std'] / cv_data['mean'].replace(0, np.nan) * 100).fillna(0)
    cv_data = cv_data.sort_values('cv_pct', ascending=False)
    bars = ax4.barh(range(len(cv_data)), cv_data['cv_pct'])
    for bar, val in zip(bars, cv_data['cv_pct']):
        bar.set_color('#e74c3c' if val > 50 else ('#f39c12' if val > 25 else '#27ae60'))
    ax4.set_yticks(range(len(cv_data)))
    ax4.set_yticklabels(cv_data.index, fontsize=8)
    ax4.set_xlabel('CV%', fontsize=9)
    ax4.set_title('Variability by Compound', fontsize=11, fontweight='bold')
    ax4.axvline(x=25, color='gray', linestyle='--', alpha=0.5)
    ax4.axvline(x=50, color='gray', linestyle='--', alpha=0.5)

    # 5. Concentration distribution
    ax5 = fig.add_subplot(gs[2, 0])
    for group in df['group'].unique():
        gdata = df[df['group'] == group]['conc_g100g'].dropna()
        ax5.hist(gdata, bins=30, alpha=0.5, label=group,
                color=GROUP_COLORS.get(group, '#95a5a6'))
    ax5.set_xlabel('Concentration [g/100g]', fontsize=9)
    ax5.set_ylabel('Frequency', fontsize=9)
    ax5.set_title('Concentration Distribution', fontsize=11, fontweight='bold')
    ax5.legend(fontsize=7)
    ax5.grid(alpha=0.3, linestyle='--')

    # 6. Summary table
    ax6 = fig.add_subplot(gs[2, 1:])
    ax6.axis('off')
    # Create summary
    summary_lines = [
        f"📊 ANALYSIS SUMMARY",
        f"",
        f"  Total samples processed: {df['sample'].nunique()}",
        f"  Total peak records: {len(df)}",
        f"  Groups: {', '.join(df['group'].unique())}",
        f"  Compounds detected: {df['compound'].nunique()}",
        f"",
        f"  Concentration range: {df['conc_g100g'].min():.4f} – {df['conc_g100g'].max():.4f} g/100g",
        f"  Mean concentration: {df['conc_g100g'].mean():.4f} g/100g",
        f"",
    ]

    # Top compound per group
    for group in df['group'].unique():
        top = df[df['group'] == group].groupby('compound')['conc_g100g'].mean().nlargest(3)
        summary_lines.append(f"  [{group}] Top 3: {', '.join(f'{c}({v:.3f})' for c, v in top.items())}")

    ax6.text(0.05, 0.95, '\n'.join(summary_lines), transform=ax6.transAxes,
            fontsize=9, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

    fig.suptitle('GCMS Compound Analysis — Summary Dashboard',
                fontsize=16, fontweight='bold', y=1.01)
    fig.savefig(output_path)
    plt.close(fig)
    print(f"     Saved: {output_path}")


# ============================================================
# EXPORT MODULE
# ============================================================

def export_to_excel(df, analysis, output_path):
    """Export all data and analysis to Excel workbook."""
    print(f"\n  📋 Exporting Excel workbook...")

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Sheet 1: Full data
        df.to_excel(writer, sheet_name='Raw Data', index=False)

        # Sheet 2: Pivot table (samples x compounds)
        if analysis['pivot'] is not None:
            analysis['pivot'].to_excel(writer, sheet_name='Pivot Table', index=False)

        # Sheet 3: Per-group statistics
        if analysis['stats'] is not None:
            analysis['stats'].to_excel(writer, sheet_name='Statistics', index=False)

        # Sheet 4: Between-group comparison
        if analysis['comparison'] is not None and not analysis['comparison'].empty:
            analysis['comparison'].to_excel(writer, sheet_name='Group Comparison', index=False)

        # Sheet 5: Composition ratios
        if analysis['composition_ratio'] is not None:
            analysis['composition_ratio'].to_excel(writer, sheet_name='Composition Ratios', index=False)

    print(f"     Saved: {output_path}")


def export_summary_csv(df, output_path):
    """Export pivot data as CSV for easy re-import."""
    print(f"\n  💾 Exporting CSV...")
    pivot = df.pivot_table(
        values='conc_g100g',
        index=['group', 'sample'],
        columns='compound',
        aggfunc='mean'
    ).reset_index()
    pivot.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"     Saved: {output_path}")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='ChemStation .D Data Auto-Analyzer (GC/MS, HPLC, GC-FID)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python gcms_analyzer.py
  python gcms_analyzer.py --data-dir "D:\\GCMS_Data"
  python gcms_analyzer.py --no-plots
  python gcms_analyzer.py --group-colors
        """
    )
    parser.add_argument('--data-dir', type=str, default=DEFAULT_DATA_DIR,
                       help='Path to directory containing .D folders')
    parser.add_argument('--output-dir', type=str, default=str(OUTPUT_DIR),
                       help='Output directory for results')
    parser.add_argument('--no-plots', action='store_true',
                       help='Skip plot generation (faster)')
    parser.add_argument('--no-excel', action='store_true',
                       help='Skip Excel export')
    args = parser.parse_args()

    if not args.data_dir:
        print("\n[ERROR] No data directory specified!")
        print("  Usage: python gcms_analyzer.py --data-dir \"path/to/.D/folders\"")
        sys.exit(1)

    # Setup output directories
    output_dir = Path(args.output_dir)
    plots_dir = output_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*60)
    print("  🧬 ChemStation .D Data Auto-Analyzer")
    print("="*60)
    print(f"  Data directory: {args.data_dir}")
    print(f"  Output directory: {output_dir}")

    # Step 1: Scan .D folders
    d_folders = scan_d_folders(args.data_dir)
    if not d_folders:
        print("\n[ERROR] No .D folders found!")
        sys.exit(1)

    # Step 2: Extract data
    df, skipped = extract_all_data(d_folders)
    if df.empty:
        print("\n[ERROR] No data could be extracted from reports!")
        print("  Make sure .D folders contain REPORT01.CSV files.")
        sys.exit(1)

    # Step 3: Analysis
    analysis = analyze_data(df)

    # Determine all detected compound columns
    compound_cols = sorted(df['compound'].unique().tolist())
    print(f"\n  ℹ️  Detected compounds: {', '.join(compound_cols[:30])}")
    if len(compound_cols) > 30:
        print(f"       ... and {len(compound_cols) - 30} more")

    # Step 4: Generate plots
    if not args.no_plots:
        print(f"\n{'='*60}")
        print(f"  GENERATING PLOTS")
        print(f"{'='*60}")

        pivot = analysis['pivot']

        plot_grouped_bar(pivot, str(plots_dir / "bar_chart_comparison.png"), compound_cols)
        plot_heatmap(pivot, str(plots_dir / "heatmap_profiles.png"), compound_cols)
        plot_pca(pivot, str(plots_dir / "pca_analysis.png"), compound_cols)
        plot_composition_ratio(pivot, str(plots_dir / "composition_ratio.png"), compound_cols)
        plot_boxplots(df, str(plots_dir / "boxplot_distribution.png"), compound_cols)
        plot_dashboard(pivot, df, str(plots_dir / "dashboard.png"), compound_cols)

    # Step 5: Export
    print(f"\n{'='*60}")
    print(f"  EXPORTING RESULTS")
    print(f"{'='*60}")

    if not args.no_excel:
        export_to_excel(df, analysis, str(output_dir / "amino_acid_summary.xlsx"))

    export_summary_csv(df, str(output_dir / "amino_acid_data.csv"))

    # Summary
    print(f"\n{'='*60}")
    print(f"  ✅ ANALYSIS COMPLETE!")
    print(f"{'='*60}")
    print(f"  Samples processed: {df['sample'].nunique()}")
    print(f"  Samples skipped (no reports): {len(skipped)}")
    print(f"  Plots saved to: {plots_dir}")
    print(f"  Excel workbook: {output_dir / 'amino_acid_summary.xlsx'}")
    print(f"  CSV data: {output_dir / 'amino_acid_data.csv'}")

    if skipped:
        print(f"\n  ⚠️  Skipped samples (no ChemStation reports):")
        for s in skipped:
            print(f"     - {s['name']} [{s['group']}]")

    print()


if __name__ == '__main__':
    main()
