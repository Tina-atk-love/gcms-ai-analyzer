#!/usr/bin/env python3
"""
Internationalization (i18n) Module — 中英文切换
=================================================
All UI text in one place. Add new strings here.

Usage:
  from tools.i18n import t, set_lang, LANG
  set_lang('zh')  # or 'en'
  print(t('load_data'))  # → "加载数据" or "Load Data"
"""

import streamlit as st

# Current language, stored in session state
DEFAULT_LANG = 'en'

# ── All translatable strings ─────────────────────────────────
# Format: { 'key': {'en': 'English', 'zh': '中文'} }
STRINGS = {
    # ── App title / header ──
    'app_title':          {'en': 'GC-MS AI Analyzer', 'zh': 'GC-MS 人工智能分析平台'},
    'app_subtitle':       {'en': 'Open-Source NIST Alternative — AI-Powered Flavor & Compound Analysis',
                           'zh': '开源 NIST 替代方案 — AI 驱动的风味与化合物分析'},
    'app_icon':           {'en': '🧬', 'zh': '🧬'},

    # ── Sidebar ──
    'sidebar_api_key':    {'en': 'DeepSeek API Key', 'zh': 'DeepSeek API 密钥'},
    'sidebar_api_help':   {'en': 'Get one at https://platform.deepseek.com',
                           'zh': '在 https://platform.deepseek.com 获取'},
    'sidebar_nist':       {'en': '🔬 NIST Library (Local)', 'zh': '🔬 NIST 谱库 (本地)'},
    'sidebar_nist_caption': {'en': '⚖️  Your NIST data stays on this computer — nothing is uploaded.',
                              'zh': '⚖️  NIST 数据保留在本机，不会上传。'},
    'sidebar_nist_format': {'en': 'NIST format:', 'zh': 'NIST 格式：'},
    'sidebar_nist_l_opt': {'en': 'NIST .L Folder (Recommended)', 'zh': 'NIST .L 文件夹 (推荐)'},
    'sidebar_nist_jcamp_opt': {'en': 'JCAMP/MSP Files', 'zh': 'JCAMP/MSP 文件'},
    'sidebar_nist_path':  {'en': 'NIST .L folder path', 'zh': 'NIST .L 文件夹路径'},
    'sidebar_nist_placeholder': {'en': 'C:\\Users\\...\\Desktop\\NIST17.L',
                                  'zh': 'C:\\Users\\...\\Desktop\\NIST17.L'},
    'sidebar_nist_help':  {'en': 'Paste the folder path and press Enter, then click Parse',
                            'zh': '粘贴文件夹路径后按回车，再点击解析'},
    'btn_parse_nist':     {'en': '🔍 Parse NIST Library', 'zh': '🔍 解析 NIST 谱库'},
    'msg_parsing_nist':   {'en': 'Parsing NIST library (this takes ~30s for full NIST17)...',
                            'zh': '正在解析 NIST 谱库 (完整 NIST17 约需 30 秒)...'},
    'msg_nist_loaded':    {'en': '✅ Loaded {n:,} compounds ({f:,} with formula)',
                            'zh': '✅ 已加载 {n:,} 个化合物 ({f:,} 个含分子式)'},
    'msg_nist_db_saved':  {'en': '📁 Database saved: {path}', 'zh': '📁 数据库已保存：{path}'},
    'msg_nist_no_entries':{'en': 'No valid entries found — check the path.',
                            'zh': '未找到有效条目 — 请检查路径。'},
    'msg_nist_not_valid': {'en': 'Not a valid NIST .L directory: {err}',
                            'zh': '不是有效的 NIST .L 目录：{err}'},
    'msg_nist_parse_fail':{'en': 'Parse failed: {err}', 'zh': '解析失败：{err}'},
    'msg_nist_enter_path':{'en': 'Please enter a valid NIST .L folder path.',
                            'zh': '请输入有效的 NIST .L 文件夹路径。'},
    'nist_quick_search':  {'en': 'Quick search NIST', 'zh': '快速搜索 NIST'},
    'nist_quick_placeholder': {'en': 'e.g. caffeine, hexanal, C8H10N4O2',
                                'zh': '例如：caffeine, 己醛, C8H10N4O2'},
    'nist_compounds_indexed': {'en': '📊 {n:,} compounds indexed', 'zh': '📊 已索引 {n:,} 个化合物'},
    'nist_no_matches':    {'en': 'No matches', 'zh': '无匹配结果'},
    'sidebar_jcamp_caption': {'en': 'Point to your licensed NIST JCAMP/MSP files.',
                               'zh': '指向您已授权的 NIST JCAMP/MSP 文件。'},
    'btn_index_nist':     {'en': '📂 Index NIST Library', 'zh': '📂 索引 NIST 谱库'},
    'msg_scanning_nist':  {'en': 'Scanning {path}...', 'zh': '正在扫描 {path}...'},
    'msg_nist_files_found': {'en': 'Found {n} files', 'zh': '找到 {n} 个文件'},
    'msg_nist_indexed':   {'en': 'Indexed {n} NIST spectra ({r} with RI)',
                            'zh': '已索引 {n} 张 NIST 谱图 ({r} 张含 RI)'},

    # ── Data source ──
    'sidebar_data_source': {'en': '📂 Data Source', 'zh': '📂 数据来源'},
    'data_local_dir':     {'en': 'Local Directory', 'zh': '本地文件夹'},
    'data_upload_zip':    {'en': 'Upload .D ZIP', 'zh': '上传 .D 压缩包'},
    'data_demo':          {'en': 'Demo Data', 'zh': '演示数据'},
    'data_path':          {'en': 'Data path', 'zh': '数据路径'},
    'data_path_help':     {'en': 'Folder containing .D files, CSV reports, or data.ms files',
                            'zh': '包含 .D 文件、CSV 报告或 data.ms 文件的文件夹'},
    'btn_load_data':      {'en': '🔄 Load Data', 'zh': '🔄 加载数据'},
    'msg_scanning_data':  {'en': 'Scanning and extracting...', 'zh': '正在扫描和提取...'},
    'msg_load_fail':      {'en': 'Load failed: {err}', 'zh': '加载失败：{err}'},
    'msg_batch1_loaded':  {'en': '✅ Batch 1: {r} peaks, {c} compounds',
                            'zh': '✅ 第 1 批：{r} 个峰，{c} 个化合物'},
    'repl_batch_loaded':  {'en': '📊 Batch 1 loaded ({n} batch(es)). Load replicate?',
                            'zh': '📊 第 1 批已加载 ({n} 批)。加载重复实验？'},
    'repl_path':          {'en': 'Replicate batch path', 'zh': '重复实验路径'},
    'repl_path_ph':       {'en': 'D:\\Experiment2 (same samples, repeated)',
                            'zh': 'D:\\实验2 (相同样品，重复测定)'},
    'btn_load_repl':      {'en': '🔄 Load Replicate Batch', 'zh': '🔄 加载重复批次'},
    'msg_loading_repl':   {'en': 'Loading replicate batch & merging...',
                            'zh': '正在加载重复批次并合并...'},
    'msg_repl_merged':    {'en': '✅ Batch {n} merged! {t} total records with {n}-replicate coverage',
                            'zh': '✅ 第 {n} 批已合并！共 {t} 条记录，{n} 次重复'},
    'msg_repl_info':      {'en': '📈 Plots will now show error bars (mean ± range). Statistics use pooled replicates.',
                            'zh': '📈 图表现在会显示误差棒 (均值±范围)。统计分析使用合并重复。'},
    'msg_repl_fail':      {'en': 'Replicate load failed: {err}', 'zh': '重复批次加载失败：{err}'},
    'zip_upload':         {'en': 'Upload .D folders as ZIP', 'zh': '上传 .D 文件夹压缩包'},
    'btn_extract_load':   {'en': '🔄 Extract & Load', 'zh': '🔄 解压并加载'},
    'msg_extracting':     {'en': 'Extracting...', 'zh': '正在解压...'},
    'msg_peaks_loaded':   {'en': '✅ {n} peaks loaded', 'zh': '✅ 已加载 {n} 个峰'},
    'repl_zip_label':     {'en': 'Load replicate batch ZIP?', 'zh': '加载重复批次压缩包？'},
    'repl_zip_upload':    {'en': 'Replicate .D ZIP', 'zh': '重复实验 .D 压缩包'},
    'btn_load_repl_zip':  {'en': '🔄 Load Replicate ZIP', 'zh': '🔄 加载重复批次压缩包'},
    'msg_repl_zip_merged': {'en': '✅ Merged! Now {n} replicates', 'zh': '✅ 已合并！现在共 {n} 次重复'},
    'btn_load_demo':      {'en': '🎲 Load Demo', 'zh': '🎲 加载演示数据'},
    'msg_generating_demo': {'en': 'Generating demo with synthetic data...',
                             'zh': '正在生成模拟演示数据...'},

    # ── Language switcher ──
    'lang_label':         {'en': '🌐 Language', 'zh': '🌐 语言'},
    'lang_en':            {'en': 'English', 'zh': 'English'},
    'lang_zh':            {'en': '中文', 'zh': '中文'},

    # ── Welcome / Hero ──
    'welcome_title':      {'en': 'GC-MS AI Analyzer',
                            'zh': 'GC-MS 人工智能分析平台'},
    'welcome_subtitle':   {'en': 'Open-Source Alternative to NIST — AI-Powered Flavor & Compound Analysis',
                            'zh': '开源 NIST 替代方案 — AI 驱动的风味与化合物分析'},
    'feature1_title':     {'en': 'Agilent .D Support', 'zh': 'Agilent .D 支持'},
    'feature1_desc':      {'en': 'Directly reads ChemStation data files. No export needed.',
                            'zh': '直接读取 ChemStation 数据文件，无需导出。'},
    'feature2_title':     {'en': 'Multi-Library Search', 'zh': '多谱库检索'},
    'feature2_desc':      {'en': '300K+ compounds: MassBank, MoNA, NIST (local), built-in MSP.',
                            'zh': '30万+ 化合物：MassBank、MoNA、NIST(本地)、内置 MSP。'},
    'feature3_title':     {'en': 'Flavor Analysis', 'zh': '风味分析'},
    'feature3_desc':      {'en': 'OAV, ROVA, flavor wheel, off-flavor DB, pathway tagging.',
                            'zh': 'OAV、ROVA、风味轮、异味数据库、路径标记。'},
    'feature4_title':     {'en': 'AI Agent', 'zh': 'AI 智能体'},
    'feature4_desc':      {'en': 'Natural language: "Find key aroma compounds" → auto-analyzes.',
                            'zh': '自然语言对话："帮我找关键风味化合物" → 自动分析。'},
    'btn_try_demo':       {'en': '☕ Try Demo: Coffee Roasting Flavor Analysis',
                            'zh': '☕ 体验演示：咖啡烘焙风味分析'},
    'msg_demo_loading':   {'en': 'Generating demo dataset...', 'zh': '正在生成演示数据集...'},
    'demo_or_load':       {'en': 'Or load your own data from the sidebar',
                            'zh': '或从侧边栏加载您自己的数据'},
    'stat_tools':         {'en': '📊 50 Analysis Tools', 'zh': '📊 50 个分析工具'},
    'stat_library':       {'en': '📚 300K+ Spectral Library', 'zh': '📚 30万+ 谱库'},
    'stat_interface':     {'en': '🌐 Web + CLI Interface', 'zh': '🌐 网页 + 命令行'},
    'stat_license':       {'en': '🆓 MIT Open Source', 'zh': '🆓 MIT 开源许可'},
    'welcome_howto_title': {'en': '### How to use:', 'zh': '### 如何使用：'},
    'welcome_step1':      {'en': '1. **Set your DeepSeek API Key** in the sidebar',
                            'zh': '1. 在侧边栏**设置 DeepSeek API 密钥**'},
    'welcome_step2':      {'en': '2. **Load data**: type a path, upload a ZIP, or try demo data',
                            'zh': '2. **加载数据**：输入路径、上传压缩包、或试用演示数据'},
    'welcome_step3':      {'en': '3. **Explore**: filter, plot, calculate OAV, run statistics',
                            'zh': '3. **探索分析**：过滤、绘图、计算 OAV、统计分析'},
    'welcome_step4':      {'en': '4. **Export**: download plots, Word tables, or HTML reports',
                            'zh': '4. **导出结果**：下载图表、Word 三线表、HTML 报告'},
    'welcome_load_hint':  {'en': '👈 Load your data from the sidebar to start',
                            'zh': '👈 从侧边栏加载数据开始使用'},

    # ── Tabs ──
    'tab_data':           {'en': '📊 Data', 'zh': '📊 数据'},
    'tab_plots':          {'en': '📈 Plots', 'zh': '📈 图表'},
    'tab_flavor':         {'en': '👃 Flavor', 'zh': '👃 风味'},
    'tab_stats':          {'en': '📐 Statistics', 'zh': '📐 统计'},
    'tab_viz':            {'en': '🔬 GC-MS View', 'zh': '🔬 色谱视图'},
    'tab_export':         {'en': '📥 Export', 'zh': '📥 导出'},

    # ── Data tab ──
    'metric_samples':     {'en': 'Samples', 'zh': '样品'},
    'metric_compounds':   {'en': 'Compounds', 'zh': '化合物'},
    'metric_records':     {'en': 'Records', 'zh': '记录'},
    'metric_groups':      {'en': 'Groups', 'zh': '分组'},
    'filter_min_area':    {'en': 'Min Area', 'zh': '最低峰面积'},
    'filter_min_match':   {'en': 'Min Match', 'zh': '最低匹配度'},
    'filter_excl_unid':   {'en': 'Exclude Unidentified', 'zh': '排除未鉴定峰'},
    'filter_excl_cont':   {'en': 'Exclude Contaminants', 'zh': '排除污染物'},
    'btn_apply_filter':   {'en': 'Apply Filters', 'zh': '应用过滤条件'},
    'msg_filtered':       {'en': '**Filtered: {r} records, {c} compounds, {s} samples**',
                            'zh': '**过滤后：{r} 条记录，{c} 个化合物，{s} 个样品**'},
    'msg_applied_to_agent': {'en': 'Filters applied to agent for downstream analysis.',
                              'zh': '过滤条件已应用到智能体，后续分析将使用过滤后数据。'},
    'btn_rename':         {'en': '✏️ Rename Samples', 'zh': '✏️ 重命名样品'},
    'btn_assign_groups':  {'en': '🏷️ Assign Groups', 'zh': '🏷️ 分配组别'},

    # ── Language ──
    'lang_switcher':      {'en': '🌐 Language / 语言', 'zh': '🌐 语言 / Language'},
}

# ── API ──────────────────────────────────────────────────────
def get_lang():
    """Get current language from session state."""
    if 'lang' not in st.session_state:
        st.session_state.lang = DEFAULT_LANG
    return st.session_state.lang

def set_lang(lang):
    """Set current language."""
    st.session_state.lang = lang

def t(key, **kwargs):
    """Translate a key to the current language.

    Args:
        key: translation key
        **kwargs: format arguments (e.g. n=100)

    Returns:
        Translated and formatted string
    """
    lang = get_lang()
    entry = STRINGS.get(key, {})
    text = entry.get(lang, entry.get('en', key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text

def lang_selector():
    """Render language selector in sidebar. Returns selected language."""
    current = get_lang()
    options = ['en', 'zh']
    labels = ['English', '中文']

    idx = options.index(current) if current in options else 0
    selected_label = st.selectbox(
        t('lang_switcher'),
        labels,
        index=idx,
    )
    selected = options[labels.index(selected_label)]
    if selected != current:
        set_lang(selected)
        st.rerun()
    return selected
