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
</style>
""", unsafe_allow_html=True)

# ---- Session State Init ----
for key, default in {
    'agent': None, 'df': None, 'data_loaded': False, 'data_dir': None,
    'profile': None, 'samples': [], 'compounds': [], 'groups': [],
    'oav_result': None, 'anova_result': None, 'plsda_result': None,
    'rf_result': None, 'plots_generated': {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ================================================================
# Sidebar — Configuration
# ================================================================
with st.sidebar:
    st.image("https://img.icons8.com/color/96/test-tube--v1.png", width=50)
    st.markdown("## 🧬 GC-MS AI Analyzer")

    # API Key
    api_key = st.text_input(
        "DeepSeek API Key",
        value=os.environ.get("DEEPSEEK_API_KEY", ""),
        type="password",
        help="Get one at https://platform.deepseek.com"
    )
    if api_key:
        os.environ["DEEPSEEK_API_KEY"] = api_key

    st.divider()

    # Data source
    st.markdown("### 📂 Data Source")
    data_source = st.radio("Load from:", ["Local Directory", "Upload .D ZIP", "Demo Data"])

    if data_source == "Local Directory":
        data_dir = st.text_input("Data path", value="", placeholder="D:\\Tina")
        if st.button("🔄 Load Data", use_container_width=True) and data_dir:
            with st.spinner("Scanning and extracting..."):
                try:
                    from gcms_agent import GCMSAgent
                    st.session_state.agent = GCMSAgent(data_dir=data_dir)
                    r = json.loads(st.session_state.agent._extract_all_data(data_dir))
                    if "error" in r:
                        st.error(r["error"])
                    else:
                        st.session_state.df = st.session_state.agent.df
                        st.session_state.data_loaded = True
                        st.session_state.data_dir = data_dir
                        st.success(f"✅ {r.get('total_records',0)} peaks, {r.get('n_compounds',0)} compounds")
                except Exception as e:
                    st.error(f"Load failed: {e}")

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
                    r = json.loads(st.session_state.agent._extract_all_data(tmpdir))
                    if "error" in r:
                        st.error(r["error"])
                    else:
                        st.session_state.df = st.session_state.agent.df
                        st.session_state.data_loaded = True
                        st.session_state.data_dir = tmpdir
                        st.success(f"✅ {r.get('total_records',0)} peaks loaded")
                except Exception as e:
                    st.error(f"Load failed: {e}")

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
st.markdown('<p class="main-header">🧬 GC-MS AI Analyzer</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Open-Source NIST Alternative · Flavor & Compound Analysis</p>', unsafe_allow_html=True)

if not st.session_state.data_loaded:
    st.info("👈 Load your data from the sidebar to start")
    st.markdown("""
    ### How to use:
    1. **Set your DeepSeek API Key** in the sidebar
    2. **Load data**: type a path, upload a ZIP of .D folders, or try demo data
    3. **Explore**: filter, plot, calculate OAV, run statistics
    4. **Export**: download plots, Word tables, or interactive HTML reports
    """)
    st.stop()

# ---- Tabs ----
df = st.session_state.df
tab_data, tab_plots, tab_flavor, tab_stats, tab_export = st.tabs(
    ["📊 Data", "📈 Plots", "👃 Flavor", "📐 Statistics", "📥 Export"]
)

# ================================================================
# Tab 1: Data Browser
# ================================================================
with tab_data:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Samples", df['sample'].nunique())
    with c2:
        st.metric("Compounds", df['compound'].nunique())
    with c3:
        st.metric("Records", len(df))
    with c4:
        g = df['group'].nunique() if 'group' in df.columns else 1
        st.metric("Groups", g)

    # Filters
    st.divider()
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        min_area = st.number_input("Min Area", value=10000, step=1000)
    with fc2:
        if 'match_factor' in df.columns:
            min_match = st.slider("Min Match", 0, 100, 0)
        else:
            min_match = 0
    with fc3:
        excl_unid = st.checkbox("Exclude Unidentified", True)
    with fc4:
        excl_cont = st.checkbox("Exclude Contaminants", True)

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
# Tab 5: Export
# ================================================================
with tab_export:
    st.markdown("### 📥 Export Results")

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
st.caption(f"Library: 29,452 spectra · RI: 2,167 · MoNA API: 1M+ · OAV DB: 120+ compounds")
