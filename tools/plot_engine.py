#!/usr/bin/env python3
"""
Plot Engine Selector - Multiple plotting backends
==================================================
Users choose their preferred plotting style:

  - plotly      Interactive web charts (default)
  - matplotlib  Static publication-quality (journal ready)
  - seaborn     Statistical style (built on matplotlib)
  - dark        Dark theme (for presentations)

Usage:
  from tools.plot_engine import PlotEngine
  engine = PlotEngine('plotly')  # or 'matplotlib', 'seaborn', 'dark'
  fig = engine.bar_chart(...)
"""

import numpy as np
from pathlib import Path

# ================================================================
# Style Presets
# ================================================================
STYLES = {
    'plotly': {
        'name': 'Plotly Interactive',
        'icon': '📊',
        'desc': 'Zoom, pan, hover - best for data exploration',
        'colors': ['#1a5276', '#e67e22', '#27ae60', '#c0392b', '#8e44ad'],
    },
    'matplotlib': {
        'name': 'Matplotlib Publication',
        'icon': '📈',
        'desc': '300dpi, Times New Roman - best for journal submission',
        'colors': ['#2c3e50', '#e74c3c', '#3498db', '#2ecc71', '#9b59b6'],
    },
    'seaborn': {
        'name': 'Seaborn Statistical',
        'icon': '📉',
        'desc': 'Clean statistical style - best for data analysis',
        'colors': ['#4c72b0', '#dd8452', '#55a868', '#c44e52', '#8172b3'],
    },
    'dark': {
        'name': 'Dark Theme',
        'icon': '🌙',
        'desc': 'Dark background - best for presentations & slides',
        'colors': ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6'],
    },
}


class PlotEngine:
    """Unified plotting interface with multiple backends."""

    def __init__(self, style='plotly'):
        self.style = style
        self.colors = STYLES.get(style, STYLES['plotly'])['colors']

    # ── Bar Chart ─────────────────────────────────────────
    def bar_chart(self, data, labels, title='', xlabel='', ylabel='', horizontal=False):
        """Create bar chart. Returns plotly Figure or matplotlib Figure."""
        if self.style == 'plotly':
            return self._bar_plotly(data, labels, title, xlabel, ylabel, horizontal)
        else:
            return self._bar_mpl(data, labels, title, xlabel, ylabel, horizontal)

    def _bar_plotly(self, data, labels, title, xlabel, ylabel, horizontal):
        import plotly.graph_objects as go
        if horizontal:
            fig = go.Figure(go.Bar(
                x=list(data), y=list(labels), orientation='h',
                marker_color=self.colors[:len(data)],
                text=[f'{v:.1f}' for v in data], textposition='outside',
            ))
        else:
            fig = go.Figure(go.Bar(
                x=list(labels), y=list(data),
                marker_color=self.colors[:len(data)],
                text=[f'{v:.1f}' for v in data], textposition='outside',
            ))
        fig.update_layout(
            title=title, xaxis_title=xlabel, yaxis_title=ylabel,
            template='plotly_white', height=400,
            margin=dict(l=20, r=20, t=50, b=50),
        )
        return fig

    def _bar_mpl(self, data, labels, title, xlabel, ylabel, horizontal):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 5))
        if horizontal:
            ax.barh(range(len(data)), data, color=self.colors[:len(data)], height=0.7)
            ax.set_yticks(range(len(data)))
            ax.set_yticklabels(labels)
        else:
            ax.bar(range(len(data)), data, color=self.colors[:len(data)], width=0.7)
            ax.set_xticks(range(len(data)))
            ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_title(title, fontweight='bold')
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        fig.tight_layout()
        return fig

    # ── Scatter / PCA ─────────────────────────────────────
    def scatter(self, x, y, groups=None, title='', xlabel='', ylabel=''):
        """Create scatter/PCA plot."""
        if self.style == 'plotly':
            return self._scatter_plotly(x, y, groups, title, xlabel, ylabel)
        else:
            return self._scatter_mpl(x, y, groups, title, xlabel, ylabel)

    def _scatter_plotly(self, x, y, groups, title, xlabel, ylabel):
        import plotly.graph_objects as go
        fig = go.Figure()
        if groups is None:
            groups = ['All'] * len(x)
        unique_g = list(set(groups))
        for i, g in enumerate(unique_g):
            mask = [gg == g for gg in groups]
            fig.add_trace(go.Scatter(
                x=np.array(x)[mask], y=np.array(y)[mask],
                mode='markers', name=str(g),
                marker=dict(size=10, color=self.colors[i % len(self.colors)]),
            ))
        fig.update_layout(title=title, xaxis_title=xlabel, yaxis_title=ylabel,
                          template='plotly_white', height=400)
        return fig

    def _scatter_mpl(self, x, y, groups, title, xlabel, ylabel):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 5))
        if groups is None:
            groups = ['All'] * len(x)
        for i, g in enumerate(set(groups)):
            mask = [gg == g for gg in groups]
            ax.scatter(np.array(x)[mask], np.array(y)[mask],
                       c=self.colors[i % len(self.colors)], label=str(g),
                       s=60, edgecolors='white', linewidth=0.5)
        ax.set_title(title, fontweight='bold')
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.legend()
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        fig.tight_layout()
        return fig

    # ── Heatmap ───────────────────────────────────────────
    def heatmap(self, data, row_labels, col_labels, title=''):
        if self.style == 'plotly':
            return self._heatmap_plotly(data, row_labels, col_labels, title)
        else:
            return self._heatmap_mpl(data, row_labels, col_labels, title)

    def _heatmap_plotly(self, data, row_labels, col_labels, title):
        import plotly.graph_objects as go
        fig = go.Figure(go.Heatmap(
            z=data, x=[str(c) for c in col_labels], y=[str(r)[:40] for r in row_labels],
            colorscale='RdBu_r', zmid=0,
        ))
        fig.update_layout(title=title, template='plotly_white', height=max(400, len(row_labels)*15))
        return fig

    def _heatmap_mpl(self, data, row_labels, col_labels, title):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(len(col_labels)*0.8, len(row_labels)*0.35))
        im = ax.imshow(data, aspect='auto', cmap='RdBu_r')
        ax.set_xticks(range(len(col_labels)))
        ax.set_xticklabels(col_labels, rotation=45, ha='right', fontsize=8)
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels([str(r)[:50] for r in row_labels], fontsize=8)
        ax.set_title(title, fontweight='bold')
        plt.colorbar(im, ax=ax, shrink=0.8)
        fig.tight_layout()
        return fig

    # ── Save ───────────────────────────────────────────────
    def save(self, fig, filepath, dpi=300):
        """Save figure to file. Handles both plotly (HTML) and matplotlib (PNG/PDF)."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.style == 'plotly':
            fig.write_html(str(path.with_suffix('.html')))
        else:
            fig.savefig(str(path), dpi=dpi, bbox_inches='tight')
        return path


# ================================================================
# Style Switcher (for Streamlit sidebar)
# ================================================================
def plot_style_selector(key='plot_style'):
    """Render plot style selector in Streamlit sidebar."""
    try:
        import streamlit as st
        styles = list(STYLES.keys())
        labels = [f"{STYLES[s]['icon']} {STYLES[s]['name']}" for s in styles]
        current = st.session_state.get(key, 'plotly')
        idx = styles.index(current) if current in styles else 0
        selected_label = st.selectbox('Plot Style', labels, index=idx, key=key)
        selected = styles[labels.index(selected_label)]
        st.session_state[key] = selected
        st.caption(STYLES[selected]['desc'])
        return PlotEngine(selected)
    except ImportError:
        return PlotEngine('plotly')
