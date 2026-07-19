#!/usr/bin/env python3
"""
Interactive GC-MS Visualization Engine
=======================================
Plotly-based interactive charts for GC-MS data analysis.

Components:
  1. TIC Chromatogram — zoomable, with peak annotations
  2. Spectrum Mirror Plot — observed vs library reference
  3. Peak Annotations — RT, area, compound name overlay
  4. EIC Overlay — extracted ion chromatograms
  5. Dashboard — multi-panel overview

All charts return Plotly Figure objects — embeddable in Streamlit, Jupyter,
or exported as standalone HTML.

Usage:
  from tools.interactive_viz import TICPlot, MirrorPlot, GCDashboard
"""

import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pathlib import Path


# ================================================================
# Color Palette
# ================================================================
COLORS = {
    'primary': '#1a5276',
    'secondary': '#e67e22',
    'accent': '#27ae60',
    'danger': '#c0392b',
    'light': '#bdc3c7',
    'dark': '#2c3e50',
    'observed': '#2980b9',    # Blue — observed spectrum (downward)
    'reference': '#c0392b',   # Red — reference spectrum (upward)
    'peak_fill': 'rgba(26, 82, 118, 0.15)',
    'shoulder': 'rgba(230, 126, 34, 0.3)',
    'grid': 'rgba(0,0,0,0.08)',
    'annotation_bg': 'rgba(255,255,255,0.9)',
}


# ================================================================
# 1. Interactive TIC Chromatogram
# ================================================================
class TICPlot:
    """Zoomable TIC chromatogram with peak annotations."""

    @staticmethod
    def create(times, intensities, peaks=None, title='TIC Chromatogram',
               xlabel='Retention Time (min)', ylabel='Intensity (counts)'):
        """Create interactive TIC plot.

        Args:
            times: retention time array
            intensities: TIC intensity array
            peaks: list of peak dicts {rt, height, area, compound_name?}
            title: chart title

        Returns:
            plotly Figure
        """
        fig = go.Figure()

        # Main TIC trace
        fig.add_trace(go.Scatter(
            x=times,
            y=intensities,
            mode='lines',
            name='TIC',
            line=dict(color=COLORS['primary'], width=1.2),
            fill='tozeroy',
            fillcolor=COLORS['peak_fill'],
            hovertemplate='RT: %{x:.3f} min<br>Intensity: %{y:.0f}<extra></extra>',
        ))

        # Peak markers
        if peaks:
            peak_rts = []
            peak_heights = []
            peak_labels = []
            peak_colors = []

            for p in peaks:
                if p.get('height', 0) > 0:
                    peak_rts.append(p['rt'])
                    peak_heights.append(p['height'])
                    # Label: compound name or RT
                    label = p.get('compound', f"RT {p['rt']:.2f}")
                    peak_labels.append(label)
                    # Color by type
                    if p.get('coeluting'):
                        peak_colors.append(COLORS['danger'])
                    elif p.get('snr', 0) > 50:
                        peak_colors.append(COLORS['accent'])
                    elif p.get('snr', 0) > 10:
                        peak_colors.append(COLORS['secondary'])
                    else:
                        peak_colors.append(COLORS['light'])

            if peak_rts:
                fig.add_trace(go.Scatter(
                    x=peak_rts,
                    y=peak_heights,
                    mode='markers+text',
                    name='Peaks',
                    marker=dict(
                        size=10,
                        color=peak_colors,
                        symbol='triangle-down',
                        line=dict(width=1, color='white'),
                    ),
                    text=peak_labels,
                    textposition='top center',
                    textfont=dict(size=9, color=COLORS['dark']),
                    hovertemplate='%{text}<br>RT: %{x:.3f} min<br>Height: %{y:.0f}<extra></extra>',
                ))

        # Shoulder peak markers
        if peaks:
            shoulder_rts = []
            shoulder_heights = []
            shoulder_labels = []
            for p in peaks:
                if p.get('type') == 'shoulder':
                    shoulder_rts.append(p['rt'])
                    shoulder_heights.append(p.get('intensity', 0))
                    shoulder_labels.append(f"Shoulder {p['rt']:.2f}")

            if shoulder_rts:
                fig.add_trace(go.Scatter(
                    x=shoulder_rts,
                    y=shoulder_heights,
                    mode='markers',
                    name='Shoulders',
                    marker=dict(
                        size=8,
                        color=COLORS['secondary'],
                        symbol='diamond-open',
                        line=dict(width=1.5),
                    ),
                    hovertemplate='Shoulder<br>RT: %{x:.3f} min<extra></extra>',
                ))

        # Layout
        fig.update_layout(
            title=dict(text=title, font=dict(size=16, color=COLORS['dark'])),
            xaxis=dict(
                title=xlabel,
                showgrid=True,
                gridcolor=COLORS['grid'],
                zeroline=False,
            ),
            yaxis=dict(
                title=ylabel,
                showgrid=True,
                gridcolor=COLORS['grid'],
                zeroline=False,
            ),
            hovermode='x unified',
            template='plotly_white',
            height=400,
            margin=dict(l=60, r=30, t=50, b=50),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1,
            ),
        )

        # Add range slider
        fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.05))

        return fig


