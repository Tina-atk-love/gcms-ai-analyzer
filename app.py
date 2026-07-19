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

# ---- CSS ----
st.markdown("""
<style>
    .main-header { font-size: 2rem; font-weight: bold; color: #1a5276; margin-bottom: 0; }
    .sub-header { font-size: 0.9rem; color: #666; margin-top: 0; }
    .metric-card { background: #f8f9fa; border-radius: 10px; padding: 15px; text-align: center; }
    .metric-value { font-size: 1.8rem; font-weight: bold; color: #1a5276; }
    .metric-label { font-size: 0.8rem; color: #666; }
    .oav-dominant { color: #c0392b; font-weight: bold; }
    .oav-significant { color: #e67e22; font-weight: bold; }
    .oav-contributing { color: #2980b9; }
    .rova-overwhelming { color: #c0392b; font-weight: bold; font-size: 1.1em; }
    .rova-major { color: #e67e22; font-weight: bold; }
    .rova-significant { color: #2980b9; }
    .feature-icon { font-size: 2rem; }
    .card { background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 12px; padding: 20px; border: 1px solid #dee2e6; height: 100%; }
    .card h4 { color: #1a5276; margin-top: 0.5rem; margin-bottom: 0.3rem; font-size: 1rem; }
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
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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
    nist_mode_idx = st.radio(
        t('sidebar_nist_format'),
        range(len(_nm_keys)),
        format_func=lambda i: _nm_labels[i],
        index=0,
        help=".L Folder = your NIST17.L directory. JCAMP = pre-exported spectra files."
    )
    nist_mode = _nm_keys[nist_mode_idx]

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
        # JCAMP: two sub-options
        jcamp_submode = st.radio("JCAMP source:", ["Exported JCAMP folder (with subdirs)", "Single JCAMP/MSP directory"],
                                 help="'Exported' = output from tools/nist_export. 'Single' = flat directory of .jdx/.msp files.")

        if jcamp_submode == "Exported JCAMP folder (with subdirs)":
            jcamp_export_path = st.text_input("Exported JCAMP path", value="",
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
                    except Exception as e:
                        st.error(f"Failed: {e}")
            if st.session_state.get('nist_spectra_loaded'):
                st.caption(f"Spectra: {len(st.session_state.nist_spec_index.spectra):,} indexed")
        else:
            st.caption("Point to your licensed NIST JCAMP/MSP files. Spectra stay on your machine.")
            nist_path = st.text_input("NIST library path", value="", placeholder="D:\\NIST_JCAMP",
                                      help="Directory containing .jdx/.msp files exported from NIST MS Search")
            if nist_path and st.button("Index NIST Library", use_container_width=True):
                if st.session_state.agent:
                    with st.spinner(f"Scanning {nist_path}..."):
                        r = json.loads(st.session_state.agent._set_nist_path(nist_path))
                        if 'error' not in r:
                            st.info(f"Found {r.get('total_files',0)} files")
                            r2 = json.loads(st.session_state.agent._load_nist_library())
                            st.success(f"Indexed {r2.get('nist_entries',0)} NIST spectra ({r2.get('with_ri',0)} with RI)")
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
    # Hero section
    st.markdown(f"""
    <div style="text-align:center; padding: 1rem 0 2rem 0;">
        <h1 style="color:#1a5276; font-size:2.5rem; margin-bottom:0.5rem;">{t('welcome_title')}</h1>
        <p style="color:#666; font-size:1.1rem;">{t('welcome_subtitle')}</p>
    </div>
    """, unsafe_allow_html=True)

    # Feature cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div class="feature-icon">🧬</div>
            <h4>{t('feature1_title')}</h4>
            <p style="font-size:0.85rem;color:#666;">{t('feature1_desc')}</p>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div class="feature-icon">🔍</div>
            <h4>{t('feature2_title')}</h4>
            <p style="font-size:0.85rem;color:#666;">{t('feature2_desc')}</p>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div class="feature-icon">👃</div>
            <h4>{t('feature3_title')}</h4>
            <p style="font-size:0.85rem;color:#666;">{t('feature3_desc')}</p>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="card" style="text-align:center;">
            <div class="feature-icon">🤖</div>
            <h4>{t('feature4_title')}</h4>
            <p style="font-size:0.85rem;color:#666;">{t('feature4_desc')}</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Demo button
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
                st.session_state.compounds = df['compound'].unique().tolist()
                st.session_state.groups = df['group'].unique().tolist()
            st.rerun()

    st.markdown(f"""
    <div style="text-align:center; color:#999; margin-top:0.5rem;">
        <small>{t('demo_or_load')}</small>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.markdown(f"""
    <div style="display:flex; justify-content:center; gap:2rem; text-align:center; color:#666; font-size:0.9rem;">
        <div>{t('stat_tools')}</div>
        <div>{t('stat_library')}</div>
        <div>{t('stat_interface')}</div>
        <div>{t('stat_license')}</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ---- Tabs ----
df = st.session_state.df
tab_data, tab_plots, tab_flavor, tab_stats, tab_viz, tab_export = st.tabs(
    [t('tab_data'), t('tab_plots'), t('tab_flavor'), t('tab_stats'), t('tab_viz'), t('tab_export')]
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

    # Filters
    st.divider()
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        min_area = st.number_input(t('filter_min_area'), value=10000, step=1000)
    with fc2:
        if 'match_factor' in df.columns:
            min_match = st.slider(t('filter_min_match'), 0, 100, 0)
        else:
            min_match = 0
    with fc3:
        excl_unid = st.checkbox(t('filter_excl_unid'), True)
    with fc4:
        excl_cont = st.checkbox(t('filter_excl_cont'), True)

    # Apply filters
    filtered = df.copy()
    if min_area > 0:
        filtered = filtered[filtered['area'] >= min_area]
    if min_match > 0 and 'match_factor' in filtered.columns:
        filtered = filtered[filtered['match_factor'].isna() | (filtered['match_factor'] >= min_match)]
    if excl_unid:
        filtered = filtered[~filtered['compound'].str.startswith('RT_', na=False)]
    if excl_cont:
        cont = ['siloxane', 'phthalate', 'column bleed', 'exclude']
        filtered = filtered[~filtered['compound'].str.lower().str.contains('|'.join(cont), na=False)]

    st.markdown(f"**Filtered: {len(filtered)} records, {filtered['compound'].nunique()} compounds, {filtered['sample'].nunique()} samples**")

    # Data table
    st.dataframe(
        filtered[['sample', 'group', 'compound', 'rt', 'area']].head(200),
        use_container_width=True, height=400,
        column_config={
            'rt': st.column_config.NumberColumn('RT (min)', format='%.3f'),
            'area': st.column_config.NumberColumn('Area', format='%.0f'),
        }
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
            st.error("Agent not initialized. Load data first.")
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
                except Exception as e:
                    st.error(f"Error: {e}")

    # Display generated plots
    plot_dir = Path("output/agent_results/plots")
    if plot_dir.exists():
        images = sorted(plot_dir.glob("*.png"))
        if images:
            st.divider()
            cols = st.columns(2)
            for i, img_path in enumerate(images[-8:]):
                with cols[i % 2]:
                    st.image(str(img_path), caption=img_path.name, use_container_width=True)

            # Download all
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
        else:
            from flavor_tools import calculate_oav, get_oav_summary
            s = get_oav_summary(df)
            st.session_state.oav_result = {'oav_summary': s}

    if st.session_state.oav_result:
        s = st.session_state.oav_result['oav_summary']
        st.markdown("#### Top Aroma-Impact Compounds")
        oav_data = []
        for x in s['top_oav_overall'][:15]:
            color = '🟢' if x['impact'] == 'negligible' else '🟡' if x['impact'] == 'contributing' \
                    else '🟠' if x['impact'] == 'significant' else '🔴'
            oav_data.append({'Rank': len(oav_data)+1, 'Compound': x['compound'],
                           'OAV': f"{x['mean_oav']:.1f}", 'Impact': f"{color} {x['impact']}"})
        st.dataframe(pd.DataFrame(oav_data), use_container_width=True, hide_index=True)
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
        else:
            from flavor_tools import calculate_rova, get_rova_summary
            s = get_rova_summary(df)
            st.session_state.rova_result = {'rova_summary': s}

    if st.session_state.rova_result:
        s = st.session_state.rova_result['rova_summary']
        st.markdown("#### Top Aroma-Dominating Compounds (by ROVA %)")

        # Dominance note
        if s.get('dominance_note'):
            st.info(f"💡 {s['dominance_note']}")

        rova_data = []
        for x in s['top_rova_overall'][:15]:
            if x['dominance'] == 'overwhelming':
                color, icon = '#c0392b', '🔴'
            elif x['dominance'] == 'major':
                color, icon = '#e67e22', '🟠'
            elif x['dominance'] == 'significant':
                color, icon = '#2980b9', '🔵'
            elif x['dominance'] == 'minor':
                color, icon = '#7f8c8d', '⚪'
            else:
                color, icon = '#bdc3c7', '·'
            rova_data.append({
                'Rank': len(rova_data) + 1,
                'Compound': x['compound'],
                'ROVA %': f"{x['mean_rova_pct']:.1f}%",
                'Cumul. %': f"{x['cumulative_pct']:.1f}%",
                'OAV': f"{x['mean_oav']:.1f}",
                'Dominance': f"{icon} {x['dominance']}",
            })
        st.dataframe(pd.DataFrame(rova_data), use_container_width=True, hide_index=True)

        # Distribution bar
        dist = s.get('rova_distribution', {})
        if dist:
            st.caption(f"📈 Dominance distribution: " + " | ".join(
                f"{k}: {v}" for k, v in dist.items()))

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🛞 Flavor Wheel", use_container_width=True):
            if st.session_state.agent:
                with st.spinner():
                    r = json.loads(st.session_state.agent._flavor_wheel())
                    wheel_path = 'output/agent_results/plots/flavor_wheel.png'
                    if os.path.exists(wheel_path):
                        st.image(wheel_path, use_container_width=True)
    with c2:
        if st.button("⚠️ Off-Flavor Check", use_container_width=True):
            if st.session_state.agent:
                with st.spinner():
                    r = json.loads(st.session_state.agent._off_flavor_check())
                    if r.get('off_flavors_detected'):
                        st.dataframe(pd.DataFrame(r['off_flavors_detected']), use_container_width=True)

    if st.button("🔬 Tag Pathways (Maillard / Lipid Oxidation)", use_container_width=True):
        if st.session_state.agent:
            with st.spinner():
                r = json.loads(st.session_state.agent._tag_pathways())
                st.json(r.get('pathway_counts', {}))

# ================================================================
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
    with c2:
        if st.button("🎯 PLS-DA + VIP", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Running PLS-DA..."):
                    r = json.loads(st.session_state.agent._run_plsda())
                    st.session_state.plsda_result = r
    with c3:
        if st.button("🌲 Random Forest", use_container_width=True):
            if st.session_state.agent:
                with st.spinner("Training RF..."):
                    r = json.loads(st.session_state.agent._run_random_forest(n_estimators=50))
                    st.session_state.rf_result = r

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

# ---- Footer ----
st.divider()
st.caption(f"GC-MS AI Analyzer v3.3.0 · {datetime.now().year} · Open Source MIT License")
st.caption(f"Library: 29,452 spectra · RI: 2,167 · MoNA API: 1M+ · OAV/ROVA DB: 120+ compounds")
