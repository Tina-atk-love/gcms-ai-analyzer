# 🧬 GC-MS AI Analyzer

**Open-Source NIST Alternative** — AI-powered GC-MS data analysis for everyone.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue)](https://docker.com)
[![Tools](https://img.shields.io/badge/Tools-50-orange)](#-tools)
[![Stars](https://img.shields.io/github/stars/Tina-atk-love/gcms-ai-analyzer?style=social)](https://github.com/Tina-atk-love/gcms-ai-analyzer)

> **中文用户?** See [README.md](README.md) for Chinese documentation.

---

## 📸 Screenshots

| TIC Chromatogram | OAV Ranking | PCA Analysis |
|:---:|:---:|:---:|
| [![TIC](docs/screenshots/01_tic_chromatogram.png)](docs/screenshots/01_tic_chromatogram.png) | [![OAV](docs/screenshots/02_oav_ranking.png)](docs/screenshots/02_oav_ranking.png) | [![PCA](docs/screenshots/03_pca_plot.png)](docs/screenshots/03_pca_plot.png) |

| Flavor Wheel | Volcano Plot | Heatmap |
|:---:|:---:|:---:|
| [![Flavor](docs/screenshots/04_flavor_wheel.png)](docs/screenshots/04_flavor_wheel.png) | [![Volcano](docs/screenshots/05_volcano_plot.png)](docs/screenshots/05_volcano_plot.png) | [![Heatmap](docs/screenshots/06_heatmap.png)](docs/screenshots/06_heatmap.png) |

---

## 🚀 Quick Start

### One-Command Install (Recommended)
```bash
pip install gcms-ai-analyzer
gcms-analyzer web    # Opens http://localhost:8501
```

### Or Clone & Run
```bash
git clone https://github.com/Tina-atk-love/gcms-ai-analyzer.git
cd gcms-ai-analyzer
pip install -r requirements.txt

# Web Interface
streamlit run app.py

# CLI Mode (AI Agent)
$env:DEEPSEEK_API_KEY = "sk-your-key"
python gcms_agent.py -d "/path/to/your/data"
```

### Docker
```bash
docker-compose up -d
# Open http://localhost:8501
```

### ☕ Try Without Data — Instant Demo
Open the web app → click **"Try Demo: Coffee Roasting Flavor Analysis"** — loads a realistic 45-compound dataset instantly. No data, no setup, no API key.

---

## 🎯 What It Does

| Category | Capability |
|----------|-----------|
| **Data Loading** | Agilent ChemStation `.D`, TIC CSV, `data.ms`, JCAMP-DX, mzML |
| **Peak Processing** | CWT wavelet peak detection + ALS baseline + AMDIS-style deconvolution |
| **Compound ID** | 7-layer strategy: NIST → MSP cosine → MassBank → MoNA → RI → Isotope → Consensus |
| **Statistics** | t-test, ANOVA+Tukey, PLS-DA VIP, Random Forest, PCA, FDR correction |
| **Quantitation** | External calibration curves, ISTD normalization, LOD/LOQ, ion ratio validation |
| **Flavor Analysis** | OAV, ROVA, flavor wheel, off-flavor database, Maillard/lipid oxidation pathway tagging |
| **Visualization** | 12+ chart types: TIC, bar, heatmap, PCA, volcano, boxplot, flavor wheel, mirror plot |
| **Export** | Excel, Word tables, Plotly interactive HTML, reproducible Python scripts |
| **AI Agent** | Natural language interface — "Find key aroma compounds" triggers full analysis |

## 📊 Spectral Libraries

| Source | Spectra | Type | License |
|--------|---------|------|---------|
| MassBank EU | 28,191 | EI-MS | CC-BY |
| Built-in Flavor Library | 186 | EI-MS | Self-built |
| MoNA API | 1,000,000+ | MS/MS | Public API |
| MassBank MSP | 139,006 | MS2 | CC-BY |
| NIST Local *(user-provided)* | Variable | EI-MS + RI | User licensed |
| JCAMP *(user-provided)* | Variable | EI-MS + RI | User licensed |

## 🔧 Tools (50 total)

### Data Loading (5)
`scan_data_directory` `extract_all_data` `check_chemstation_files` `load_replicate_batch` `detect_peaks`

### Advanced Peak Detection (2)
`detect_peaks` `detect_peaks_advanced` *(CWT wavelet + ALS baseline + shoulder detection)*

### Compound Identification (10)
`match_builtin_library` `search_public_libraries` `calibrate_ri` `identify_with_ri`
`enhanced_identify` `diagnose_unknown` `compound_class_hint` `batch_identify`
`deconvolve_peaks` `search_nist`

### NIST Local Library (5)
`set_nist_path` `load_nist_library` `search_nist` `search_nist_local` *(local NIST server)* `nist_local_server`

### Statistics (5)
`compare_groups` `run_statistical_analysis` `run_anova` `run_plsda` `run_random_forest`

### Flavor Analysis (5)
`calculate_oav` `calculate_rova` `flavor_wheel` `off_flavor_check` `tag_pathways`

### Quantitation (3)
`calibrate_quant` `normalize_istd` `subtract_blank`

### Visualization (6)
`generate_plots` `volcano_plot` `correlation_heatmap` `mirror_plot` `html_report` `tic_chromatogram`

### Quality (3)
`quality_report` `find_anomalies` `correct_batch`

### Workflow & Templates (4)
`list_templates` `apply_template` `save_workflow` `suggest_analysis`

### Export (2)
`export_report` `comprehensive_report` `word_tables`

---

## 🏗 Architecture

```
gcms_analyzer/
├── gcms_agent.py              # Main AI Agent (50 tools, DeepSeek API)
├── app.py                     # Streamlit Web Interface
├── flavor_tools.py            # Flavor: OAV/ROVA/ANOVA/PLS-DA/RF/wheel
├── identification_engine.py   # Enhanced ID: isotopes/consensus/diagnosis
├── spectral_match.py          # Spectral search: cosine/weighted/mirror
├── deconvolution.py           # AMDIS-style peak deconvolution
├── quantitation.py            # Quant: calibration curves/ion ratio
├── workflow_tools.py          # Templates + RT drift correction
├── public_library_manager.py  # Unified library manager (MSP/JCAMP/NIST)
├── spectral_library.py        # Built-in MSP flavor library
├── tools/
│   ├── nist_local_server.py   # Local NIST .L parser + HTTP API
│   ├── advanced_peak_detection.py  # CWT + ALS peak engine
│   ├── interactive_viz.py     # Plotly interactive charts
│   ├── demo_data.py           # Built-in coffee demo dataset
│   └── generate_screenshots.py # README screenshot generator
├── public_libraries/          # Open-source library files
├── Dockerfile / docker-compose.yml
└── docs/screenshots/          # Documentation images
```

---

## 🤖 AI Agent — Natural Language Control

Instead of clicking menus, just ask:

```
You: "Find the key aroma compounds that differ between roasted and green coffee"
Agent: [Calls detect_peaks_advanced → calculate_oav → run_anova → volcano_plot]
       "2-Furanmethanethiol dominates the roasted profile (OAV=850, p<0.001).
        Hexanal is highest in green beans (OAV=12). See volcano plot for details."
```

### CLI Shortcuts

| Command | Action |
|---------|--------|
| `/run` | Auto-extract + detect + identify all peaks |
| `/oav` | Calculate Odor Activity Values |
| `/rova` | Calculate Relative Odor Activity Values |
| `/anova` | Run one-way ANOVA across all groups |
| `/plsda` | PLS-DA with VIP scores |
| `/flavor` | Generate flavor wheel + off-flavor check |
| `/plot` | Generate plots (bar/heatmap/pca/volcano/dashboard) |
| `/nist` | Configure & search local NIST library |
| `/nist-local` | Start local NIST server |

---

## ⚖️ Legal — NIST Library

This project does **NOT** distribute any NIST library data. All NIST-related tools:

- `nist_local_server.py` — reads **your** licensed NIST `.L` files on **your** computer
- `search_nist_local` — connects to `localhost:8765` only
- NIST data (names, formulas, spectra) **never leaves your machine**

If you own a licensed NIST library, point the tool at it and use it locally. If you don't, use the built-in open-source libraries (MassBank, MoNA) which are free and CC-BY licensed.

---

## 📚 Citation

If you use open-source libraries for compound identification, please cite:

- MassBank: Horai et al. (2010) *J. Mass Spectrom.* 45(7), 703-714
- MoNA: https://mona.fiehnlab.ucdavis.edu
- NIST WebBook: Linstrom & Mallard (eds.), NIST SRD 69

---

## 🤝 Contributing

Contributions welcome! See issues for open tasks.

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT — free and open source. Built-in spectral libraries are CC-BY. NIST integration does not distribute any commercial library data.