# ================================================================
# 2. Spectrum Mirror Plot
# ================================================================
class MirrorPlot:
    """NIST-style mirror plot: reference (up) vs observed (down)."""

    @staticmethod
    def create(observed_ions, reference_ions=None, compound_name='Unknown',
               sample_name='', match_factor=None, ri_diff=None):
        """Create interactive mirror plot.

        Args:
            observed_ions: list of (mz, intensity) tuples — plotted downward
            reference_ions: list of (mz, intensity) tuples — plotted upward
            compound_name: label for the compound
            sample_name: sample identifier
            match_factor: cosine match score (0-999)
            ri_diff: retention index difference

        Returns:
            plotly Figure
        """
        fig = go.Figure()

        # Reference spectrum (upward)
        if reference_ions:
            ref_mz = [mz for mz, _ in reference_ions]
            ref_int = [intensity for _, intensity in reference_ions]
            # Normalize to 0-1000
            if ref_int:
                max_ref = max(ref_int)
                ref_int = [i / max_ref * 1000 for i in ref_int]

            fig.add_trace(go.Bar(
                x=ref_mz,
                y=ref_int,
                name=f'Reference: {compound_name}',
                marker_color=COLORS['reference'],
                hovertemplate='m/z: %{x}<br>Int: %{y:.0f}<extra></extra>',
                width=2,
            ))

        # Observed spectrum (downward — negative values)
        if observed_ions:
            obs_mz = [mz for mz, _ in observed_ions]
            obs_int = [intensity for _, intensity in observed_ions]
            if obs_int:
                max_obs = max(obs_int)
                obs_int = [-i / max_obs * 1000 for i in obs_int]  # Negative for downward

            fig.add_trace(go.Bar(
                x=obs_mz,
                y=obs_int,
                name=f'Observed: {sample_name}',
                marker_color=COLORS['observed'],
                hovertemplate='m/z: %{x}<br>Int: %{y:.0f}<extra></extra>',
                width=2,
            ))

        # Build title with match info
        title_parts = [f'Spectrum Comparison: {compound_name}']
        subtitle_parts = []
        if match_factor is not None:
            subtitle_parts.append(f'Match: {match_factor}')
        if ri_diff is not None:
            subtitle_parts.append(f'ΔRI: {ri_diff}')
        subtitle = ' | '.join(subtitle_parts) if subtitle_parts else ''

        # Layout
        fig.update_layout(
            title=dict(
                text=f'{" ".join(title_parts)}<br><sup>{subtitle}</sup>',
                font=dict(size=16, color=COLORS['dark']),
            ),
            xaxis=dict(
                title='m/z',
                showgrid=True,
                gridcolor=COLORS['grid'],
                zeroline=True,
                zerolinecolor=COLORS['dark'],
            ),
            yaxis=dict(
                title='Relative Intensity',
                showgrid=True,
                gridcolor=COLORS['grid'],
                zeroline=True,
                zerolinecolor=COLORS['dark'],
                tickvals=[-1000, -500, 0, 500, 1000],
                ticktext=['1000', '500', '0', '500', '1000'],
            ),
            template='plotly_white',
            height=450,
            margin=dict(l=60, r=30, t=70, b=50),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.05,
                xanchor='center',
                x=0.5,
            ),
            bargap=0,
            bargroupgap=0.05,
        )

        # Add match annotation
        if match_factor is not None:
            color = (COLORS['accent'] if match_factor >= 800
                     else COLORS['secondary'] if match_factor >= 600
                     else COLORS['danger'])
            fig.add_annotation(
                x=0.98, y=0.95,
                xref='paper', yref='paper',
                text=f'<b>Match: {match_factor}</b>',
                showarrow=False,
                font=dict(size=14, color=color),
                bgcolor=COLORS['annotation_bg'],
                bordercolor=color,
                borderwidth=1,
                borderpad=4,
            )

        return fig


