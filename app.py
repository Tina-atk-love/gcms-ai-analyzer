#!/usr/bin/env python3
"""
GC-MS AI Analyzer — Web Interface
==================================
Streamlit web app for Agilent GC-MS .D data analysis.
Upload data → auto-analyze → interactive plots → export reports.

Usage:
    streamlit run app.py
    Or: docker-compose up
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import io
import zipfile
import tempfile
import shutil
import base64
from pathlib import Path
from datetime import datetime
from tools.i18n import t, lang_selector, get_lang, set_lang
from tools.config_manager import load_config, save_config
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go

# ---- Page Config ----
st.set_page_config(
    page_title="GC-MS AI Analyzer",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- MASSFLOW Dark Premium Design System ----
st.markdown("""
<style>
/* ============================================================
   MASSFLOW · Enterprise GC-MS Workbench Theme
   Midnight Blue · Graphite · Ice Accent
   ============================================================ */
:root {
    --primary: #7dd3fc;
    --primary-600: #38bdf8;
    --primary-400: #7dd3fc;
    --primary-200: #bae6fd;
    --accent: #4adeb0;
    --accent-500: #2dd4bf;
    --accent-300: #5eead4;
    --success: #4adeb0;
    --warning: #fbbf24;
    --danger: #f87171;
    --bg-root: #0c1119;
    --bg-sidebar: #080d14;
    --bg-panel: #131a25;
    --bg-card: #18202e;
    --bg-input: #141c2b;
    --surface: #18202e;
    --bg: #0c1119;
    --bg-alt: #111827;
    --border-subtle: rgba(255,255,255,0.05);
    --border: rgba(255,255,255,0.07);
    --border-light: rgba(255,255,255,0.04);
    --border-focus: rgba(125,211,252,0.2);
    --text: #e8ecf1;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --radius-sm: 6px;
    --radius: 10px;
    --radius-lg: 14px;
    --shadow-xs: none;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.2);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.3);
    --shadow-lg: 0 8px 24px rgba(0,0,0,0.4);
    --transition: 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
/* ============================================================
   GLOBAL
   ============================================================ */
.stApp { background: var(--bg-root); }
.stMainBlock { max-width: 1400px; margin: 0 auto; }

[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; }
footer { display: none !important; }

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.06); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.12); }

/* Top accent line */
.stMainBlock::before {
    content: '';
    position: fixed; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, var(--primary) 20%, var(--accent) 80%, transparent);
    z-index: 99999; pointer-events: none; opacity: 0.6;
}

/* ============================================================
   SIDEBAR — deep space, premium
   ============================================================ */
[data-testid="stSidebar"] {
    background: var(--bg-sidebar) !important;
    border-right: 1px solid var(--border-subtle) !important;
    box-shadow: none !important;
}
[data-testid="stSidebar"] h2 {
    font-size: 1.05rem !important; font-weight: 600 !important;
    letter-spacing: 0.06em; color: var(--primary) !important;
    text-transform: uppercase;
}
[data-testid="stSidebar"] h3 {
    font-size: 0.78rem !important; font-weight: 600 !important;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--text-muted) !important;
    padding: 0.25rem 0; margin-top: 1.25rem;
    border-bottom: 1px solid var(--border-subtle);
}
[data-testid="stSidebar"] label {
    font-size: 0.8rem !important; font-weight: 500 !important;
    color: var(--text-secondary) !important; letter-spacing: 0.02em;
}
[data-testid="stSidebar"] .stButton > button {
    border-radius: var(--radius-sm) !important; font-weight: 500 !important;
    font-size: 0.82rem !important; letter-spacing: 0.04em;
    transition: var(--transition) !important;
    background: var(--bg-card) !important; color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(125,211,252,0.08) !important;
    color: var(--primary) !important; border-color: var(--border-focus) !important;
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stTextInput > div > div > input {
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-input) !important;
    font-size: 0.83rem !important; color: var(--text) !important;
}
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: var(--border-focus) !important;
    box-shadow: 0 0 0 2px rgba(125,211,252,0.08) !important;
}
[data-testid="stSidebar"] hr {
    border: none !important; height: 1px !important;
    background: var(--border-subtle) !important; margin: 1rem 0 !important;
}
[data-testid="stSidebar"] .stCaption { font-size: 0.74rem !important; color: var(--text-muted) !important; }
[data-testid="stSidebar"] .stExpander {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--bg-card) !important; box-shadow: none !important;
}
[data-testid="stSidebar"] .stExpander:hover { border-color: var(--border-focus) !important; }

/* ============================================================
   MAIN HEADER
   ============================================================ */
.main-header {
    font-size: 1.8rem; font-weight: 600; letter-spacing: 0.06em;
    color: var(--text); margin-bottom: 2px;
    animation: fadeIn 0.4s ease;
}
.sub-header {
    font-size: 0.88rem; color: var(--text-muted);
    margin-top: 2px; font-weight: 400; letter-spacing: 0.02em;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ============================================================
   CARDS — frosted glass, precision
   ============================================================ */
.card {
    background: var(--bg-card); border-radius: var(--radius);
    padding: 20px 18px; border: 1px solid var(--border);
    box-shadow: none; transition: var(--transition);
    height: 100%; position: relative;
}
.card:hover { border-color: var(--border-focus); }
.card h4 {
    color: var(--text); margin: 0.4rem 0 0.2rem 0;
    font-size: 0.92rem; font-weight: 600; letter-spacing: 0.03em;
}
.card p { font-size: 0.82rem; color: var(--text-secondary); line-height: 1.5; margin: 0; }
.feature-icon { font-size: 1.8rem; display: block; margin-bottom: 0.25rem; opacity: 0.8; transition: var(--transition); }
.card:hover .feature-icon { opacity: 1; }

/* ============================================================
   METRIC CARDS (Streamlit native st.metric)
   ============================================================ */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 16px 18px !important;
}
[data-testid="stMetric"] label {
    font-size: 0.68rem !important; font-weight: 500 !important;
    letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--text-muted) !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.8rem !important; font-weight: 700 !important;
    color: var(--primary) !important;
    font-family: "SF Mono","JetBrains Mono","Cascadia Code","Consolas",monospace !important;
}

/* ============================================================
   SEVERITY STATUS
   ============================================================ */
.oav-dominant { color: #f87171; font-weight: 600; }
.oav-significant { color: #fbbf24; font-weight: 600; }
.oav-contributing { color: #7dd3fc; font-weight: 600; }
.rova-overwhelming { color: #f87171; font-weight: 600; font-size: 1.02em; }
.rova-major { color: #fbbf24; font-weight: 600; }
.rova-significant { color: #7dd3fc; font-weight: 600; }

/* ============================================================
   BUTTONS
   ============================================================ */
.stButton > button {
    border-radius: var(--radius-sm) !important; font-weight: 500 !important;
    font-size: 0.86rem !important; letter-spacing: 0.03em;
    transition: var(--transition) !important;
}
.stButton > button:hover { filter: brightness(1.1); }
button[kind="primary"], .stButton > button[kind="primary"] {
    background: rgba(125,211,252,0.12) !important;
    color: var(--primary) !important;
    border: 1px solid rgba(125,211,252,0.25) !important;
    box-shadow: none !important;
}
button[kind="primary"]:hover {
    background: rgba(125,211,252,0.18) !important;
    border-color: rgba(125,211,252,0.4) !important;
}
button[kind="secondary"] {
    background: var(--bg-card) !important; color: var(--text-secondary) !important;
    border: 1px solid var(--border) !important;
}
button[kind="secondary"]:hover {
    border-color: var(--border-focus) !important; color: var(--text) !important;
}

/* ============================================================
   TABS — precision selector
   ============================================================ */
[data-testid="stTabs"] {
    background: var(--bg-panel); border-radius: var(--radius) var(--radius) 0 0;
    padding: 0.25rem 0.75rem 0 0.75rem;
    border-bottom: 1px solid var(--border-subtle); box-shadow: none;
}
[data-testid="stTabs"] button {
    font-weight: 500 !important; font-size: 0.82rem !important;
    letter-spacing: 0.04em; color: var(--text-muted) !important;
    border: none !important; padding: 0.55rem 1rem !important;
    transition: var(--transition) !important; background: transparent !important;
}
[data-testid="stTabs"] button:hover {
    color: var(--text) !important; background: rgba(255,255,255,0.03) !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: var(--primary) !important;
    border-bottom: 2px solid var(--primary) !important;
    background: transparent !important;
}

/* ============================================================
   DATAFRAME
   ============================================================ */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important; overflow: hidden;
}
[data-testid="stDataFrame"] th {
    background: var(--bg-alt) !important; font-weight: 600 !important;
    font-size: 0.74rem !important; letter-spacing: 0.04em; text-transform: uppercase;
    color: var(--text-muted) !important; padding: 8px 12px !important;
    border-bottom: 1px solid var(--border) !important;
}
[data-testid="stDataFrame"] td {
    font-size: 0.82rem !important; padding: 6px 12px !important;
    border-bottom: 1px solid var(--border-light) !important;
    color: var(--text) !important;
}
[data-testid="stDataFrame"] tbody tr:hover { background: rgba(125,211,252,0.04) !important; }
[data-testid="stDataFrame"] tbody tr:nth-child(even) { background: rgba(255,255,255,0.01); }

/* ============================================================
   EXPANDER · INPUTS · DIVIDERS
   ============================================================ */
.stExpander {
    border: 1px solid var(--border) !important; border-radius: var(--radius-sm) !important;
    background: var(--bg-card) !important; box-shadow: none; transition: var(--transition);
}
.stExpander:hover { border-color: var(--border-focus); }
.stSelectbox [data-baseweb="select"] > div {
    border-radius: var(--radius-sm) !important; border-color: var(--border) !important;
    background: var(--bg-input) !important;
}
.stSelectbox [data-baseweb="select"] > div:focus-within {
    border-color: var(--border-focus) !important;
    box-shadow: 0 0 0 2px rgba(125,211,252,0.06) !important;
}
.stCheckbox label { font-size: 0.83rem !important; }
.stNumberInput input {
    border-radius: var(--radius-sm) !important; border-color: var(--border) !important;
    background: var(--bg-input) !important; color: var(--text) !important;
}
hr {
    border: none !important; height: 1px !important;
    background: linear-gradient(90deg, transparent, var(--border), transparent) !important;
    margin: 1.25rem 0 !important;
}

/* ============================================================
   MESSAGE BARS
   ============================================================ */
[data-testid="stSuccess"] {
    border-left: 3px solid var(--accent) !important; border-radius: var(--radius-sm) !important;
    background: rgba(74,222,176,0.06) !important;
}
[data-testid="stError"] {
    border-left: 3px solid var(--danger) !important; border-radius: var(--radius-sm) !important;
    background: rgba(248,113,113,0.06) !important;
}
[data-testid="stWarning"] {
    border-left: 3px solid var(--warning) !important; border-radius: var(--radius-sm) !important;
    background: rgba(251,191,36,0.06) !important;
}
[data-testid="stInfo"] {
    border-left: 3px solid var(--primary) !important; border-radius: var(--radius-sm) !important;
    background: rgba(125,211,252,0.04) !important;
}

/* ============================================================
   PROGRESS · DOWNLOAD
   ============================================================ */
.stProgress > div > div { background: var(--primary) !important; }
.stDownloadButton > button {
    border-radius: var(--radius-sm) !important; font-weight: 500 !important;
    letter-spacing: 0.03em; transition: var(--transition) !important;
}
.stDownloadButton > button:hover { filter: brightness(1.1); }

/* ============================================================
   HERO SECTION
   ============================================================ */
.gcms-hero {
    text-align: center; padding: 2rem 1rem 1rem 1rem;
    animation: fadeIn 0.5s ease;
}
.gcms-hero h1 {
    font-size: 2.2rem; font-weight: 600; letter-spacing: 0.06em;
    color: var(--text); margin-bottom: 0.5rem;
}
.gcms-hero p { color: var(--text-secondary); font-size: 0.95rem; max-width: 560px; margin: 0 auto; line-height: 1.6; }
.gcms-hero .hero-badge {
    display: inline-block; background: rgba(125,211,252,0.06);
    border: 1px solid rgba(125,211,252,0.12); border-radius: 2px;
    padding: 0.3rem 1rem; font-size: 0.76rem; font-weight: 500;
    letter-spacing: 0.06em; text-transform: uppercase;
    color: var(--text-secondary); margin-bottom: 1.25rem;
}
.step-card {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 12px 16px; background: var(--bg-card);
    border: 1px solid var(--border); border-radius: var(--radius-sm);
    margin-bottom: 8px; box-shadow: none; transition: var(--transition);
}
.step-card:hover { border-color: var(--border-focus); }
.step-num {
    width: 28px; height: 28px; min-width: 28px;
    border: 1.5px solid var(--primary); border-radius: 2px;
    background: transparent; color: var(--primary);
    display: flex; align-items: center; justify-content: center;
    font-weight: 600; font-size: 0.82rem;
    font-family: "SF Mono","JetBrains Mono","Cascadia Code","Consolas",monospace;
}
.hero-cta {
    background: var(--bg-card); border: 1px solid var(--border);
    border-left: 3px solid var(--accent); border-radius: var(--radius-sm);
    padding: 1.5rem; text-align: center; box-shadow: none;
}
.stat-bar {
    display: flex; justify-content: center; gap: 2.5rem;
    text-align: center; color: var(--text-muted); font-size: 0.85rem;
    padding: 0.25rem 0; letter-spacing: 0.03em;
}
.stat-bar span { font-weight: 500; }

/* ============================================================
   FOOTER
   ============================================================ */
.gcms-footer {
    text-align: center; padding: 0.75rem 0;
    color: var(--text-muted); font-size: 0.74rem; letter-spacing: 0.03em;
    border-top: 1px solid var(--border-subtle); margin-top: 1rem;
}
.gcms-footer strong { color: var(--text-secondary); font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# ---- Load saved config ----
if 'config_loaded' not in st.session_state:
    saved = load_config()
    st.session_state.config_loaded = True
    # Restore language
    if saved.get('language', 'en') != get_lang():
        set_lang(saved.get('language', 'en'))
    # Save for later use
    st.session_state._saved_config = saved

saved_cfg = st.session_state.get('_saved_config', {})

# ---- Session Persistence Helpers ----
SESSION_FILE = Path(__file__).parent / '.gcms_session.pkl'

def _save_working_session():
    """Save current analysis state so it survives browser refresh/back."""
    import pickle as _pk
    state = {}
    for k in ('df', 'data_dir', 'data_loaded', 'samples', 'compounds', 'groups',
              'oav_result', 'rova_result', 'anova_result', 'plsda_result', 'rf_result',
              'plots_generated', 'replicates_loaded', 'chat_history',
              'nist_spectra_loaded', 'nist_jcamp_path', 'nist_loaded'):
        if k in st.session_state:
            v = st.session_state[k]
            # DataFrames need special handling for pickle
            if k == 'df' and v is not None and hasattr(v, 'to_pickle'):
                pass  # Will save df separately
            state[k] = v
    try:
        with open(SESSION_FILE, 'wb') as f:
            _pk.dump(state, f, protocol=_pk.HIGHEST_PROTOCOL)
    except Exception:
        pass  # Never crash on save failure

def _restore_working_session():
    """Restore previous analysis state after browser refresh."""
    import pickle as _pk
    if not SESSION_FILE.exists():
        return False
    try:
        with open(SESSION_FILE, 'rb') as f:
            state = _pk.load(f)
        df = state.get('df')
        if df is None or not state.get('data_loaded'):
            return False

        # Restore dataframe and metadata
        st.session_state.df = df
        st.session_state.data_loaded = True
        st.session_state.data_dir = state.get('data_dir', '')
        st.session_state.replicates_loaded = state.get('replicates_loaded', 1)

        # Reconstruct sample/compound/group lists from dataframe
        st.session_state.samples = sorted(df['sample'].unique().tolist())
        st.session_state.compounds = sorted(df['compound'].unique().tolist())
        st.session_state.groups = sorted(df['group'].unique().tolist()) if 'group' in df.columns else []

        # Restore analysis results + NIST state
        for k in ('oav_result', 'rova_result', 'anova_result', 'plsda_result',
                  'rf_result', 'plots_generated', 'chat_history',
                  'nist_spectra_loaded', 'nist_jcamp_path', 'nist_loaded'):
            if k in state and state[k] is not None:
                st.session_state[k] = state[k]

        # Try to reconnect agent (best effort — temp dirs may be gone)
        data_dir = st.session_state.get('data_dir', '')
        if data_dir and Path(data_dir).exists():
            try:
                from gcms_agent import GCMSAgent
                st.session_state.agent = GCMSAgent(data_dir=data_dir)
                st.session_state.agent.df = df
                _inject_nist_to_agent(st.session_state)
            except Exception:
                st.session_state.agent = None  # Agent unavailable, data still restored
        else:
            st.session_state.agent = None

        return True
    except Exception:
        return False

def _clear_working_session():
    """Delete saved session."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

# ---- Session State Init ----
for key, default in {
    'agent': None, 'df': None, 'data_loaded': False, 'data_dir': saved_cfg.get('data_dir') or None,
    'profile': None, 'samples': [], 'compounds': [], 'groups': [],
    'oav_result': None, 'rova_result': None, 'anova_result': None, 'plsda_result': None,
    'rf_result': None, 'plots_generated': {},
    'nist_loaded': saved_cfg.get('nist_loaded', False),
    'nist_entries': [], 'nist_name_index': {}, 'nist_db_path': saved_cfg.get('nist_db_path'),
    'replicates_loaded': 0,
    'nist_input_path': saved_cfg.get('nist_path', ''),
    'session_restored': False,
    'chat_history': [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---- Auto-restore last session ----
if not st.session_state.get('data_loaded') and not st.session_state.get('session_restored'):
    restored = _restore_working_session()
    if restored:
        st.session_state.session_restored = True
        st.toast('📂 ' + ('Last session restored!', '已恢复上次工作记录！')[get_lang() == 'zh'], icon='🔄')

# ---- Auto-restore NIST JCAMP index from saved path ----
if (saved_cfg.get('nist_loaded') and
    not st.session_state.get('nist_spectra_loaded') and
    not st.session_state.get('nist_spec_index') and
    saved_cfg.get('nist_jcamp_path')):
    jcamp_path = Path(saved_cfg['nist_jcamp_path'])
    if jcamp_path.exists():
        try:
            from tools.nist_local_server import SpectrumIndex
            st.session_state.nist_spec_index = SpectrumIndex()
            n = st.session_state.nist_spec_index.load_jcamp_dir(str(jcamp_path))
            st.session_state.nist_spectra_loaded = True
            st.session_state.nist_jcamp_path = str(jcamp_path)
            # Populate metadata
            meta = [{'name': s['name'], 'formula': s.get('formula','')}
                    for s in st.session_state.nist_spec_index.spectra]
            st.session_state.nist_entries = meta
            for e in meta:
                st.session_state.nist_name_index[e['name'].lower()] = e
            st.session_state.nist_loaded = True
            print(f"  [Restore] JCAMP: {n:,} spectra loaded from {jcamp_path}")
        except Exception as e:
            print(f"  [Restore] JCAMP failed: {e}")

# ---- Auto-restore NIST from SQLite DB (instant, no re-parse) ----
if (st.session_state.get('nist_loaded') and
    not st.session_state.get('nist_entries') and
    st.session_state.get('nist_db_path')):
    db_path = Path(st.session_state.nist_db_path)
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            entries = []
            for name, formula in conn.execute("SELECT name, formula FROM compounds").fetchall():
                entries.append({'name': name, 'formula': formula})
            conn.close()
            if entries:
                st.session_state.nist_entries = entries
                for e in entries:
                    st.session_state.nist_name_index[e['name'].lower()] = e
                print(f"  [Restore] NIST: {len(entries):,} compounds loaded from cache (instant)")
        except Exception:
            pass  # Silently fail — user can re-parse

def _get_pubchem_cid(name):
    """Look up PubChem CID for a compound name. Returns CID or None."""
    import urllib.request, urllib.parse, json as _json
    try:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{urllib.parse.quote(name)}/cids/JSON"
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = _json.loads(resp.read())
            cids = data.get('IdentifierList', {}).get('CID', [])
            return cids[0] if cids else None
    except:
        return None

def _inject_nist_to_agent(session):
    """Pass in-memory NIST data to the agent so it can search locally."""
    if session.get('nist_loaded') and session.get('agent'):
        session.agent.nist_entries = session.get('nist_entries', [])
        session.agent.nist_name_index = session.get('nist_name_index', {})

# ================================================================
# Sidebar — Configuration
# ================================================================
with st.sidebar:
    lang_selector()
    st.divider()

    # ── Session Restore Panel ──
    if SESSION_FILE.exists():
        try:
            import pickle as _pk
            with open(SESSION_FILE, 'rb') as f:
                _snap = _pk.load(f)
            n_rows = len(_snap.get('df', pd.DataFrame())) if _snap.get('df') is not None else 0
            n_compounds = _snap.get('df', pd.DataFrame()).compound.nunique() if n_rows > 0 and hasattr(_snap.get('df'), 'compound') else 0
            has_oav = bool(_snap.get('oav_result'))
            has_rova = bool(_snap.get('rova_result'))
            has_plots = len(_snap.get('plots_generated', {}))
            tags = []
            if has_oav: tags.append('OAV')
            if has_rova: tags.append('ROVA')
            if has_plots: tags.append(f'{has_plots} plots')
            tag_str = ' · '.join(tags) if tags else 'raw data'

            st.markdown(f"""
            <div style="background:rgba(125,211,252,0.06); border:1px solid rgba(125,211,252,0.12);
                        border-radius:8px; padding:12px 14px; margin-bottom:4px;">
                <div style="font-size:0.68rem;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;
                            color:#64748b;margin-bottom:4px;">
                    📂 {'Saved Session' if get_lang()=='en' else '已保存的工作记录'}
                </div>
                <div style="font-size:0.78rem;color:#94a3b8;line-height:1.5;">
                    {n_rows:,} {'records' if get_lang()=='en' else '条记录'} · {n_compounds} {'compounds' if get_lang()=='en' else '个化合物'}<br>
                    <span style="color:#7dd3fc;">{tag_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            cr1, cr2 = st.columns(2)
            with cr1:
                if not st.session_state.get('data_loaded'):
                    if st.button('🔄 ' + ('Restore', '恢复')[get_lang() == 'zh'], use_container_width=True,
                                 key='sess_restore_btn', type='primary'):
                        restored = _restore_working_session()
                        if restored:
                            st.session_state.session_restored = True
                            st.rerun()
                        else:
                            st.error(('Failed', '恢复失败')[get_lang() == 'zh'])
            with cr2:
                if st.button('🗑️ ' + ('Clear', '清除')[get_lang() == 'zh'], use_container_width=True,
                             key='sess_clear_btn'):
                    _clear_working_session()
                    st.rerun()
        except Exception:
            pass

    st.image("https://img.icons8.com/color/96/test-tube--v1.png", width=50)
    st.markdown(f"## 🧬 {t('app_title')}")

    # API Key
    saved_api = saved_cfg.get('api_key', '') or os.environ.get("DEEPSEEK_API_KEY", '')
    api_key = st.text_input(
        t('sidebar_api_key'),
        value=saved_api,
        type="password",
        help=t('sidebar_api_help')
    )
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key

    # ---- Save/Restore Section ----
    st.divider()
    col_save, col_del = st.columns(2)
    with col_save:
        if st.button("💾 " + ('Save Settings', '保存设置')[get_lang() == 'zh'], use_container_width=True):
            cfg = {
                'api_key': api_key,
                'nist_path': st.session_state.get('nist_input_path', ''),
                'data_dir': st.session_state.get('data_dir', ''),
                'language': get_lang(),
                'nist_loaded': st.session_state.get('nist_loaded', False),
                'nist_db_path': st.session_state.get('nist_db_path'),
                'filter_min_area': st.session_state.get('filter_min_area', 10000),
                'filter_min_match': st.session_state.get('filter_min_match', 0),
                'filter_exclude_unidentified': st.session_state.get('filter_exclude_unidentified', True),
                'filter_exclude_contaminants': st.session_state.get('filter_exclude_contaminants', True),
            }
            save_config(cfg)
            st.success('✅ ' + ('Saved!', '已保存！')[get_lang() == 'zh'])
            st.toast('💾 ' + ('Settings saved', '设置已保存')[get_lang() == 'zh'])
    with col_del:
        if st.button("🗑️ " + ('Reset', '重置')[get_lang() == 'zh'], use_container_width=True):
            from tools.config_manager import delete_config
            delete_config()
            st.session_state.config_loaded = False
            st.rerun()

    st.divider()

    # NIST Library (Local Only — No Data Upload)
    st.markdown(f"### {t('sidebar_nist')}")
    st.caption(t('sidebar_nist_caption'))

    _nm_keys = ['NIST .L Folder (Recommended)', 'JCAMP/MSP Files']
    _nm_labels = [t('sidebar_nist_l_opt'), t('sidebar_nist_jcamp_opt')]
    saved_nist_mode = saved_cfg.get('nist_mode', 'NIST .L Folder (Recommended)')
    nist_mode_idx = st.radio(
        t('sidebar_nist_format'),
        range(len(_nm_keys)),
        format_func=lambda i: _nm_labels[i],
        index=_nm_keys.index(saved_nist_mode) if saved_nist_mode in _nm_keys else 0,
        key="nist_mode_radio",
        help=".L Folder = your NIST17.L directory. JCAMP = pre-exported spectra files."
    )
    nist_mode = _nm_keys[nist_mode_idx]
    # Persist nist_mode selection
    if nist_mode != saved_nist_mode:
        save_config({**saved_cfg, 'nist_mode': nist_mode})

    if nist_mode == "NIST .L Folder (Recommended)":
        # Use session state to persist the path
        if 'nist_input_path' not in st.session_state:
            st.session_state.nist_input_path = ''

        nist_l_path = st.text_input(t('sidebar_nist_path'),
                                     value=st.session_state.nist_input_path,
                                     placeholder=t('sidebar_nist_placeholder'),
                                     help=t('sidebar_nist_help'),
                                     key="nist_path_input")
        st.session_state.nist_input_path = nist_l_path

        if st.button("🔍 Parse NIST Library", use_container_width=True):
            if nist_l_path and Path(nist_l_path).exists():
                with st.spinner("Parsing NIST library (this takes ~30s for full NIST17)..."):
                    try:
                        from tools.nist_local_server import NISTParser, build_database
                        parser_obj = NISTParser(nist_l_path)
                        entries = parser_obj.parse_entries()
                        if entries:
                            # Build in-memory search index
                            st.session_state.nist_entries = entries
                            st.session_state.nist_name_index = {}
                            for e in entries:
                                key = e['name'].lower()
                                st.session_state.nist_name_index[key] = e
                            st.session_state.nist_loaded = True
                            with_formula = sum(1 for e in entries if e.get('formula'))
                            st.success(f"✅ Loaded {len(entries):,} compounds ({with_formula:,} with formula)")
                            # Also build SQLite DB for faster search
                            db_path = Path(nist_l_path).parent / 'nist_local.db'
                            build_database(entries, db_path)
                            st.session_state.nist_db_path = str(db_path)
                            st.info(f"📁 Database saved: {db_path}")
                            # Auto-save NIST config
                            save_config({
                                'api_key': api_key,
                                'nist_path': nist_l_path,
                                'nist_loaded': True,
                                'nist_db_path': str(db_path),
                                'language': get_lang(),
                            })
                        else:
                            st.error("No valid entries found — check the path.")
                    except FileNotFoundError as e:
                        st.error(f"Not a valid NIST .L directory: {e}")
                    except Exception as e:
                        st.error(f"Parse failed: {e}")
            else:
                st.warning("Please enter a valid NIST .L folder path.")

        if st.session_state.get('nist_loaded'):
            st.caption(f"📊 {len(st.session_state.nist_entries):,} compounds indexed")

            # Quick search box (uses SQLite for instant results)
            nist_query = st.text_input("Quick search NIST", placeholder="e.g. caffeine, hexanal, C8H10N4O2",
                                        key="nist_quick_search")
            if nist_query:
                q = nist_query.lower().strip()
                results = []
                db_path = st.session_state.get('nist_db_path')
                if db_path and Path(db_path).exists():
                    import sqlite3
                    conn = sqlite3.connect(str(db_path))
                    rows = conn.execute(
                        "SELECT name, formula FROM compounds WHERE name_lower LIKE ? LIMIT 10",
                        (f'%{q}%',)
                    ).fetchall()
                    conn.close()
                    results = [{'name': r[0], 'formula': r[1]} for r in rows]
                else:
                    results = [e for e in st.session_state.nist_entries
                              if q in e['name'].lower() or (e.get('formula') and q.lower() in e['formula'].lower())][:10]
                if results:
                    for r in results:
                        f_str = f" — *{r['formula']}*" if r.get('formula') else ''
                        st.write(f"• {r['name']}{f_str}")
                    # PubChem structure for first result
                    if results and results[0].get('name'):
                        cid = _get_pubchem_cid(results[0]['name'])
                        if cid:
                            img_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG?image_size=200x150"
                            try:
                                st.image(img_url, caption=f"Structure: {results[0]['name']}", width=200)
                            except:
                                pass
                else:
                    st.caption("No matches")

    else:
        # JCAMP: two sub-options — path is saved to config for persistence
        saved_jcamp_submode = saved_cfg.get('nist_jcamp_submode', 'Exported JCAMP folder (with subdirs)')
        saved_jcamp_path = saved_cfg.get('nist_jcamp_path', '')
        jcamp_submodes = ["Exported JCAMP folder (with subdirs)", "Single JCAMP/MSP directory"]
        jcamp_submode = st.radio("JCAMP source:", jcamp_submodes,
                                 index=jcamp_submodes.index(saved_jcamp_submode) if saved_jcamp_submode in jcamp_submodes else 0,
                                 key="jcamp_submode_radio",
                                 help="'Exported' = output from tools/nist_export. 'Single' = flat directory of .jdx/.msp files.")
        # Save sub-mode selection
        if jcamp_submode != saved_cfg.get('nist_jcamp_submode', ''):
            save_config({**saved_cfg, 'nist_jcamp_submode': jcamp_submode})

        if jcamp_submode == "Exported JCAMP folder (with subdirs)":
            jcamp_export_path = st.text_input("Exported JCAMP path",
                                               value=st.session_state.get('nist_jcamp_path', saved_jcamp_path),
                                               placeholder="C:\\Users\\...\\Desktop\\JCAMP_Export",
                                               help="The folder containing 00000/, 10000/, etc. subdirectories")
            if jcamp_export_path and st.button("Load NIST Spectra Index", use_container_width=True):
                with st.spinner("Building spectrum index (~2 min for 306K spectra)..."):
                    try:
                        from tools.nist_local_server import SpectrumIndex
                        if 'nist_spec_index' not in st.session_state:
                            st.session_state.nist_spec_index = SpectrumIndex()
                        n = st.session_state.nist_spec_index.load_jcamp_dir(jcamp_export_path)
                        st.session_state.nist_spectra_loaded = True
                        st.session_state.nist_jcamp_path = jcamp_export_path
                        # Also populate metadata for quick search
                        meta_entries = [{'name': s['name'], 'formula': s.get('formula','')}
                                       for s in st.session_state.nist_spec_index.spectra]
                        st.session_state.nist_entries = meta_entries
                        for e in meta_entries:
                            st.session_state.nist_name_index[e['name'].lower()] = e
                        st.session_state.nist_loaded = True
                        st.success(f"Spectrum index: {n:,} spectra ready for matching + metadata search")
                        # Persist JCAMP path to config
                        save_config({
                            **saved_cfg,
                            'nist_jcamp_path': jcamp_export_path,
                            'nist_jcamp_submode': jcamp_submode,
                            'nist_mode': nist_mode,
                            'nist_loaded': True,
                            'language': get_lang(),
                        })
                    except Exception as e:
                        st.error(f"Failed: {e}")
            if st.session_state.get('nist_spectra_loaded'):
                st.caption(f"Spectra: {len(st.session_state.nist_spec_index.spectra):,} indexed")
        else:
            st.caption("Point to your licensed NIST JCAMP/MSP files. Spectra stay on your machine.")
            nist_path = st.text_input("NIST library path", value=saved_jcamp_path,
                                      placeholder="D:\\NIST_JCAMP",
                                      help="Directory containing .jdx/.msp files exported from NIST MS Search")
            if nist_path and st.button("Index NIST Library", use_container_width=True):
                if st.session_state.agent:
                    with st.spinner(f"Scanning {nist_path}..."):
                        r = json.loads(st.session_state.agent._set_nist_path(nist_path))
                        if 'error' not in r:
                            st.info(f"Found {r.get('total_files',0)} files")
                            r2 = json.loads(st.session_state.agent._load_nist_library())
                            st.success(f"Indexed {r2.get('nist_entries',0)} NIST spectra ({r2.get('with_ri',0)} with RI)")
                            # Persist JCAMP path to config
                            save_config({
                                **saved_cfg,
                                'nist_jcamp_path': nist_path,
                                'nist_jcamp_submode': jcamp_submode,
                                'nist_mode': nist_mode,
                                'nist_loaded': True,
                                'language': get_lang(),
                            })
                        else:
                            st.warning(r['error'])

    st.divider()

    # Data source
    st.markdown(f"### {t('sidebar_data_source')}")
    # Internal keys for radio, display with translation
    _ds_keys = ['Local Directory', 'Upload .D ZIP', 'Demo Data']
    _ds_labels = [t('data_local_dir'), t('data_upload_zip'), t('data_demo')]
    data_source_idx = st.radio(
        t('sidebar_data_source') + ':',
        range(len(_ds_keys)),
        format_func=lambda i: _ds_labels[i],
        index=0
    )
    data_source = _ds_keys[data_source_idx]

    if data_source == "Local Directory":
        data_dir = st.text_input("Data path", value="",
                                  placeholder="D:\\Experiment1",
                                  help="Folder containing .D files, CSV reports, or data.ms files")
        if st.button("🔄 Load Data", use_container_width=True) and data_dir:
            with st.spinner("Scanning and extracting..."):
                try:
                    from gcms_agent import GCMSAgent
                    st.session_state.agent = GCMSAgent(data_dir=data_dir)
                    _inject_nist_to_agent(st.session_state)
                    r = json.loads(st.session_state.agent._extract_all_data(data_dir))
                    if "error" in r:
                        st.error(r["error"])
                    else:
                        st.session_state.df = st.session_state.agent.df
                        st.session_state.data_loaded = True
                        st.session_state.data_dir = data_dir
                        st.session_state.replicates_loaded = 1
                        _save_working_session()
                        st.success(f"✅ Batch 1: {r.get('total_records',0)} peaks, {r.get('n_compounds',0)} compounds")
                except Exception as e:
                    st.error(f"Load failed: {e}")

        # ---- Replicate Batch Loading ----
        if st.session_state.get('replicates_loaded', 0) >= 1:
            st.divider()
            st.caption(f"📊 Batch 1 loaded ({st.session_state.get('replicates_loaded', 0)} batch(es)). Load replicate?")
            repl_dir = st.text_input("Replicate batch path", value="",
                                      placeholder="D:\\Experiment2 (same samples, repeated)",
                                      key="repl_path")
            if repl_dir and st.button("🔄 Load Replicate Batch", use_container_width=True):
                with st.spinner("Loading replicate batch & merging..."):
                    try:
                        r = json.loads(st.session_state.agent._load_replicate_batch(repl_dir))
                        if "error" in r:
                            st.error(r["error"])
                        else:
                            st.session_state.df = st.session_state.agent.df
                            st.session_state.replicates_loaded += 1
                            n = st.session_state.replicates_loaded
                            _save_working_session()
                            st.success(f"✅ Batch {n} merged! {len(st.session_state.df)} total records with {n}-replicate coverage")
                            st.info("📈 Plots will now show error bars (mean ± range). Statistics use pooled replicates.")
                    except Exception as e:
                        st.error(f"Replicate load failed: {e}")

    elif data_source == "Upload .D ZIP":
        uploaded = st.file_uploader("Upload .D folders as ZIP", type="zip")
        if uploaded and st.button("🔄 Extract & Load", use_container_width=True):
            with st.spinner("Extracting..."):
                tmpdir = tempfile.mkdtemp()
                with zipfile.ZipFile(uploaded) as zf:
                    zf.extractall(tmpdir)
                try:
                    from gcms_agent import GCMSAgent
                    st.session_state.agent = GCMSAgent(data_dir=tmpdir)
                    _inject_nist_to_agent(st.session_state)
                    r = json.loads(st.session_state.agent._extract_all_data(tmpdir))
                    if "error" in r:
                        st.error(r["error"])
                    else:
                        st.session_state.df = st.session_state.agent.df
                        st.session_state.data_loaded = True
                        st.session_state.data_dir = tmpdir
                        st.session_state.replicates_loaded = 1
                        _save_working_session()
                        st.success(f"✅ {r.get('total_records',0)} peaks loaded")
                except Exception as e:
                    st.error(f"Load failed: {e}")

                # ZIP replicate upload
                if st.session_state.get('replicates_loaded', 0) >= 1:
                    st.divider()
                    st.caption("Load replicate batch ZIP?")
                    repl_zip = st.file_uploader("Replicate .D ZIP", type="zip", key="repl_zip_upload")
                    if repl_zip and st.button("🔄 Load Replicate ZIP", use_container_width=True):
                        with st.spinner("Extracting & merging..."):
                            tmpdir2 = tempfile.mkdtemp()
                            with zipfile.ZipFile(repl_zip) as zf:
                                zf.extractall(tmpdir2)
                            r = json.loads(st.session_state.agent._load_replicate_batch(tmpdir2))
                            if "error" in r:
                                st.error(r["error"])
                            else:
                                st.session_state.df = st.session_state.agent.df
                                st.session_state.replicates_loaded += 1
                                _save_working_session()
                                st.success(f"✅ Merged! Now {st.session_state.replicates_loaded} replicates")

    elif data_source == "Demo Data":
        if st.button("🎲 Load Demo", use_container_width=True):
            with st.spinner("Generating demo with synthetic data..."):
                np.random.seed(42)
                samples = ['Sample_A1', 'Sample_A2', 'Sample_B1', 'Sample_B2', 'Sample_B3',
                          'Sample_C1', 'Sample_C2', 'Sample_C3', 'Sample_C4']
                groups = ['Control']*2 + ['Treatment_1']*3 + ['Treatment_2']*4
                compounds = ['Compound_01', 'Compound_02', 'Compound_03', 'Compound_04',
                           'Compound_05', 'Compound_06', 'Compound_07', 'Compound_08',
                           'Compound_09', 'Compound_10', 'Compound_11', 'Compound_12',
                           'Compound_13', 'Compound_14', 'Compound_15', 'Compound_16',
                           'Compound_17', 'Compound_18', 'Compound_19', 'Compound_20']
                records = []
                for s, g in zip(samples, groups):
                    for c in compounds:
                        base = np.random.lognormal(8, 0.8)
                        records.append({'group': g, 'sample': s, 'compound': c,
                                       'rt': round(np.random.uniform(2, 25), 3),
                                       'area': round(base * np.random.uniform(0.5, 1.5), 1),
                                       'conc_g100g': round(base * np.random.uniform(0.5, 1.5) / 10000, 6)})
                st.session_state.df = pd.DataFrame(records)
                st.session_state.data_loaded = True
                _save_working_session()
                st.info("ℹ️ This is synthetic demo data. Load your own .D files from the sidebar for real analysis.")
                st.success(f"✅ Demo loaded: {len(samples)} samples, {len(compounds)} compounds")

    # Sample & Group Configuration
    if st.session_state.data_loaded:
        st.divider()
        st.markdown("### 🏷 Rename & Group")
        with st.expander("Configure sample names and groups"):
            raw = sorted(st.session_state.df['sample'].unique().tolist())
            st.caption(f"Detected: {', '.join(raw[:8])}{'...' if len(raw)>8 else ''}")
            rename_str = st.text_area(
                "Rename (one per line: old_name=new_name)",
                placeholder="Sample001.D=Control_1\nSample002.D=Control_2\nSample003.D=Treatment_A",
                height=100
            )
            group_str = st.text_area(
                "Groups (one per line: GroupName=sample1,sample2,...)",
                placeholder="Control=Control_1,Control_2\nTreatment=Treatment_A,Treatment_B",
                height=80
            )
            if st.button("✅ Apply", use_container_width=True):
                if st.session_state.agent:
                    if rename_str.strip():
                        mapping = ','.join(line.strip() for line in rename_str.strip().split('\n') if '=' in line)
                        st.session_state.agent._rename_samples(mapping)
                    if group_str.strip():
                        for line in group_str.strip().split('\n'):
                            if '=' in line:
                                gname, members = line.split('=', 1)
                                st.session_state.agent._set_groups(gname.strip(), members.strip())
                    st.session_state.df = st.session_state.agent.df
                    st.success("✅ Applied")
                    st.rerun()

# ================================================================
# Main Content
# ================================================================
st.markdown(f'<p class="main-header">🧬 {t("app_title")}</p>', unsafe_allow_html=True)
st.markdown(f'<p class="sub-header">{t("app_subtitle")}</p>', unsafe_allow_html=True)

if not st.session_state.data_loaded:
    # ── Modern Hero Section ──
    st.markdown(f"""
    <div class="gcms-hero">
        <div class="hero-badge">🧬 {'Open-Source · AI-Powered' if get_lang() == 'en' else '开源 · AI驱动'}</div>
        <h1>{t('welcome_title')}</h1>
        <p>{t('welcome_subtitle')}</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Feature Cards ──
    c1, c2, c3, c4 = st.columns(4)
    features = [
        ('🧬', t('feature1_title'), t('feature1_desc')),
        ('🔍', t('feature2_title'), t('feature2_desc')),
        ('👃', t('feature3_title'), t('feature3_desc')),
        ('🤖', t('feature4_title'), t('feature4_desc')),
    ]
    for i, (col, (icon, title, desc)) in enumerate(zip([c1, c2, c3, c4], features)):
        with col:
            st.markdown(f"""
            <div class="card" style="text-align:center;">
                <span class="feature-icon">{icon}</span>
                <h4>{title}</h4>
                <p>{desc}</p>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Quick Start Guide ──
    steps = [
        ('1', ('Set your DeepSeek API Key in the sidebar →', '在侧边栏设置 DeepSeek API 密钥 →')),
        ('2', ('Load data: local path, upload ZIP, or try the demo below', '加载数据：输入路径、上传压缩包、或试用下方演示')),
        ('3', ('Explore: filter peaks, generate charts, calculate OAV & ROVA', '探索分析：过滤峰、生成图表、计算 OAV 与 ROVA')),
        ('4', ('Export: download publication-ready plots, Word tables, HTML reports', '导出：下载论文级图表、Word三线表、HTML报告')),
    ]
    st.markdown("#### 🚀 " + ('Quick Start', '快速开始')[get_lang() == 'zh'])
    for num, (en_text, zh_text) in steps:
        text = en_text if get_lang() == 'en' else zh_text
        st.markdown(f"""
        <div class="step-card">
            <div class="step-num">{num}</div>
            <div style="font-size:0.9rem; color:var(--text-secondary); padding-top:4px;">{text}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── CTA Demo Section ──
    st.markdown(f"""
    <div class="hero-cta">
        <h3 style="margin:0 0 0.5rem 0; font-weight:700; color:var(--text);">
            ☕ {'Try It Now — No Data Required' if get_lang() == 'en' else '立即体验 — 无需准备数据'}
        </h3>
        <p style="color:var(--text-secondary); font-size:0.9rem; margin-bottom:1rem;">
            {'Explore a pre-loaded coffee roasting flavor dataset with 20 compounds across 9 samples.' if get_lang() == 'en' else '探索预加载的咖啡烘焙风味数据集，包含 9 个样品、20 种化合物。'}
        </p>
    </div>
    """, unsafe_allow_html=True)

    demo_col1, demo_col2, demo_col3 = st.columns([1, 2, 1])
    with demo_col2:
        if st.button(t('btn_try_demo'), type="primary", use_container_width=True):
            with st.spinner(t('msg_demo_loading')):
                from tools.demo_data import generate_demo_dataset
                df = generate_demo_dataset()
                st.session_state.df = df
                st.session_state.data_loaded = True
                st.session_state.data_dir = "Demo: Coffee Roasting Experiment"
                st.session_state.samples = df['sample'].unique().tolist()
                _save_working_session()
                st.session_state.compounds = df['compound'].unique().tolist()
                st.session_state.groups = df['group'].unique().tolist()
            st.rerun()

    st.caption(t('demo_or_load'))

    # ── Stats Bar ──
    st.divider()
    st.markdown(f"""
    <div class="stat-bar">
        <span>{t('stat_tools')}</span>
        <span>{t('stat_library')}</span>
        <span>{t('stat_interface')}</span>
        <span>{t('stat_license')}</span>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ---- Auto-reconnect agent if data loaded but agent lost ----
if st.session_state.get('data_loaded') and st.session_state.get('df') is not None:
    if st.session_state.get('agent') is None:
        try:
            from gcms_agent import GCMSAgent
            agent = GCMSAgent(data_dir=st.session_state.get('data_dir', ''))
            agent.df = st.session_state.df
            _inject_nist_to_agent(st.session_state)
            st.session_state.agent = agent
        except Exception:
            pass  # Agent unavailable, some features may be limited

# ---- Tabs ----
df = st.session_state.df
tab_data, tab_plots, tab_flavor, tab_stats, tab_viz, tab_ai, tab_export = st.tabs(
    [t('tab_data'), t('tab_plots'), t('tab_flavor'), t('tab_stats'), t('tab_viz'),
     '🤖 ' + ('AI Analysis', 'AI 智能分析')[get_lang() == 'zh'],
     t('tab_export')]
)

# ================================================================
# Tab 1: Data Browser
# ================================================================
with tab_data:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(t('metric_samples'), df['sample'].nunique())
    with c2:
        st.metric(t('metric_compounds'), df['compound'].nunique())
    with c3:
        st.metric(t('metric_records'), len(df))
    with c4:
        g = df['group'].nunique() if 'group' in df.columns else 1
        st.metric(t('metric_groups'), g)

    # ── Quick Spectral Search (populate match_factor) ──
    has_match = any(c in df.columns for c in ['match_factor', 'match', 'match_quality'])
    match_exists = has_match and (
        (df.get('match_factor', pd.Series([])).notna().sum() > 0) if 'match_factor' in df.columns else
        (df.get('match', pd.Series([])).notna().sum() > 0) if 'match' in df.columns else False
    )
    if not match_exists and st.session_state.agent:
        st.divider()
        st.caption(
            ('💡 Match scores are empty — built-in library only gives compound names, not similarity scores. '
             'Click below to search public spectral libraries (MoNA + MassBank) for match quality values.',
             '💡 匹配度评分为空 — 内置库只提供化合物名称，不含相似度分值。点击下方按钮搜索公开谱库获取匹配度。')[get_lang() == 'zh']
        )
        if st.button('🔬 ' + ('Search Public Libraries for Match Scores', '搜索公开谱库获取匹配分值')[get_lang() == 'zh'],
                     use_container_width=True, type='secondary'):
            with st.spinner(('Searching MoNA + MassBank + NIST WebBook...\n\nThis may take 1-3 minutes for all compounds.',
                             '正在搜索 MoNA + MassBank + NIST WebBook...\n\n可能需要 1-3 分钟。')[get_lang() == 'zh']):
                try:
                    r = json.loads(st.session_state.agent._enhance_identification(max_per_sample=50))
                    if r.get('status') == 'done':
                        st.session_state.df = st.session_state.agent.df
                        _save_working_session()
                        new_matches = 0
                        if 'match_factor' in st.session_state.agent.df.columns:
                            new_matches = st.session_state.agent.df['match_factor'].notna().sum()
                        st.success(f"✅ {'Match scores populated! ' + str(new_matches) + ' compounds now have match data.' if get_lang()=='en' else '匹配分值已更新！' + str(new_matches) + ' 个化合物现在有匹配数据。'}")
                        st.rerun()
                    else:
                        st.warning(str(r.get('error', 'Unknown error')))
                except Exception as e:
                    st.error(f"Search failed: {e}")

        # ── NIST Local Spectral Matching ──
        nist_available = (st.session_state.get('nist_loaded') or
                          st.session_state.get('nist_spectra_loaded') or
                          st.session_state.get('nist_spec_index') is not None)
        if nist_available and st.session_state.agent:
            if st.button('🧬 ' + ('Run NIST Spectral Matching (Local)', '运行 NIST 质谱匹配 (本地)')[get_lang() == 'zh'],
                         use_container_width=True):
                with st.spinner(('Extracting mass spectra & searching NIST library...',
                                 '正在提取质谱并搜索 NIST 谱库...')[get_lang() == 'zh']):
                    try:
                        agent = st.session_state.agent
                        n_matched = 0
                        from pathlib import Path as P
                        import numpy as np

                        # Recursively find .D folders with data.ms
                        data_dir = st.session_state.get('data_dir', '')
                        d_folders = []
                        if data_dir and P(data_dir).exists():
                            for ms_file in P(data_dir).rglob('data.ms'):
                                d_folders.append(ms_file.parent)

                        spec_idx = (st.session_state.get('nist_spec_index') or
                                     st.session_state.get('nist_spectra_index'))
                        if d_folders and spec_idx:
                            for d_folder in d_folders[:5]:  # First 5 .D folders
                                try:
                                    from aston.tracefile.agilent_ms import AgilentMS
                                    ms_file = d_folder / 'data.ms'
                                    tf = AgilentMS(str(ms_file))
                                    sample_name = d_folder.name.replace('.D', '')

                                    sdf = agent.df[agent.df['sample'] == sample_name]
                                    for idx, row in sdf.iterrows():
                                        rt = row['rt']
                                        if pd.isna(rt):
                                            continue
                                        try:
                                            spec = tf.spectrum_at_time(rt * 60)  # min → sec
                                            ions = [(float(mz), float(intens))
                                                    for mz, intens in zip(spec.mz, spec.intensity)
                                                    if intens > 0]
                                            if len(ions) >= 10:
                                                hits = spec_idx.search_spectrum(ions[:100], max_results=1, min_match=0)
                                                if hits and hits[0].get('match_score', 0) > 0:
                                                    agent.df.at[idx, 'match_factor'] = float(hits[0]['match_score'])
                                                    agent.df.at[idx, 'reverse_match'] = float(hits[0].get('reverse_match', hits[0]['match_score']))
                                                    agent.df.at[idx, 'match_method'] = 'nist_local'
                                                    if hits[0].get('formula'):
                                                        agent.df.at[idx, 'formula'] = str(hits[0]['formula'])
                                                    if hits[0].get('cas'):
                                                        agent.df.at[idx, 'cas'] = str(hits[0]['cas'])
                                                    n_matched += 1
                                        except Exception:
                                            continue
                                except ImportError:
                                    st.warning('Aston library required for mass spectrum extraction.')
                                    break
                                except Exception as e:
                                    continue

                            st.session_state.df = agent.df
                            _save_working_session()
                            if n_matched > 0:
                                st.success(f'✅ NIST 匹配完成！{n_matched} 个化合物获得匹配分值。')
                                st.rerun()
                            else:
                                st.info('NIST 匹配未能产生结果。请确认数据包含 mass spectra (.D 文件夹)。')
                        else:
                            if not d_folders:
                                st.warning(
                                    ('No .D folders with data.ms found in: ' + str(data_dir)[:60] + '\n\n'
                                     'Your data may be in a subfolder. The search is now recursive.',
                                     '未找到包含 data.ms 的 .D 文件夹。路径: ' + str(data_dir)[:60] + '\n\n'
                                     '已使用递归搜索，如仍未找到请检查数据目录结构。')[get_lang() == 'zh'])
                            else:
                                st.warning(
                                    ('NIST spectra not loaded. Load JCAMP or .L library in sidebar first.',
                                     '未加载 NIST 谱库。请先在侧边栏加载 JCAMP 或 .L 谱库。')[get_lang() == 'zh'])
                    except Exception as e:
                        st.error(f'NIST matching failed: {e}')

    # Filters
    st.divider()
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        min_area = st.number_input(t('filter_min_area'), value=10000, step=1000,
                                   key='filter_min_area_widget')
    with fc2:
        # Always show match slider — auto-detect if column exists
        has_match = 'match_factor' in df.columns or 'match' in df.columns or 'match_quality' in df.columns
        match_col = None
        if 'match_factor' in df.columns:
            match_col = 'match_factor'
        elif 'match' in df.columns:
            match_col = 'match'
        elif 'match_quality' in df.columns:
            match_col = 'match_quality'
        min_match = st.slider(
            t('filter_min_match'), 0, 100, 0,
            disabled=not has_match,
            help=('Drag to filter compounds below this match score. Only available when match data exists.',
                  '拖动滑块过滤低于此匹配度的化合物。仅在有匹配数据时可用。')[get_lang() == 'zh'])
    with fc3:
        excl_unid = st.checkbox(t('filter_excl_unid'), True)
    with fc4:
        excl_cont = st.checkbox(t('filter_excl_cont'), True)

    # Apply filters (real-time, no button needed)
    filtered = df.copy()
    if min_area > 0:
        filtered = filtered[filtered['area'] >= min_area]
    if min_match > 0 and match_col and match_col in filtered.columns:
        filtered = filtered[filtered[match_col].isna() | (filtered[match_col] >= min_match)]
    if excl_unid:
        filtered = filtered[~filtered['compound'].str.startswith('RT_', na=False)]
    if excl_cont:
        cont = ['siloxane', 'phthalate', 'column bleed', 'exclude']
        filtered = filtered[~filtered['compound'].str.lower().str.contains('|'.join(cont), na=False)]

    st.markdown(f"**Filtered: {len(filtered)} records, {filtered['compound'].nunique()} compounds, {filtered['sample'].nunique()} samples**")

    # Build display columns — always include match info if available
    display_cols = ['sample', 'group', 'compound', 'rt', 'area']
    extra_cols = []
    if match_col and match_col in filtered.columns:
        extra_cols.append(match_col)
    for c in ['height', 'amount', 'conc_g100g']:
        if c in filtered.columns:
            extra_cols.append(c)

    # Build column_config, handling None values gracefully
    col_cfg = {
        'rt': st.column_config.NumberColumn('RT (min)', format='%.3f'),
        'area': st.column_config.NumberColumn('Area', format='%.0f'),
    }
    if match_col and match_col in filtered.columns:
        has_real_match = filtered[match_col].notna().any()
        if has_real_match:
            col_cfg[match_col] = st.column_config.NumberColumn('Match %', format='%.0f')
        else:
            col_cfg[match_col] = st.column_config.TextColumn('Match %')
    if 'height' in extra_cols:
        col_cfg['height'] = st.column_config.NumberColumn('Height', format='%.0f')
    if 'amount' in extra_cols:
        col_cfg['amount'] = st.column_config.NumberColumn('Amount', format='%.4f')
    if 'conc_g100g' in extra_cols:
        col_cfg['conc_g100g'] = st.column_config.NumberColumn('Conc (g/100g)', format='%.6f')

    # Show "—" for None match values
    show_df = filtered[display_cols + extra_cols].head(200).copy()
    if match_col and match_col in show_df.columns and not has_real_match:
        show_df[match_col] = show_df[match_col].fillna('—')

    st.dataframe(show_df, use_container_width=True, height=400, column_config=col_cfg)

    if match_col and match_col in filtered.columns and not has_real_match:
        st.caption(
            ('💡 Match scores are unavailable — run NIST/MoNA spectral search to get match quality values.',
             '💡 匹配度评分为空 — 运行 NIST 或 MoNA 谱库搜索后可获得匹配分值。')[get_lang() == 'zh']
        )

    # Update agent's df
    if st.session_state.agent:
        st.session_state.agent.df = filtered

# ================================================================
# Tab 2: Plots
# ================================================================
with tab_plots:
    st.markdown("### Publication-Quality Charts")

    plot_type = st.selectbox("Chart Type", ["Bar Chart", "Heatmap", "PCA", "Volcano",
                                             "Boxplot", "Composition", "Dashboard", "All"])
    plot_title = st.text_input("Chart Title (optional)", "")

    if st.button("🎨 Generate Plot", type="primary"):
        if not st.session_state.agent:
            if df is None or len(df) == 0:
                st.error("Agent not initialized. Load data first.")
            else:
                st.warning("Agent unavailable (session restored). Use Nature or Plotly charts instead.")
        else:
            agent = st.session_state.agent
            with st.spinner("Generating..."):
                try:
                    if plot_type in ("Bar Chart", "All"):
                        r = json.loads(agent._generate_plots(plot_type='bar',
                                     title=plot_title or 'Flavor Compounds by Group'))
                        st.session_state.plots_generated['bar'] = r
                    if plot_type in ("Heatmap", "All"):
                        r = json.loads(agent._generate_plots(plot_type='heatmap',
                                     title=plot_title or 'Hierarchical Clustering'))
                        st.session_state.plots_generated['heatmap'] = r
                    if plot_type in ("PCA", "All"):
                        r = json.loads(agent._generate_plots(plot_type='pca',
                                     title=plot_title or 'PCA Analysis'))
                        st.session_state.plots_generated['pca'] = r
                    if plot_type in ("Boxplot", "All"):
                        r = json.loads(agent._generate_plots(plot_type='boxplot',
                                     title=plot_title or 'Distribution'))
                        st.session_state.plots_generated['boxplot'] = r
                    if plot_type in ("Composition", "All"):
                        r = json.loads(agent._generate_plots(plot_type='composition',
                                     title=plot_title or 'Composition Profile'))
                        st.session_state.plots_generated['composition'] = r
                    if plot_type in ("Dashboard", "All"):
                        r = json.loads(agent._generate_plots(plot_type='dashboard',
                                     title=plot_title or 'Dashboard'))
                        st.session_state.plots_generated['dashboard'] = r
                    if plot_type in ("Volcano", "All"):
                        groups = df['group'].unique()
                        if len(groups) >= 2:
                            r = json.loads(agent._volcano_plot(group_a=str(groups[0]),
                                         group_b=str(groups[1]), p_threshold=0.1))
                            st.session_state.plots_generated['volcano'] = r
                    st.success("✅ Plots generated!")
                    _save_working_session()
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── Professional Plotly Charts ──
    # ── Nature Journal Figures ──
    st.markdown("#### " + ('Nature Journal Figures (600dpi TIFF)', 'Nature 期刊图表 (600dpi TIFF)')[get_lang() == 'zh'])
    nc1, nc2, nc3, nc4, nc5 = st.columns([1, 2, 2, 2, 1])
    with nc2:
        nature_type = st.selectbox('Type', ['bar','pca','heatmap','volcano','boxplot','all'], key='nature_type')
    with nc3:
        nature_size = st.selectbox('Size', ['single','1.5col','double'],
                                    format_func=lambda s: {'single':'89mm','1.5col':'140mm','double':'183mm'}[s],
                                    key='nature_size')
    with nc4:
        st.write('')
        if st.button('🧬 Generate', type='primary', key='nature_btn'):
            if df is not None and len(df) > 0:
                with st.spinner('Generating Nature-quality figure...'):
                    try:
                        from tools.nature_skills import generate_nature_figures
                        r = generate_nature_figures(df, nature_type, nature_size)
                        files = r.get('files', [])
                        if files:
                            st.success(f"✅ {r['count']} figure(s) generated!")
                            # Display preview + download — centered
                            for f in files:
                                if isinstance(f, dict):
                                    tiff_path, png_path = f.get('tiff',''), f.get('png','')
                                    fig_type = f.get('type','')
                                else:
                                    tiff_path = str(f)
                                    png_path = tiff_path.replace('.tiff','.png')
                                    fig_type = ''
                                # Generate PNG preview if not exist
                                if not Path(png_path).exists() and Path(tiff_path).exists():
                                    from PIL import Image
                                    Image.open(tiff_path).save(png_path)
                                if Path(png_path).exists():
                                    st.image(str(png_path), caption=f'Nature {fig_type} ({nature_size})')
                                if Path(tiff_path).exists():
                                    with open(tiff_path, 'rb') as tf:
                                        st.download_button(
                                            f'📥 {Path(tiff_path).name}',
                                            tf.read(),
                                            file_name=Path(tiff_path).name,
                                            mime='image/tiff'
                                        )
                    except Exception as e:
                        st.error(f"Failed: {e}")
            else:
                st.warning(('Load data first', '请先加载数据')[get_lang() == 'zh'])

    st.divider()

    st.markdown("#### " + ('Professional Interactive Charts (Plotly)', '专业交互式图表 (Plotly)')[get_lang() == 'zh'])
    plotly_type = st.selectbox(
        ('Chart Type', '图表类型')[get_lang() == 'zh'],
        ['pca', 'heatmap', 'bar', 'volcano', 'radar', 'dashboard'],
        key='plotly_chart_type')
    if st.button('🚀 ' + ('Generate Interactive Chart', '生成交互图表')[get_lang() == 'zh'],
                 type='primary', key='plotly_gen_btn'):
        if df is not None and len(df) > 0:
            with st.spinner('Generating Plotly chart...'):
                try:
                    import plotly.graph_objects as go
                    import plotly.express as px
                    from sklearn.decomposition import PCA
                    from sklearn.preprocessing import StandardScaler
                    import numpy as np

                    plots_dir = Path("output/agent_results/plots")
                    plots_dir.mkdir(parents=True, exist_ok=True)

                    val_col = 'area'
                    if 'conc_g100g' in df.columns and df['conc_g100g'].notna().sum() > 5:
                        val_col = 'conc_g100g'
                    elif 'amount' in df.columns and df['amount'].notna().sum() > 5:
                        val_col = 'amount'

                    colors = ['#7dd3fc','#4adeb0','#fbbf24','#f87171','#a78bfa',
                              '#fb923c','#e879f9','#67e8f9','#fda4af','#86efac']

                    if plotly_type == 'pca':
                        pivot = df.pivot_table(values=val_col, index='sample', columns='compound', aggfunc='mean').fillna(0)
                        X_s = StandardScaler().fit_transform(pivot.values)
                        pca = PCA(n_components=min(3, X_s.shape[0], X_s.shape[1]))
                        X_pca = pca.fit_transform(X_s)
                        evr = pca.explained_variance_ratio_
                        samples_all = list(pivot.index)
                        groups_uniq = sorted(df['group'].unique()) if 'group' in df.columns else ['All']
                        group_map = dict(zip(df['sample'], df['group'])) if 'group' in df.columns else {s:'All' for s in samples_all}

                        fig = go.Figure()
                        for gi, grp in enumerate(groups_uniq):
                            idxs = [i for i,s in enumerate(samples_all) if group_map.get(s)==grp]
                            if not idxs: continue
                            fig.add_trace(go.Scatter(
                                x=X_pca[idxs,0], y=X_pca[idxs,1] if X_pca.shape[1]>=2 else [0]*len(idxs),
                                mode='markers+text', name=str(grp),
                                text=[str(samples_all[i]).replace('.D','') for i in idxs],
                                textposition='top center', textfont=dict(size=10, color='#94a3b8'),
                                marker=dict(size=14, color=colors[gi%len(colors)], line=dict(width=1, color='rgba(0,0,0,0.1)')),
                                hovertemplate='<b>%{text}</b><br>PC1: %{x:.2f}<br>PC2: %{y:.2f}<extra></extra>'))
                        fig.update_layout(
                            title=f'PCA ({evr[0]*100:.1f}% + {evr[1]*100:.1f}%)',
                            xaxis_title=f'PC1 ({evr[0]*100:.1f}%)', yaxis_title=f'PC2 ({evr[1]*100:.1f}%)',
                            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(gridcolor='rgba(255,255,255,0.04)', color='#94a3b8'),
                            yaxis=dict(gridcolor='rgba(255,255,255,0.04)', color='#94a3b8'),
                            height=520, dragmode='pan',
                            legend=dict(orientation='h', y=1.12, x=0.5, xanchor='center', font=dict(color='#94a3b8'))
                        )
                        path = str(plots_dir / 'pca_interactive.html')
                        fig.write_html(path, include_plotlyjs='cdn')

                    elif plotly_type == 'heatmap':
                        pivot = df.pivot_table(values=val_col, index='sample', columns='compound', aggfunc='mean').fillna(0)
                        data_z = ((pivot-pivot.mean())/pivot.std()).fillna(0)
                        from scipy.cluster.hierarchy import linkage, leaves_list
                        Z = linkage(data_z.values, method='ward')
                        row_order = leaves_list(Z)
                        Zc = linkage(data_z.T.values, method='ward')
                        col_order = leaves_list(Zc)
                        d = data_z.iloc[row_order, col_order]
                        fig = go.Figure(data=go.Heatmap(
                            z=d.values, x=[str(c)[:20] for c in d.columns],
                            y=[str(i).replace('.D','') for i in d.index],
                            colorscale='RdBu_r', zmid=0,
                            hovertemplate='<b>%{x}</b><br>%{y}<br>Z: %{z:.2f}<extra></extra>',
                            colorbar=dict(title='Z-score', len=0.5, tickfont=dict(color='#94a3b8')))
                        )
                        fig.update_layout(height=max(500,len(pivot)*28),
                                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                          xaxis=dict(tickfont=dict(size=9, color='#94a3b8')),
                                          yaxis=dict(tickfont=dict(size=9, color='#94a3b8')))
                        path = str(plots_dir / 'heatmap_interactive.html')
                        fig.write_html(path, include_plotlyjs='cdn')

                    elif plotly_type == 'bar':
                        if 'group' in df.columns and df['group'].nunique() >= 2:
                            top12 = df.groupby('compound')[val_col].mean().nlargest(12).index
                            gdata = df[df['compound'].isin(top12)].groupby(['group','compound'])[val_col].mean().reset_index()
                            fig = px.bar(gdata, x='compound', y=val_col, color='group', barmode='group')
                        else:
                            top15 = df.groupby('compound')[val_col].mean().nlargest(15).reset_index()
                            fig = px.bar(top15, x=val_col, y='compound', orientation='h')
                        fig.update_layout(height=450, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                          xaxis=dict(gridcolor='rgba(255,255,255,0.04)', color='#94a3b8'),
                                          yaxis=dict(gridcolor='rgba(255,255,255,0.04)', color='#94a3b8'),
                                          legend=dict(font=dict(color='#94a3b8')), font=dict(color='#94a3b8'))
                        path = str(plots_dir / 'bar_interactive.html')
                        fig.write_html(path, include_plotlyjs='cdn')

                    elif plotly_type == 'volcano':
                        groups = df['group'].unique()
                        if len(groups) >= 2:
                            g1, g2 = str(groups[0]), str(groups[1])
                            m1 = df[df['group']==g1].groupby('compound')[val_col].mean()
                            m2 = df[df['group']==g2].groupby('compound')[val_col].mean()
                            common = list(m1.index.intersection(m2.index))
                            fc = np.log2((m2[common].values+1e-6)/(m1[common].values+1e-6))
                            from scipy.stats import ttest_ind
                            pvals=[]
                            for c in common:
                                v1=df[(df['group']==g1)&(df['compound']==c)][val_col]
                                v2=df[(df['group']==g2)&(df['compound']==c)][val_col]
                                try: _,pv=ttest_ind(v1,v2); pvals.append(max(pv,1e-300))
                                except: pvals.append(1.0)
                            nlp=-np.log10(pvals)
                            fig=go.Figure()
                            fig.add_trace(go.Scatter(
                                x=fc, y=nlp, mode='markers',
                                marker=dict(size=8, color=['#f87171' if abs(f)>1 and n>1.3 else '#64748b' for f,n in zip(fc,nlp)], line=dict(width=0)),
                                text=common, hovertemplate='<b>%{text}</b><br>log2FC:%{x:.2f}<br>-log10(p):%{y:.2f}<extra></extra>'))
                            fig.add_hline(y=1.3, line_dash='dash', line_color='rgba(128,128,128,0.3)')
                            fig.update_layout(
                                title=f'{g1} vs {g2}', xaxis_title='log2 Fold Change', yaxis_title='-log10(p)',
                                height=500, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                                xaxis=dict(gridcolor='rgba(255,255,255,0.04)', color='#94a3b8'),
                                yaxis=dict(gridcolor='rgba(255,255,255,0.04)', color='#94a3b8'))
                            path = str(plots_dir / 'volcano_interactive.html')
                            fig.write_html(path, include_plotlyjs='cdn')
                        else:
                            st.warning('Need at least 2 groups for volcano plot')

                    elif plotly_type == 'radar':
                        from flavor_tools import calculate_oav
                        CATS = {
                            '青香/草香': ['hexanal','heptanal','octanal','nonanal','decanal'],
                            '果香/甜香': ['ethyl acetate','isoamyl acetate','benzaldehyde','vanillin','linalool'],
                            '烤香/坚果': ['2-methylpyrazine','2,5-dimethylpyrazine','furfural'],
                            '油脂/酸败': ['2,4-decadienal','butyric acid','hexanoic acid'],
                            '土味/霉味': ['geosmin','1-octen-3-ol','indole'],
                            '花香/辛香': ['alpha-pinene','limonene','eugenol','thymol'],
                            '含硫化合物': ['dimethyl sulfide','dimethyl disulfide','methional'],
                            '发酵/乳品': ['acetoin','2,3-butanedione','acetic acid'],
                        }
                        try:
                            df_oav = calculate_oav(df)
                            scores={}
                            for cat,comps in CATS.items():
                                s=0.0
                                for c in comps:
                                    mask=df_oav['compound'].str.lower().str.strip()==c.lower()
                                    if mask.any(): s+=float(df_oav.loc[mask,'log_oav'].mean())
                                scores[cat]=max(s,0.01)
                            cats=list(scores.keys()); vals=[scores[c] for c in cats]
                            fig=go.Figure()
                            fig.add_trace(go.Scatterpolar(r=vals+[vals[0]],theta=cats+[cats[0]],fill='toself',
                                fillcolor='rgba(125,211,252,0.15)',line=dict(color='#7dd3fc',width=2.5),
                                marker=dict(size=6,color='#7dd3fc')))
                            fig.update_layout(
                                polar=dict(radialaxis=dict(range=[0,max(vals)*1.2],gridcolor='rgba(255,255,255,0.05)',color='#64748b'),
                                           angularaxis=dict(gridcolor='rgba(255,255,255,0.05)',color='#94a3b8',tickfont=dict(size=12)),
                                           bgcolor='rgba(0,0,0,0)'),
                                height=500, paper_bgcolor='rgba(0,0,0,0)', showlegend=False)
                            path = str(plots_dir / 'radar_interactive.html')
                            fig.write_html(path, include_plotlyjs='cdn')
                        except Exception as e:
                            st.error(f'Radar failed: {e}')

                    elif plotly_type == 'dashboard':
                        from plotly.subplots import make_subplots
                        pivot = df.pivot_table(values=val_col, index='sample', columns='compound', aggfunc='mean').fillna(0)
                        X_s = StandardScaler().fit_transform(pivot.values)
                        pca_obj = PCA(n_components=min(3,X_s.shape[0],X_s.shape[1]))
                        X_pca = pca_obj.fit_transform(X_s)
                        evr = pca_obj.explained_variance_ratio_
                        top10 = df.groupby('compound')[val_col].mean().nlargest(10)
                        groups_uniq = sorted(df['group'].unique()) if 'group' in df.columns else ['All']
                        gm = dict(zip(df['sample'],df['group'])) if 'group' in df.columns else {}

                        fig=make_subplots(rows=2,cols=2,subplot_titles=('Top Compounds','PCA','Heatmap','Distribution'),
                            specs=[[{'type':'bar'},{'type':'scatter'}],[{'type':'heatmap'},{'type':'bar'}]])
                        fig.add_trace(go.Bar(x=top10.values,y=top10.index,orientation='h',marker_color='#7dd3fc'),row=1,col=1)
                        for gi,grp in enumerate(groups_uniq):
                            idxs=[i for i,s in enumerate(pivot.index) if gm.get(s)==grp]
                            if not idxs: continue
                            fig.add_trace(go.Scatter(x=X_pca[idxs,0],y=X_pca[idxs,1],mode='markers+text',
                                name=str(grp),text=[str(pivot.index[i]).replace('.D','') for i in idxs],
                                textposition='top center',textfont=dict(size=9),
                                marker=dict(size=10,color=colors[gi%len(colors)])),row=1,col=2)
                        dz=((pivot-pivot.mean())/pivot.std()).fillna(0)
                        fig.add_trace(go.Heatmap(z=dz.values,x=[str(c)[:15] for c in dz.columns],
                            y=[str(i).replace('.D','') for i in dz.index],colorscale='RdBu_r',zmid=0,showscale=False),row=2,col=1)
                        fig.add_trace(go.Histogram(x=df[val_col],marker_color='#7dd3fc',nbinsx=30),row=2,col=2)
                        fig.update_layout(height=800,paper_bgcolor='rgba(0,0,0,0)',
                            xaxis=dict(color='#94a3b8'),yaxis=dict(color='#94a3b8'),
                            xaxis2=dict(color='#94a3b8'),yaxis2=dict(color='#94a3b8'),
                            xaxis3=dict(color='#94a3b8'),yaxis3=dict(color='#94a3b8'),
                            xaxis4=dict(color='#94a3b8'),yaxis4=dict(color='#94a3b8'),
                            showlegend=True, legend=dict(font=dict(color='#94a3b8')))
                        path = str(plots_dir / 'dashboard_interactive.html')
                        fig.write_html(path, include_plotlyjs='cdn')

                    if 'path' in dir():
                        st.success(f'✅ {plotly_type}_interactive.html generated!')
                        _save_working_session()
                    else:
                        st.warning('No chart generated for this type')

                except Exception as e:
                    st.error(f"Failed: {e}")
        else:
            st.warning(('Load data first', '请先加载数据')[get_lang() == 'zh'])

    # Display generated plots
    plot_dir = Path("output/agent_results/plots")
    if plot_dir.exists():
        # Show interactive HTML files first
        htmls = sorted(plot_dir.glob("*_interactive.html"))
        if htmls:
            st.divider()
            st.markdown("##### " + ('Interactive Charts', '交互式图表')[get_lang() == 'zh'])
            chosen_html = st.selectbox(
                ('Select to view:', '选择查看：')[get_lang() == 'zh'],
                [h.name for h in htmls])
            if chosen_html:
                html_path = plot_dir / chosen_html
                with open(html_path, 'r', encoding='utf-8') as f:
                    st.components.v1.html(f.read(), height=620, scrolling=True)

        # Then static PNGs
        images = sorted(plot_dir.glob("*.png"))
        if images:
            st.divider()
            st.markdown("##### " + ('Static PNGs', '静态图片')[get_lang() == 'zh'])
            cols = st.columns(2)
            for i, img_path in enumerate(images[-8:]):
                with cols[i % 2]:
                    st.image(str(img_path), caption=img_path.name, use_container_width=True)

            if len(images) > 0:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w') as zf:
                    for p in images:
                        zf.write(p, p.name)
                st.download_button("📥 Download All Plots (ZIP)", buf.getvalue(),
                                   "gcms_plots.zip", "application/zip")

# ================================================================
# Tab 3: Flavor Analysis
# ================================================================
with tab_flavor:
    st.markdown("### 👃 Flavor & Aroma Analysis")

    if st.button("🔬 Calculate OAV (Odor Activity Values)", type="primary"):
        if st.session_state.agent:
            with st.spinner("Computing OAV..."):
                r = json.loads(st.session_state.agent._calculate_oav())
                st.session_state.oav_result = r
                _save_working_session()
        else:
            from flavor_tools import calculate_oav, get_oav_summary
            s = get_oav_summary(df)
            st.session_state.oav_result = {'oav_summary': s}
            _save_working_session()

    if st.session_state.oav_result:
        s = st.session_state.oav_result['oav_summary']
        oav_top = s['top_oav_overall'][:12]
        oav_by_group = s.get('top_oav_by_group', {})
        is_zh = get_lang() == 'zh'

        if oav_top:
            st.markdown("#### " + ('Odor Activity Values (OAV) — Top Compounds', '气味活性值 (OAV) — 关键香气化合物')[is_zh])

            # Multi-group comparison or single overview
            if len(oav_by_group) >= 2:
                # Grouped bar chart: compare OAV across groups
                groups = list(oav_by_group.keys())
                # Collect compounds that appear in at least one group's top 10
                all_comps = set()
                for g in groups:
                    for c in oav_by_group[g][:8]:
                        all_comps.add(c['compound'])
                all_comps = list(all_comps)[:12]

                fig_oav = go.Figure()
                group_colors = ['#7dd3fc', '#4adeb0', '#fbbf24', '#f87171', '#a78bfa']
                for gi, g in enumerate(groups):
                    gdata = {c['compound']: c['mean_oav'] for c in oav_by_group[g]}
                    x_vals = [gdata.get(c, 0) for c in all_comps]
                    fig_oav.add_trace(go.Bar(
                        name=str(g),
                        x=all_comps, y=x_vals,
                        marker_color=group_colors[gi % len(group_colors)],
                        text=[f'{v:.0f}' if v > 0 else '' for v in x_vals],
                        textposition='outside', textfont=dict(size=10, color='#94a3b8'),
                        hovertemplate='<b>%{x}</b><br>' + str(g) + ': %{y:.1f}<extra></extra>'
                    ))
                fig_oav.update_layout(
                    barmode='group', bargap=0.15, bargroupgap=0.1,
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=10, r=10, t=10, b=80),
                    height=420,
                    xaxis=dict(tickangle=-35, color='#94a3b8', tickfont=dict(size=10),
                               gridcolor='rgba(255,255,255,0.03)'),
                    yaxis=dict(title='OAV' if not is_zh else 'OAV 值', color='#94a3b8',
                               gridcolor='rgba(255,255,255,0.04)', type='log'),
                    legend=dict(orientation='h', yanchor='top', y=-0.15, xanchor='center', x=0.5,
                                font=dict(color='#94a3b8', size=11)),
                    dragmode=False
                )
            else:
                # Single horizontal bar chart
                names_oat = [x['compound'] for x in reversed(oav_top)]
                vals_oat = [x['mean_oav'] for x in reversed(oav_top)]
                imps_oat = [x['impact'] for x in reversed(oav_top)]
                imp_colors = {'dominant': '#f87171','significant': '#fbbf24',
                              'contributing': '#7dd3fc','negligible': '#64748b'}
                bars_oat = [imp_colors.get(imp, '#64748b') for imp in imps_oat]

                fig_oav = go.Figure()
                fig_oav.add_trace(go.Bar(
                    x=vals_oat, y=names_oat, orientation='h',
                    marker=dict(color=bars_oat, line=dict(width=0)),
                    text=[f'{v:.0f}' for v in vals_oat],
                    textposition='outside', textfont=dict(size=11, color='#94a3b8'),
                    hovertemplate='<b>%{y}</b><br>OAV: %{x:.0f}<br>' +
                                  ('Impact: %{customdata}' if not is_zh else '等级: %{customdata}') +
                                  '<extra></extra>',
                    customdata=imps_oat
                ))
                fig_oav.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=10, r=70, t=10, b=10), height=380,
                    xaxis=dict(title='OAV (log scale)', color='#94a3b8',
                               gridcolor='rgba(255,255,255,0.04)', type='log'),
                    yaxis=dict(color='#94a3b8', automargin=True, tickfont=dict(size=11)),
                    showlegend=False, dragmode=False
                )
                st.caption('  '.join([
                    '<span style="color:#f87171">● dominant</span>',
                    '<span style="color:#fbbf24">● significant</span>',
                    '<span style="color:#7dd3fc">● contributing</span>',
                    '<span style="color:#64748b">● negligible</span>'
                ]))

            st.plotly_chart(fig_oav, use_container_width=True)

        no_thresh = s.get('compounds_without_threshold', [])
        if no_thresh:
            st.caption(f"⚠️ {len(no_thresh)} compounds missing odor thresholds")

    st.divider()

    # --- ROVA Section ---
    if st.button("📊 Calculate ROVA (Relative Odor Activity Values)", type="primary"):
        if st.session_state.agent:
            with st.spinner("Computing ROVA..."):
                r = json.loads(st.session_state.agent._calculate_rova())
                st.session_state.rova_result = r
                _save_working_session()
        else:
            from flavor_tools import calculate_rova, get_rova_summary
            s2 = get_rova_summary(df)
            st.session_state.rova_result = {'rova_summary': s2}
            _save_working_session()

    if st.session_state.rova_result:
        s = st.session_state.rova_result['rova_summary']

        rova_top = s['top_rova_overall'][:12]
        is_zh = get_lang() == 'zh'

        if rova_top:
            st.markdown("#### " + ('Relative Odor Activity (ROVA) — Aroma Dominance', '相对气味活性 (ROVA) — 香气贡献度')[is_zh])

            if s.get('dominance_note'):
                st.info(f"💡 {s['dominance_note']}")

            # ROVA bar + cumulative line chart
            names_rov = [x['compound'] for x in reversed(rova_top)]
            pcts_rov = [x['mean_rova_pct'] for x in reversed(rova_top)]
            cums_rov = [x['cumulative_pct'] for x in reversed(rova_top)]
            doms_rov = [x['dominance'] for x in reversed(rova_top)]
            dom_colors = {'overwhelming': '#f87171','major': '#fbbf24',
                          'significant': '#7dd3fc','minor': '#64748b'}
            cols_rov = [dom_colors.get(d, '#64748b') for d in doms_rov]

            fig_rova = go.Figure()
            fig_rova.add_trace(go.Bar(
                x=pcts_rov, y=names_rov, orientation='h',
                marker=dict(color=cols_rov, line=dict(width=0)),
                text=[f'{v:.1f}%' for v in pcts_rov],
                textposition='outside', textfont=dict(size=11, color='#94a3b8'),
                hovertemplate='<b>%{y}</b><br>ROVA: %{x:.1f}%<br>' +
                              ('Cumulative: %{customdata:.1f}%' if not is_zh else '累计: %{customdata:.1f}%') +
                              '<extra></extra>',
                customdata=cums_rov,
                name='ROVA %'
            ))
            fig_rova.add_trace(go.Scatter(
                x=[cums_rov[-1-i] for i in range(len(cums_rov))],
                y=names_rov,
                mode='lines+markers',
                line=dict(color='#fbbf24', width=1.5, dash='dot'),
                marker=dict(size=5, color='#fbbf24'),
                name=('累计' if is_zh else 'Cumulative'),
                hovertemplate=('累计: %{x:.1f}%' if is_zh else 'Cumul: %{x:.1f}%') + '<extra></extra>'
            ))
            fig_rova.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=10, r=70, t=10, b=10), height=400,
                xaxis=dict(title='ROVA %' if not is_zh else 'ROVA % (相对贡献)', color='#94a3b8',
                           gridcolor='rgba(255,255,255,0.04)', zeroline=True, zerolinecolor='rgba(255,255,255,0.06)'),
                yaxis=dict(color='#94a3b8', automargin=True, tickfont=dict(size=11)),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                            font=dict(color='#94a3b8', size=10)),
                dragmode=False
            )
            st.plotly_chart(fig_rova, use_container_width=True)
            st.caption('  '.join([
                '<span style="color:#f87171">● overwhelming</span>',
                '<span style="color:#fbbf24">● major</span>',
                '<span style="color:#7dd3fc">● significant</span>',
                '<span style="color:#64748b">● minor</span>'
            ]))

        dist = s.get('rova_distribution', {})
        if dist:
            st.caption(("📈 Distribution: " if not is_zh else "📈 分布: ") + " | ".join(
                f"{k}: {v}" for k, v in dist.items()))

    st.divider()

    # === Flavor Dimension Radar Chart ===
    st.markdown("#### 🎯 " + ('Flavor Dimension Radar', '风味维度雷达图')[get_lang() == 'zh'])
    st.caption(
        ('8 aroma dimensions scored by log(OAV) of detected compounds. Higher = stronger contribution to that aroma category.',
         '8 个风味维度基于 log(OAV) 评分，分数越高表示该类香气贡献越大。')[get_lang() == 'zh']
    )
    if st.button("🛞 " + ('Generate Flavor Radar', '生成风味雷达图')[get_lang() == 'zh'],
                 type="primary", use_container_width=True):
        with st.spinner("Computing flavor dimensions..."):
            try:
                from flavor_tools import calculate_oav, ODOR_THRESHOLDS

                ODOR_CATEGORIES = {
                    ('Green/Grassy', '青香/草香'): ['hexanal', 'heptanal', 'octanal', 'nonanal', 'decanal',
                                     '2-heptenal', '2-octenal', '2-nonenal', 'citronellal', 'hexanol', '2-hexenal'],
                    ('Fruity/Sweet', '果香/甜香'): ['ethyl acetate', 'isoamyl acetate', 'ethyl butyrate',
                                     'ethyl hexanoate', 'ethyl octanoate', 'benzaldehyde',
                                     'vanillin', 'beta-ionone', 'linalool', 'geraniol', 'maltol', 'furaneol'],
                    ('Roasted/Nutty', '烤香/坚果'): ['2-methylpyrazine', '2,5-dimethylpyrazine',
                                      '2,6-dimethylpyrazine', '2,3,5-trimethylpyrazine',
                                      'furfural', 'furfuryl alcohol', 'pyrrole', '2-acetylpyrrole'],
                    ('Fatty/Rancid', '油脂/酸败'): ['2,4-decadienal', 'butyric acid', 'hexanoic acid',
                                     'octanoic acid', 'isovaleric acid', 'heptanoic acid'],
                    ('Earthy/Musty', '土味/霉味'): ['geosmin', '2-methylisoborneol', '1-octen-3-ol',
                                     '2-pentylfuran', 'indole', 'skatole'],
                    ('Floral/Spicy', '花香/辛香'): ['alpha-pinene', 'limonene', 'caryophyllene', 'eugenol',
                                     'phenylethyl alcohol', 'alpha-terpineol', 'thymol', 'linalool oxide'],
                    ('Sulfurous', '含硫化合物'): ['dimethyl sulfide', 'dimethyl disulfide', 'dimethyl trisulfide',
                                  'methional', 'furfurylthiol', '3-methylthiopropanal'],
                    ('Fermented/Dairy', '发酵/乳制品'): ['acetoin', '2,3-butanedione', '2,3-pentanedione',
                                  'acetic acid', '3-methylbutanal', '2-methylbutanal'],
                }

                df_oav = calculate_oav(df)
                is_zh = get_lang() == 'zh'
                cat_scores = {}
                cat_labels = {}
                for (en_label, zh_label), compounds in ODOR_CATEGORIES.items():
                    score = 0.0
                    for comp in compounds:
                        mask = df_oav['compound'].str.lower().str.strip() == comp
                        if mask.any():
                            score += float(df_oav.loc[mask, 'log_oav'].mean())
                    cat_scores[en_label] = max(score, 0.01)
                    cat_labels[en_label] = zh_label if is_zh else en_label

                cats = list(cat_scores.keys())
                vals = [cat_scores[c] for c in cats]
                display_labels = [cat_labels[c] for c in cats]

                fig_radar = go.Figure()
                fig_radar.add_trace(go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=display_labels + [display_labels[0]],
                    fill='toself',
                    fillcolor='rgba(125,211,252,0.12)',
                    line=dict(color='#7dd3fc', width=2.5),
                    marker=dict(color='#7dd3fc', size=7, symbol='circle'),
                    name=('Flavor Profile' if not is_zh else '风味谱图'),
                    hovertemplate='<b>%{theta}</b><br>Score: %{r:.2f}<extra></extra>'
                ))
                max_val = max(vals) if vals else 1.0
                fig_radar.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    polar=dict(
                        radialaxis=dict(
                            visible=True, color='#64748b',
                            gridcolor='rgba(255,255,255,0.05)',
                            linecolor='rgba(255,255,255,0.08)',
                            tickfont=dict(size=9),
                            range=[0, max_val * 1.25],
                            ticksuffix=''
                        ),
                        angularaxis=dict(
                            color='#e8ecf1', gridcolor='rgba(255,255,255,0.05)',
                            tickfont=dict(size=12, family='PingFang SC,Microsoft YaHei,sans-serif'),
                            linecolor='rgba(255,255,255,0.08)'
                        ),
                        bgcolor='rgba(0,0,0,0)'
                    ),
                    height=520, margin=dict(l=60, r=60, t=30, b=30),
                    showlegend=False
                )
                st.plotly_chart(fig_radar, use_container_width=True)

                # Score card
                score_df = pd.DataFrame({
                    ('Dimension' if not is_zh else '维度'): display_labels,
                    ('Score' if not is_zh else 'log(OAV) 得分'): [f'{v:.2f}' for v in vals],
                    ('Rank' if not is_zh else '排名'): list(range(1, len(vals)+1))
                }).sort_values(('Score' if not is_zh else 'log(OAV) 得分'), ascending=False)

                # Simple bar chart for dimension scores alongside radar
                col_r1, col_r2 = st.columns([3, 2])
                with col_r1:
                    st.caption('##### ' + ('Dimension Scores', '维度得分排名')[is_zh])
                    score_sorted = score_df.copy()
                    dim_bars = go.Figure()
                    sorted_labels = [cat_labels[c] for c in cats]
                    sorted_vals_raw = [cat_scores[c] for c in cats]
                    # Sort by value descending
                    paired = sorted(zip(sorted_vals_raw, sorted_labels), reverse=True)
                    s_vals, s_labels = zip(*paired) if paired else ([], [])

                    dim_bars.add_trace(go.Bar(
                        x=list(s_vals), y=list(s_labels), orientation='h',
                        marker=dict(
                            color=list(s_vals),
                            colorscale=[[0, '#64748b'], [1, '#7dd3fc']],
                            showscale=False,
                            line=dict(width=0)
                        ),
                        text=[f'{v:.1f}' for v in s_vals],
                        textposition='outside', textfont=dict(size=11, color='#94a3b8'),
                        hovertemplate='<b>%{y}</b>: %{x:.2f}<extra></extra>'
                    ))
                    dim_bars.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=10, r=60, t=5, b=5), height=320,
                        xaxis=dict(color='#94a3b8', gridcolor='rgba(255,255,255,0.03)',
                                   title='log(OAV)' if not is_zh else 'log(OAV) 得分'),
                        yaxis=dict(color='#94a3b8', automargin=True, tickfont=dict(size=11)),
                        showlegend=False, dragmode=False
                    )
                    st.plotly_chart(dim_bars, use_container_width=True)

                with col_r2:
                    st.dataframe(score_df, use_container_width=True, hide_index=True,
                                 height=320)

                _save_working_session()

            except Exception as e:
                st.error(f"Radar generation failed: {e}")

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🛞 Flavor Wheel (PNG)", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Generating..."):
                    r = json.loads(st.session_state.agent._flavor_wheel())
                    wheel_path = 'output/agent_results/plots/flavor_wheel.png'
                    if os.path.exists(wheel_path):
                        st.image(wheel_path, use_container_width=True)
    with c2:
        if st.button("⚠️ Off-Flavor Check", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Checking..."):
                    r = json.loads(st.session_state.agent._off_flavor_check())
                    if r.get('off_flavors_detected'):
                        st.dataframe(pd.DataFrame(r['off_flavors_detected']), use_container_width=True)
    with c3:
        if st.button("🔬 Tag Pathways", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Tagging..."):
                    r = json.loads(st.session_state.agent._tag_pathways())
                    st.json(r.get('pathway_counts', {}))


# Tab 4: Statistics
# ================================================================
with tab_stats:
    st.markdown("### 📐 Statistical Analysis")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📊 ANOVA + Post-Hoc", use_container_width=True, type="primary"):
            if st.session_state.agent:
                with st.spinner("Running ANOVA..."):
                    r = json.loads(st.session_state.agent._run_anova(alpha=0.05))
                    st.session_state.anova_result = r
                    _save_working_session()
    with c2:
        if st.button("🎯 PLS-DA + VIP", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Running PLS-DA..."):
                    r = json.loads(st.session_state.agent._run_plsda())
                    st.session_state.plsda_result = r
                    _save_working_session()
    with c3:
        if st.button("🌲 Random Forest", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Training RF..."):
                    r = json.loads(st.session_state.agent._run_random_forest(n_estimators=50))
                    st.session_state.rf_result = r
                    _save_working_session()

    # ANOVA results
    if st.session_state.anova_result:
        ar = st.session_state.anova_result
        st.metric("Significant Compounds", f"{ar['n_significant']} / {ar['n_tested']}")
        if ar['significant_compounds']:
            st.markdown("**Significant compounds:** " + ", ".join(ar['significant_compounds'][:15]))
        if ar.get('posthoc_results'):
            for comp, comps in list(ar['posthoc_results'].items())[:5]:
                st.markdown(f"**{comp}**")
                for c in comps:
                    sig = "✅" if c['significant'] else ""
                    st.caption(f"  {c['groups']}: diff={c['mean_diff']:.4f} FC={c['fold_change']:.2f} {sig}")

    # PLS-DA results
    if st.session_state.plsda_result:
        pr = st.session_state.plsda_result
        st.metric("PLS-DA R²", f"{pr['r2']:.3f}")
        st.markdown(f"**{pr['n_key_compounds']} key discriminating compounds (VIP≥1.0)**")
        vip_df = pd.DataFrame(pr['key_compounds'][:10])
        st.dataframe(vip_df[['compound', 'vip_score']], use_container_width=True, hide_index=True)
        plsda_path = 'output/agent_results/plots/plsda.png'
        if os.path.exists(plsda_path):
            st.image(plsda_path, use_container_width=True)

    # RF results
    if st.session_state.rf_result:
        rr = st.session_state.rf_result
        st.metric("RF CV Accuracy", f"{rr['cv_accuracy']:.1%}")
        st.markdown(f"**Top marker: {rr['top_features'][0]['compound']}**")
        rf_path = 'output/agent_results/plots/rf_importance.png'
        if os.path.exists(rf_path):
            st.image(rf_path, use_container_width=True)

# ================================================================
# Tab 5: GC-MS Interactive View
# ================================================================
with tab_viz:
    st.markdown("### 🔬 Interactive GC-MS Visualization")

    if st.session_state.data_loaded:
        df = st.session_state.df

        # Build TIC from data if available
        has_tic_data = False
        if 'rt' in df.columns and 'area' in df.columns:
            has_tic_data = True
            rt_vals = sorted(df['rt'].dropna().unique())
            # Aggregate intensities by RT
            tic_df = df.groupby('rt')['area'].sum().reset_index()
            times = tic_df['rt'].values
            intensities = tic_df['area'].values

        if has_tic_data:
            from tools.interactive_viz import TICPlot, MirrorPlot, GCDashboard
            from tools.advanced_peak_detection import PeakDetector

            viz_col1, viz_col2 = st.columns([3, 1])

            with viz_col1:
                st.markdown("#### TIC Chromatogram")

                # Run advanced peak detection
                if st.button("🔍 Detect Peaks (CWT)", use_container_width=True, key="cwt_detect"):
                    with st.spinner("Running CWT peak detection..."):
                        detector = PeakDetector(snr_threshold=5.0)
                        result = detector.process_chromatogram(times, intensities)
                        st.session_state.peak_result = result
                        st.success(f"Found {result['summary']['n_major']} major + "
                                  f"{result['summary']['n_minor']} minor peaks "
                                  f"({result['summary']['n_shoulders']} shoulders)")

                if st.session_state.get('peak_result'):
                    peaks = st.session_state.peak_result['peaks']
                    # Annotate identified peaks
                    for p in peaks:
                        peak_rt = p['rt']
                        # Find closest compound match
                        matches = df[abs(df['rt'] - peak_rt) < 0.1]
                        if len(matches) > 0:
                            identified = matches[matches['compound'].notna()]
                            if len(identified) > 0:
                                p['compound'] = str(identified['compound'].iloc[0])

                    tic_fig = TICPlot.create(
                        times, intensities, peaks,
                        title=f'TIC — {st.session_state.data_dir}'
                    )
                    st.plotly_chart(tic_fig, use_container_width=True)

                    # Peak table
                    st.markdown("**Detected Peaks**")
                    peak_data = []
                    for p in peaks:
                        if p.get('snr', 0) >= 5:
                            peak_data.append({
                                'RT (min)': f"{p['rt']:.3f}",
                                'Height': f"{p['height']:.0f}",
                                'SNR': f"{p['snr']:.1f}",
                                'Width (pts)': f"{p['width']:.0f}",
                                'Asym': f"{p.get('asymmetry', 1):.2f}" if p.get('asymmetry') else '-',
                                'Compound': p.get('compound', '-'),
                            })
                    if peak_data:
                        st.dataframe(pd.DataFrame(peak_data), use_container_width=True, hide_index=True)
                else:
                    # Simple TIC without peak detection
                    simple_fig = TICPlot.create(times, intensities, title='TIC Chromatogram')
                    st.plotly_chart(simple_fig, use_container_width=True)

            with viz_col2:
                st.markdown("#### Spectrum Viewer")
                # Compound selector for mirror plot
                compounds = sorted(df['compound'].dropna().unique())
                compounds = [c for c in compounds if str(c) != 'nan' and not str(c).startswith('RT_')]
                selected_compound = st.selectbox("Compound", compounds[:50] if compounds else ['None'])

                if selected_compound and selected_compound != 'None':
                    if st.button("🔬 Show Mirror Plot", use_container_width=True):
                        cdf = df[df['compound'] == selected_compound].iloc[0]
                        # Get mass spectrum if available
                        from spectral_match import get_compound_spectrum
                        try:
                            from mass_spectra_reader import MassSpectraReader
                            agent = st.session_state.agent
                            if agent and hasattr(agent, 'd_folders'):
                                spec_data = None
                                for d in agent.d_folders.get('ready', []):
                                    ms_file = Path(d['path']) / 'data.ms'
                                    if ms_file.exists():
                                        try:
                                            from aston.tracefile.agilent_ms import AgilentMS
                                            tf = AgilentMS(str(ms_file))
                                            rt = cdf['rt']
                                            spec = tf.spectrum_at_time(rt * 60)
                                            observed = [(mz, int(i)) for mz, i
                                                       in zip(spec.mz, spec.intensity) if i > 0]
                                            if observed:
                                                mirror_fig = MirrorPlot.create(
                                                    observed[:80],
                                                    compound_name=selected_compound,
                                                    sample_name=str(cdf.get('sample', '')),
                                                )
                                                st.plotly_chart(mirror_fig, use_container_width=True)
                                                break
                                        except Exception:
                                            pass
                            else:
                                st.info("Mass spectrum data not available for this sample.")
                        except ImportError:
                            st.info("Aston library required for spectrum extraction.")
                else:
                    st.caption("Select a compound to view its spectrum")

            # EIC viewer
            st.divider()
            st.markdown("#### Extracted Ion Chromatograms (EIC)")
            mz_input = st.text_input("m/z values (comma-separated)", "43, 57, 71",
                                     help="Enter m/z values to overlay their ion chromatograms")
            if mz_input:
                try:
                    mz_list = [int(x.strip()) for x in mz_input.split(',')]
                    from tools.interactive_viz import EICPlot
                    # Generate sample EICs from data
                    eic_dict = {}
                    for mz in mz_list:
                        if 'rt' in df.columns:
                            eic_values = np.zeros_like(times)
                            for i, rt in enumerate(times):
                                nearby = df[(abs(df['rt'] - rt) < 0.2)]
                                if len(nearby) > 0:
                                    eic_values[i] = nearby['area'].mean()
                            eic_dict[str(mz)] = eic_values
                    eic_fig = EICPlot.create(times, eic_dict)
                    st.plotly_chart(eic_fig, use_container_width=True)
                except ValueError:
                    st.warning("Please enter valid m/z values")
        else:
            st.info("Load data with RT and Area columns to enable interactive visualization")
    else:
        st.info("Load data from the sidebar to start")

# ================================================================
# Tab 6: Export
# ================================================================
with tab_export:
    st.markdown("### 📥 Export Results")

    # One-click comprehensive report
    if st.button("🚀 Generate Full Analysis Report", type="primary", use_container_width=True):
        with st.spinner("Running comprehensive analysis..."):
            try:
                from tools.comprehensive_report import generate_report
                report_path = generate_report(st.session_state.df, title='GC-MS Comprehensive Analysis Report')
                st.success(f"✅ Report generated!")
                with open(report_path, 'r', encoding='utf-8') as f:
                    st.download_button(
                        "📥 Download Full Report (HTML)",
                        f.read(),
                        file_name=report_path.name,
                        mime="text/html",
                        use_container_width=True
                    )
            except Exception as e:
                st.error(f"Report generation failed: {e}")

    st.divider()

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🌐 Interactive HTML Report", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Generating HTML..."):
                    r = json.loads(st.session_state.agent._html_report())
                    if r['status'] == 'done' and os.path.exists(r['file']):
                        with open(r['file'], 'r', encoding='utf-8') as f:
                            st.download_button("Download HTML Report", f.read(),
                                             "gcms_report.html", "text/html")
    with c2:
        if st.button("📝 Word Tables (三线表)", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Generating Word..."):
                    r = json.loads(st.session_state.agent._word_tables())
                    if r['status'] == 'done' and os.path.exists(r['file']):
                        with open(r['file'], 'rb') as f:
                            st.download_button("Download Word Tables", f.read(),
                                             "gcms_tables.docx")
    with c3:
        if st.button("📊 Excel Export", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Exporting Excel..."):
                    r = json.loads(st.session_state.agent._export_report(format='excel'))
                    xlsx_path = Path('output/agent_results') / 'analysis_report.xlsx'
                    if xlsx_path.exists():
                        with open(xlsx_path, 'rb') as f:
                            st.download_button("Download Excel", f.read(),
                                             "gcms_analysis.xlsx")

# ================================================================
# Tab 7: AI Analysis — Natural Language Data Analysis
# ================================================================
with tab_ai:
    st.markdown("### 🤖 " + ('AI Analysis', 'AI 智能分析')[get_lang() == 'zh'])
    st.caption(
        ('Ask questions about your data in natural language. The AI can run statistics, generate plots, identify compounds, and more.',
         '用自然语言向 AI 提问，自动运行统计分析、生成图表、鉴定化合物等。')[get_lang() == 'zh']
    )

    if not st.session_state.data_loaded:
        st.info(('👈 Load data from the sidebar first, then come back here.',
                 '👈 请先从侧边栏加载数据，再回到这里。')[get_lang() == 'zh'])
    elif not os.environ.get("DEEPSEEK_API_KEY"):
        st.warning(('⚠️ Set your DeepSeek API Key in the sidebar first.',
                     '⚠️ 请先在侧边栏设置 DeepSeek API 密钥。')[get_lang() == 'zh'])
    else:
        # Init chat history
        if 'chat_history' not in st.session_state:
            st.session_state.chat_history = []
        if 'chat_ready' not in st.session_state:
            st.session_state.chat_ready = False

        # Ensure agent is ready
        if not st.session_state.chat_ready or st.session_state.agent is None:
            if st.button('🚀 ' + ('Start AI Analysis Session', '启动 AI 分析会话')[get_lang() == 'zh'],
                         type='primary', use_container_width=True):
                with st.spinner(('Initializing AI agent...', '正在初始化 AI 智能体...')[get_lang() == 'zh']):
                    try:
                        if st.session_state.agent is None:
                            from gcms_agent import GCMSAgent
                            st.session_state.agent = GCMSAgent(
                                data_dir=st.session_state.get('data_dir', ''),
                                api_key=os.environ.get("DEEPSEEK_API_KEY")
                            )
                        _inject_nist_to_agent(st.session_state)
                        st.session_state.agent.df = st.session_state.df
                        st.session_state.chat_ready = True
                        st.session_state.chat_history = []
                        st.success('✅ ' + ('Agent ready! You can now ask questions.',
                                            '智能体就绪！现在可以提问了。')[get_lang() == 'zh'])
                        st.rerun()
                    except Exception as e:
                        st.error(f"{'Failed to init agent: ' if get_lang()=='en' else '初始化失败：'}{e}")

        # Quick analysis buttons
        quick_zh = [
            ('📊 数据总览', '帮我总结一下当前数据集的基本特征和关键指标'),
            ('🔬 差异分析', '找出组间差异最显著的化合物，并解释它们的化学意义'),
            ('👃 风味评估', '分析当前数据中的关键风味化合物，计算OAV并给出感官描述'),
            ('📈 统计报告', '运行ANOVA和PLS-DA，给我一份完整的统计分析报告'),
            ('🧪 鉴定未知峰', '搜索公共谱库，尝试鉴定当前数据中尚未识别的色谱峰'),
        ]
        quick_en = [
            ('📊 Data Overview', 'Summarize the key characteristics and metrics of the current dataset'),
            ('🔬 Differential Analysis', 'Find the most significantly different compounds between groups and explain their chemical significance'),
            ('👃 Flavor Assessment', 'Analyze key flavor compounds, calculate OAV and provide sensory descriptions'),
            ('📈 Statistical Report', 'Run ANOVA and PLS-DA, give me a complete statistical analysis report'),
            ('🧪 Identify Unknowns', 'Search public libraries to identify currently unidentified chromatographic peaks'),
        ]
        quicks = quick_zh if get_lang() == 'zh' else quick_en

        if st.session_state.chat_ready and len(st.session_state.chat_history) == 0:
            st.markdown("##### ⚡ " + ('Quick Analysis', '快速分析')[get_lang() == 'zh'])
            cols = st.columns(len(quicks))
            for i, (label, prompt) in enumerate(quicks):
                with cols[i]:
                    if st.button(label, key=f"quick_{i}", use_container_width=True,
                                 help=prompt):
                        st.session_state.pending_prompt = prompt
                        st.rerun()

        # Chat interface
        if st.session_state.chat_ready:
            # Display chat history
            for msg in st.session_state.chat_history:
                with st.chat_message(msg['role']):
                    st.markdown(msg['content'])
                    if msg.get('tool_calls'):
                        with st.expander('🔧 ' + ('Tool calls', '工具调用')[get_lang() == 'zh'],
                                         expanded=False):
                            for tc in msg['tool_calls']:
                                st.caption(f"`{tc['name']}` — {tc.get('summary', '')}")

            # Handle pending prompt
            if st.session_state.get('pending_prompt'):
                prompt = st.session_state.pending_prompt
                st.session_state.pending_prompt = None

                with st.chat_message('user'):
                    st.markdown(prompt)
                st.session_state.chat_history.append({'role': 'user', 'content': prompt})

                with st.chat_message('assistant'):
                    with st.spinner('🧠 ' + ('Analyzing...', '正在分析...')[get_lang() == 'zh']):
                        try:
                            agent = st.session_state.agent
                            result = agent.chat(prompt)

                            # Extract final answer
                            if hasattr(agent, 'messages') and agent.messages:
                                last = agent.messages[-1]
                                if last['role'] == 'assistant':
                                    answer = last.get('content', '')
                                    if answer:
                                        st.markdown(answer)
                                        st.session_state.chat_history.append({
                                            'role': 'assistant', 'content': answer
                                        })
                                        _save_working_session()
                                    else:
                                        st.markdown(result[:2000] if isinstance(result, str) else str(result))
                                        st.session_state.chat_history.append({
                                            'role': 'assistant', 'content': result[:2000]
                                        })
                                    _save_working_session()
                                else:
                                    st.info(('Analysis complete. Check the results in other tabs.',
                                             '分析完成，请在其他标签页查看结果。')[get_lang() == 'zh'])
                            else:
                                st.info(('Done. Check results in other tabs.',
                                         '完成，请在其他标签页查看结果。')[get_lang() == 'zh'])
                        except Exception as e:
                            err_msg = str(e)
                            st.error(f"❌ {err_msg[:300]}")
                            st.session_state.chat_history.append({
                                'role': 'assistant',
                                'content': f'❌ Error: {err_msg[:300]}'
                            })
                st.rerun()

            # Chat input
            chat_input = st.chat_input(
                ('Ask about your GC-MS data... e.g. "Find the top 10 most abundant compounds"',
                 '输入分析问题… 例如："找出丰度最高的10个化合物"')[get_lang() == 'zh']
            )
            if chat_input:
                st.session_state.pending_prompt = chat_input
                st.rerun()

            # Clear button
            if st.session_state.chat_history:
                st.divider()
                if st.button('🗑️ ' + ('Clear Conversation', '清空对话')[get_lang() == 'zh']):
                    st.session_state.chat_history = []
                    if st.session_state.agent and hasattr(st.session_state.agent, 'messages'):
                        st.session_state.agent.messages = []
                    st.rerun()

# ---- Footer ----
st.divider()
st.markdown(f"""
<div class="gcms-footer">
    <strong>GC-MS AI Analyzer</strong> v3.3.0 · {datetime.now().year} · MIT Open Source<br>
    <span style="font-size:0.75rem;">Library: 29,452 spectra · RI: 2,167 · MoNA API: 1M+ · OAV/ROVA DB: 120+ compounds</span>
</div>
""", unsafe_allow_html=True)