# ================================================================
# 3. EIC Overlay Plot
# ================================================================
class EICPlot:
    """Overlay of extracted ion chromatograms for selected m/z values."""

    @staticmethod
    def create(times, eic_dict, title='Extracted Ion Chromatograms'):
        """Create EIC overlay plot.

        Args:
            times: retention time array
            eic_dict: {mz_label: intensity_array, ...}
            title: plot title

        Returns:
            plotly Figure
        """
        fig = go.Figure()

        # Color palette for multiple EICs
        colors = px.colors.qualitative.Plotly
        if len(eic_dict) > len(colors):
            colors = colors * (len(eic_dict) // len(colors) + 1)

        for i, (label, intensities) in enumerate(eic_dict.items()):
            # Normalize each EIC
            y = np.asarray(intensities, dtype=float)
            if y.max() > 0:
                y = y / y.max() * 100

            fig.add_trace(go.Scatter(
                x=times,
                y=y,
                mode='lines',
                name=f'm/z {label}',
                line=dict(color=colors[i % len(colors)], width=1.5),
                hovertemplate=f'm/z {label}<br>RT: %{{x:.3f}} min<br>Rel: %{{y:.1f}}%<extra></extra>',
            ))

        fig.update_layout(
            title=dict(text=title, font=dict(size=16, color=COLORS['dark'])),
            xaxis=dict(
                title='Retention Time (min)',
                showgrid=True,
                gridcolor=COLORS['grid'],
            ),
            yaxis=dict(
                title='Relative Intensity (%)',
                showgrid=True,
                gridcolor=COLORS['grid'],
                range=[0, 105],
            ),
            template='plotly_white',
            height=350,
            hovermode='x unified',
            margin=dict(l=60, r=30, t=50, b=50),
        )

        return fig


# ================================================================
# 4. GC-MS Dashboard
# ================================================================
class GCDashboard:
    """Multi-panel GC-MS analysis dashboard."""

    @staticmethod
    def create(times, tic, peaks=None, top_ions=None, compound_name=None):
        """Create comprehensive multi-panel dashboard.

        Panels:
          1. TIC chromatogram with peaks
          2. Spectrum plot (if top_ions provided)
          3. Peak table summary

        Returns:
            plotly Figure (subplots)
        """
        n_rows = 2 if top_ions else 1
        row_heights = [0.5, 0.5] if top_ions else [1.0]

        specs = [[{'type': 'xy'}], [{'type': 'xy'}]] if top_ions else [[{'type': 'xy'}]]
        subplot_titles = ['TIC Chromatogram', 'Mass Spectrum'] if top_ions else ['TIC Chromatogram']

        fig = make_subplots(
            rows=n_rows, cols=1,
            row_heights=row_heights,
            subplot_titles=subplot_titles,
            vertical_spacing=0.12,
        )

        # Panel 1: TIC
        fig.add_trace(
            go.Scatter(
                x=times, y=tic,
                mode='lines',
                name='TIC',
                line=dict(color=COLORS['primary'], width=1.2),
                fill='tozeroy',
                fillcolor=COLORS['peak_fill'],
            ),
            row=1, col=1,
        )

        # Peak markers on TIC
        if peaks:
            major_peaks = [p for p in peaks if p.get('snr', 0) >= 10]
            if major_peaks:
                rts = [p['rt'] for p in major_peaks]
                heights = [p['height'] for p in major_peaks]
                labels = [p.get('compound', f"RT {p['rt']:.2f}") for p in major_peaks]

                fig.add_trace(
                    go.Scatter(
                        x=rts, y=heights,
                        mode='markers+text',
                        name='Peaks',
                        marker=dict(size=8, color=COLORS['secondary'],
                                   symbol='triangle-down'),
                        text=labels,
                        textposition='top center',
                        textfont=dict(size=8),
                    ),
                    row=1, col=1,
                )

        # Panel 2: Mass Spectrum
        if top_ions:
            mzs = [ion[0] for ion in top_ions]
            intensities = [ion[1] for ion in top_ions]

            fig.add_trace(
                go.Bar(
                    x=mzs, y=intensities,
                    name='Spectrum',
                    marker_color=COLORS['observed'],
                    width=2,
                ),
                row=2, col=1,
            )

            fig.update_xaxes(title_text='m/z', row=2, col=1)
            fig.update_yaxes(title_text='Intensity', row=2, col=1)

        # Update all axes
        fig.update_xaxes(
            title_text='Retention Time (min)',
            showgrid=True,
            gridcolor=COLORS['grid'],
            row=1, col=1,
        )
        fig.update_yaxes(
            title_text='Intensity',
            showgrid=True,
            gridcolor=COLORS['grid'],
            row=1, col=1,
        )

        # Overall layout
        title_text = 'GC-MS Analysis Dashboard'
        if compound_name:
            title_text += f' — {compound_name}'

        fig.update_layout(
            title=dict(text=title_text, font=dict(size=18, color=COLORS['dark'])),
            template='plotly_white',
            height=350 * n_rows,
            showlegend=False,
            margin=dict(l=60, r=30, t=60, b=50),
        )

        return fig


# ================================================================
# 5. Export Helpers
# ================================================================
def save_figure(fig, filepath, width=None, height=None):
    """Save Plotly figure as interactive HTML.

    Args:
        fig: plotly Figure
        filepath: output path (.html)
        width, height: optional override dimensions
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(
        str(path),
        include_plotlyjs='cdn',
        full_html=True,
        config={
            'displayModeBar': True,
            'scrollZoom': True,
            'responsive': True,
        },
    )
    return path


def figure_to_json(fig):
    """Convert Plotly figure to JSON-serializable dict."""
    return fig.to_dict()


def json_to_figure(data):
    """Restore Plotly figure from JSON dict."""
    return go.Figure(data)


# ================================================================
# CLI Demo
# ================================================================
# ================================================================
# 6. Enhanced Heatmap with Dendrogram + Significance
# ================================================================
class EnhancedHeatmap:
    """Publication-quality heatmap with hierarchical clustering and significance annotations."""

    @staticmethod
    def create(dataframe, group_col='group', top_n=30, title='Compound Abundance Heatmap'):
        """Create enhanced heatmap with dendrograms.

        Args:
            dataframe: pandas DataFrame with columns: compound, sample, area, group
            group_col: column with group labels
            top_n: number of top-variable compounds to show
            title: plot title

        Returns:
            plotly Figure
        """
        from scipy.cluster.hierarchy import linkage, dendrogram
        from scipy.spatial.distance import pdist
        from scipy.stats import ttest_ind

        df = dataframe

        # Pivot: compounds x samples
        pivot = df.pivot_table(values='area', index='compound', columns='sample', aggfunc='mean').fillna(0)

        # Top N by variance
        variances = pivot.var(axis=1).sort_values(ascending=False)
        top_compounds = variances.head(top_n).index
        data = pivot.loc[top_compounds]

        # Log2 transform + z-score normalize
        data_log = np.log2(data.values + 1)
        data_z = (data_log - data_log.mean(axis=1, keepdims=True)) / (data_log.std(axis=1, keepdims=True) + 1e-10)

        # Hierarchical clustering on compounds (rows)
        row_dist = pdist(data_z)
        row_linkage = linkage(row_dist, method='ward')
        row_dendro = dendrogram(row_linkage, no_plot=True)
        row_order = row_dendro['leaves']

        # Clustering on samples (columns)
        col_dist = pdist(data_z.T)
        col_linkage = linkage(col_dist, method='ward')
        col_dendro = dendrogram(col_linkage, no_plot=True)
        col_order = col_dendro['leaves']

        # Reorder data
        data_ordered = data_z[row_order, :][:, col_order]
        compounds_ordered = [top_compounds[i] for i in row_order]
        samples_ordered = [data.columns[i] for i in col_order]

        # Significance test between groups
        sig_markers = []
        if group_col and group_col in df.columns:
            groups = df.groupby('sample')[group_col].first()
            unique_groups = list(groups.unique())
            if len(unique_groups) == 2:
                g1, g2 = unique_groups
                g1_samples = groups[groups == g1].index
                g2_samples = groups[groups == g2].index
                for i, comp in enumerate(compounds_ordered):
                    v1 = data.loc[comp, g1_samples].values
                    v2 = data.loc[comp, g2_samples].values
                    if len(v1) >= 2 and len(v2) >= 2:
                        _, p = ttest_ind(v1, v2)
                        if p < 0.05:
                            sig_markers.append({'row': i, 'p': p})

        # Build heatmap
        fig = go.Figure()

        # Main heatmap
        fig.add_trace(go.Heatmap(
            z=data_ordered,
            x=[str(s) for s in samples_ordered],
            y=[str(c)[:50] for c in compounds_ordered],
            colorscale='RdBu_r',
            zmid=0,
            hovertemplate='Compound: %{y}<br>Sample: %{x}<br>Z-score: %{z:.2f}<extra></extra>',
            colorbar=dict(title='Z-score', thickness=15),
        ))

        # Significance markers (*)
        for m in sig_markers:
            fig.add_annotation(
                x=len(samples_ordered) + 0.5,
                y=m['row'],
                text='*' if m['p'] < 0.05 else '**',
                showarrow=False,
                font=dict(size=12, color='#c0392b' if m['p'] < 0.01 else '#e67e22'),
            )

        fig.update_layout(
            title=dict(text=title, font=dict(size=16)),
            xaxis=dict(title='Sample', tickangle=45),
            yaxis=dict(title='Compound', tickfont=dict(size=9)),
            template='plotly_white',
            height=max(500, top_n * 15 + 100),
            margin=dict(l=20, r=60, t=50, b=100),
        )

        return fig


# ================================================================
# 7. SCI-Quality Figure Export
# ================================================================
def export_sci_figure(fig_or_func, filepath, figsize=(8, 6), dpi=300, fmt='png'):
    """Export publication-quality figure for journal submission.

    Args:
        fig_or_func: matplotlib Figure or callable that creates one
        filepath: output path (.png, .tiff, .pdf, .svg)
        figsize: (width_inches, height_inches)
        dpi: resolution (300 for most journals, 600 for line art)
        fmt: 'png', 'tiff', 'pdf', 'svg'

    Returns:
        Path to saved file
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    # Journal-quality rcParams
    sci_rc = {
        'font.family': 'serif',
        'font.serif': ['Times New Roman', 'DejaVu Serif'],
        'mathtext.fontset': 'stix',
        'font.size': 8,
        'axes.titlesize': 9,
        'axes.labelsize': 8,
        'xtick.labelsize': 7,
        'ytick.labelsize': 7,
        'legend.fontsize': 7,
        'figure.dpi': dpi,
        'savefig.dpi': dpi,
        'savefig.bbox': 'tight',
        'savefig.pad_inches': 0.05,
        'figure.facecolor': 'white',
        'axes.facecolor': 'white',
        'axes.edgecolor': '.15',
        'axes.linewidth': 0.8,
        'axes.grid': False,
        'lines.linewidth': 1.2,
        'lines.markersize': 4,
    }
    orig_rc = {k: plt.rcParams.get(k) for k in sci_rc}
    plt.rcParams.update(sci_rc)

    try:
        if callable(fig_or_func):
            fig = fig_or_func(figsize)
        else:
            fig = fig_or_func

        fig.set_size_inches(figsize)
        fig.savefig(filepath, dpi=dpi, format=fmt)

        # Also save as PDF (vector) for journals that prefer it
        if fmt != 'pdf':
            pdf_path = str(Path(filepath).with_suffix('.pdf'))
            fig.savefig(pdf_path, dpi=dpi, format='pdf')

        return Path(filepath)
    finally:
        plt.rcParams.update(orig_rc)


if __name__ == '__main__':
    import tempfile

    print("Generating demo visualizations...")

    # Demo data
    t = np.linspace(0, 10, 1000)
    tic = (
        100000 * np.exp(-((t - 2.5) / 0.15) ** 2) +
        60000 * np.exp(-((t - 3.0) / 0.12) ** 2) +
        80000 * np.exp(-((t - 6.0) / 0.3) ** 2) +
        np.random.normal(0, 500, len(t))
    )

    peaks = [
        {'rt': 2.5, 'height': 100000, 'snr': 200, 'compound': 'Hexanal'},
        {'rt': 3.0, 'height': 60000, 'snr': 120, 'compound': 'Nonanal', 'coeluting': True},
        {'rt': 6.0, 'height': 80000, 'snr': 160, 'compound': 'Limonene'},
    ]

    # TIC plot
    tic_fig = TICPlot.create(t, tic, peaks, title='Demo GC-MS TIC')
    tic_path = Path(tempfile.gettempdir()) / 'gcms_tic_demo.html'
    save_figure(tic_fig, tic_path)
    print(f"  TIC plot: {tic_path}")

    # Mirror plot
    observed = [(43, 999), (57, 850), (71, 600), (85, 400), (99, 100), (113, 50)]
    reference = [(43, 999), (57, 880), (71, 620), (85, 410), (99, 110)]
    mirror_fig = MirrorPlot.create(
        observed, reference,
        compound_name='Hexanal',
        sample_name='Sample-001',
        match_factor=872,
    )
    mirror_path = Path(tempfile.gettempdir()) / 'gcms_mirror_demo.html'
    save_figure(mirror_fig, mirror_path)
    print(f"  Mirror plot: {mirror_path}")

    # Dashboard
    dash_fig = GCDashboard.create(t, tic, peaks, observed, 'Hexanal')
    dash_path = Path(tempfile.gettempdir()) / 'gcms_dashboard_demo.html'
    save_figure(dash_fig, dash_path)
    print(f"  Dashboard: {dash_path}")

    print("\nAll visualizations generated successfully!")
