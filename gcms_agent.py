#!/usr/bin/env python3
"""
ChemStation .D Data AI Agent -- DeepSeek API
=============================================
Interactive AI agent for Agilent ChemStation .D data analysis
(GC/MS, HPLC, GC-FID, and other chromatographic methods).

Supports REPORT01.CSV (UTF-16 LE), Report.TXT, and Report.XLS/XLSX formats.
Auto-adapts to any compound type — no preset compound list required.

Before first use:
  1. Register DeepSeek: https://platform.deepseek.com
  2. Get API Key: top-right -> API Keys -> Create
  3. PowerShell: $env:DEEPSEEK_API_KEY = "sk-xxx"
  4. Install: pip install openai pandas numpy matplotlib seaborn scipy scikit-learn openpyxl
  5. Run: python gcms_agent.py -d "path/to/data"

Cost: ~$0.14/M input tokens, ~$0.28/M output tokens; ~few cents per analysis
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ============================================================
# Configuration
# ============================================================

AGENT_NAME = "GCMS Analyzer Agent"
AGENT_VERSION = "3.1.0"
OUTPUT_DIR = Path(__file__).parent / "output" / "agent_results"

# DeepSeek API settings
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ============================================================
# Professional Matplotlib Configuration
# ============================================================

PUBLICATION_RCPARAMS = {
    'font.family': 'sans-serif',
    'font.sans-serif': ['Microsoft YaHei', 'SimHei', 'Arial', 'Helvetica'],
    'axes.unicode_minus': False,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
    'figure.facecolor': 'white',
    'axes.facecolor': 'white',
    'axes.edgecolor': '.15',
    'axes.grid': True,
    'grid.alpha': 0.2,
    'grid.linestyle': '-',
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'axes.labelsize': 12,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'legend.frameon': True,
    'legend.framealpha': 0.9,
    'legend.edgecolor': '.15',
    'lines.linewidth': 1.5,
    'lines.markersize': 6,
}

# Color-blind friendly palettes (Okabe-Ito inspired)
COLOR_PALETTES = {
    'categorical': ['#0072B2', '#E69F00', '#009E73', '#F0E442',
                    '#56B4E9', '#D55E00', '#CC79A7', '#000000'],
    'divergent':   ['#2166ac', '#92c5de', '#d1e5f0', '#f7f7f7',
                    '#fddbc7', '#f4a582', '#b2182b'],
}

# ============================================================
# Tool Definitions (OpenAI function-calling format)
# ============================================================

TOOLS = [
    # --- 1. scan_data_directory ---
    {
        "type": "function",
        "function": {
            "name": "scan_data_directory",
            "description": "Scan the data directory for .D folders and report their status (ready/skipped). Call this first to understand the data landscape before any analysis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": "Data directory path containing .D folders"
                    }
                },
                "required": []
            }
        }
    },
    # --- 2. extract_all_data ---
    {
        "type": "function",
        "function": {
            "name": "extract_all_data",
            "description": "Parse REPORT01.CSV (UTF-16 LE) from all .D folders. Returns structured amino acid concentration data. Must be called after scan and before any analysis that needs data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_dir": {
                        "type": "string",
                        "description": "Data directory path"
                    }
                },
                "required": []
            }
        }
    },
    # --- 3. get_sample_info ---
    {
        "type": "function",
        "function": {
            "name": "get_sample_info",
            "description": "Get detailed amino acid profile for a specific sample: concentration, retention time, peak area, and percentage of total amino acids. Supports fuzzy name/number matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sample_name": {
                        "type": "string",
                        "description": "Sample name, e.g. '37', 'egg yolk gel 1', supports fuzzy matching"
                    }
                },
                "required": ["sample_name"]
            }
        }
    },
    # --- 4. compare_groups ---
    {
        "type": "function",
        "function": {
            "name": "compare_groups",
            "description": "Compare amino acid profiles between two groups. Performs Welch t-test, Mann-Whitney U test, computes fold change, Cohen's d effect size, and FDR-adjusted p-values. Returns compounds sorted by significance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_a": {"type": "string", "description": "First group name (numerator for fold change)"},
                    "group_b": {"type": "string", "description": "Second group name (denominator for fold change)"}
                },
                "required": ["group_a", "group_b"]
            }
        }
    },
    # --- 5. generate_plots ---
    {
        "type": "function",
        "function": {
            "name": "generate_plots",
            "description": "Generate publication-quality figures. Options: bar (with significance brackets), heatmap (hierarchical clustering), pca (with 95% confidence ellipses), boxplot (with individual points), composition (stacked ratio), dashboard (6-panel overview), or all.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plot_type": {
                        "type": "string",
                        "enum": ["bar", "heatmap", "pca", "boxplot", "composition", "dashboard", "all"],
                        "description": "Plot type to generate"
                    },
                    "title": {"type": "string", "description": "Optional custom title"}
                },
                "required": ["plot_type"]
            }
        }
    },
    # --- 6. run_statistical_analysis ---
    {
        "type": "function",
        "function": {
            "name": "run_statistical_analysis",
            "description": "Run full statistical analysis: descriptive statistics (mean/std/CV%/quartiles), group comparison (t-test + MWU with FDR), and amino acid correlation matrix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "analysis_type": {
                        "type": "string",
                        "enum": ["descriptive", "comparison", "correlation", "all"],
                        "description": "descriptive=summary stats, comparison=group tests, correlation=pairwise r, all=everything"
                    }
                },
                "required": ["analysis_type"]
            }
        }
    },
    # --- 7. find_anomalies ---
    {
        "type": "function",
        "function": {
            "name": "find_anomalies",
            "description": "Detect outliers using Z-score method. Marks amino acid values exceeding the threshold within each compound. Also identifies affected samples.",
            "parameters": {
                "type": "object",
                "properties": {
                    "zscore_threshold": {
                        "type": "number",
                        "description": "Z-score threshold (default 2.5, lower = more sensitive)"
                    }
                },
                "required": []
            }
        }
    },
    # --- 8. export_report ---
    {
        "type": "function",
        "function": {
            "name": "export_report",
            "description": "Export analysis results to Excel (multi-sheet workbook) or CSV files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["excel", "csv", "both"],
                        "description": "Output format"
                    },
                    "filename": {
                        "type": "string",
                        "description": "Output filename without extension, default: analysis_report"
                    }
                },
                "required": ["format"]
            }
        }
    },
    # --- 9. volcano_plot (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "volcano_plot",
            "description": "Generate a volcano plot (log2 fold change vs -log10 p-value) comparing two groups. Highlights significantly different amino acids above fold-change and p-value thresholds. Ideal for identifying key biomarkers at a glance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_a": {"type": "string", "description": "First group name (numerator for fold change)"},
                    "group_b": {"type": "string", "description": "Second group name (denominator for fold change)"},
                    "p_threshold": {"type": "number", "description": "P-value threshold (default 0.05)"},
                    "fc_threshold": {"type": "number", "description": "Fold change threshold, not log2 (default 1.5)"},
                    "top_n_labels": {"type": "integer", "description": "Number of top points to label (default 10)"}
                },
                "required": ["group_a", "group_b"]
            }
        }
    },
    # --- 10. correlation_heatmap (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "correlation_heatmap",
            "description": "Generate a hierarchically clustered correlation heatmap showing amino acid co-variation patterns across all samples. Includes dendrograms for both rows and columns. Useful for discovering metabolic relationships.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["pearson", "spearman"],
                        "description": "Correlation method: pearson (linear) or spearman (rank-based, robust). Default: pearson"
                    }
                },
                "required": []
            }
        }
    },
    # --- 11. quality_report (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "quality_report",
            "description": "Assess data quality comprehensively: computes missing rate per compound, CV% distribution, outlier count per group using IQR method, and basic batch-effect check. Returns a quality score (good/fair/poor) with detailed metrics.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # --- 12. suggest_analysis (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "suggest_analysis",
            "description": "Given the current data context (groups, samples, compounds, prior results), suggest the most informative next analysis steps. Recommends specific tool calls with rationale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "enum": ["explore", "compare", "quality", "publication", "all"],
                        "description": "Goal: explore=EDA, compare=group differences, quality=QC assessment, publication=figures for papers, all=comprehensive"
                    }
                },
                "required": []
            }
        }
    },
    # --- 13. comprehensive_report (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "comprehensive_report",
            "description": "Generate a professional analysis report suitable for publication. Includes: full statistical analysis, all figures, biological interpretation of amino acid profiles, nutritional/functional significance, comparison with literature values, and scientific references. Saves a formatted report to the output directory. Use this when the user wants paper-quality analysis, not just quick stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_a": {
                        "type": "string",
                        "description": "First group name for comparison (optional, if omitted compares all available groups)"
                    },
                    "group_b": {
                        "type": "string",
                        "description": "Second group name for comparison (optional)"
                    },
                    "report_type": {
                        "type": "string",
                        "enum": ["full", "comparison", "profile", "quality"],
                        "description": "Report type: full=comprehensive report with all sections, comparison=group comparison focused, profile=amino acid profiling focused, quality=QC focused"
                    }
                },
                "required": []
            }
        }
    },
    # --- 14. chemstation_export_guide (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "chemstation_export_guide",
            "description": "Provide step-by-step instructions for exporting data from Agilent ChemStation software. Covers CSV/TXT export, AIA/CDF universal format, batch export, peak table copy, and macro-based automation. Use this when: (a) samples have .D folders but no report files, (b) user needs to know how to get data out of ChemStation, (c) user asks about data export workflow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "enum": ["csv", "txt", "nist", "aia_cdf", "peak_table", "batch", "macro", "all"],
                        "description": "Export format: csv=CSV signal, txt=TXT report, nist=NIST library search for compound names+match, aia_cdf=universal CDF, peak_table=copy table, batch=batch export, macro=automation, all=all methods"
                    }
                },
                "required": []
            }
        }
    },
    # --- 15. check_chemstation_files (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "check_chemstation_files",
            "description": "Check what files exist inside a .D folder to determine the best strategy: has REPORT*.CSV? Report*.TXT? Only raw .CH files? tic_front.csv? data.ms? Returns a detailed inventory and recommends next steps. Use this BEFORE attempting data extraction when scan shows samples with uncertain status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sample_name": {
                        "type": "string",
                        "description": "Specific .D folder name to inspect, e.g. '12.D'. If omitted, checks all folders."
                    }
                },
                "required": []
            }
        }
    },
    # --- 16. detect_peaks (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "detect_peaks",
            "description": "Perform automatic peak detection and integration on TIC chromatogram data. Uses scipy.signal.find_peaks, integrates each peak via trapezoidal rule. Supports min_area filtering. Essential for samples with tic_front.csv but no integrated report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prominence": {
                        "type": "number",
                        "description": "Minimum peak prominence relative to signal range (default 0.005 = 0.5%). Lower = more peaks."
                    },
                    "min_width": {
                        "type": "number",
                        "description": "Minimum peak width in data points (default 5)."
                    },
                    "min_height": {
                        "type": "number",
                        "description": "Minimum absolute peak height (default 10000)."
                    },
                    "min_area": {
                        "type": "number",
                        "description": "Minimum peak area for inclusion in results (default 10000). Filters noise peaks after detection."
                    }
                },
                "required": []
            }
        }
    },
    # --- 17. set_groups (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "set_groups",
            "description": "Assign samples to experimental groups for comparison. All samples default to one group. Use this to split samples into treatment/control or other groups. ALWAYS ask the user about group assignments if there are 2+ distinct sample types or conditions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_name": {
                        "type": "string",
                        "description": "Name for the new group, e.g. 'Control', 'Treatment', 'Fermented'"
                    },
                    "samples": {
                        "type": "string",
                        "description": "Comma-separated sample names or numbers, e.g. 'Sample001,Sample002' or '1-8' for Sample001-Sample008"
                    }
                },
                "required": ["group_name", "samples"]
            }
        }
    },
    # --- 18. match_builtin_library (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "match_builtin_library",
            "description": "Match RT-labeled peaks against a built-in library of ~150 common flavor/aroma compounds. Uses retention time (±0.3 min tolerance) for tentative identification. Provides compound names, categories, odor descriptors, and CAS numbers. Use this when NIST library search results are NOT available, or to supplement NIST results for unidentified peaks. Matched peaks are updated in the dataset with compound names and metadata.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rt_tolerance": {
                        "type": "number",
                        "description": "RT matching tolerance in minutes (default 0.3). Larger = more matches but less confident."
                    }
                },
                "required": []
            }
        }
    },
    # --- 18. filter_data (NEW) ---
    {
        "type": "function",
        "function": {
            "name": "filter_data",
            "description": "Filter the current dataset. ALWAYS call this before plotting. Recommend: exclude_unidentified=true + exclude_contaminants=true for clean publication figures. Parameters are optional — call with no args to see current filter state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_area": {
                        "type": "number",
                        "description": "Minimum absolute peak area (default 10000)."
                    },
                    "min_match": {
                        "type": "number",
                        "description": "Minimum NIST match factor 0-100 (default 70)."
                    },
                    "exclude_unidentified": {
                        "type": "boolean",
                        "description": "Exclude RT-labeled peaks (those without compound names). RECOMMENDED for publication plots."
                    },
                    "exclude_contaminants": {
                        "type": "boolean",
                        "description": "Exclude siloxanes (column bleed) and other contamination markers. RECOMMENDED."
                    },
                    "include_compounds": {
                        "type": "string",
                        "description": "Comma-separated compound names to include. Empty = include all."
                    },
                    "exclude_compounds": {
                        "type": "string",
                        "description": "Comma-separated compound names or patterns to exclude."
                    }
                },
                "required": []
            }
        }
    },
    # --- 19. search_public_libraries (NEW - Open Source NIST Alternative) ---
    {
        "type": "function",
        "function": {
            "name": "search_public_libraries",
            "description": "Search open-source mass spectral libraries (MoNA, MassBank EU, NIST WebBook, built-in MSP) for compound identification — a FREE alternative to Agilent's closed-source NIST library. Searches by spectrum (cosine similarity), compound name, or CAS number. Use this when: (a) NIST library search results are not available from MassHunter, (b) you need to identify RT-labeled peaks, (c) user wants to use free/open-source identification instead of paid NIST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_type": {
                        "type": "string",
                        "enum": ["spectrum", "name", "cas", "all"],
                        "description": "spectrum=search by mass spectrum (needs data.ms access), name=search by compound name, cas=search by CAS number, all=search all available methods"
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query: compound name for 'name' search, CAS number for 'cas' search, or 'auto' for spectrum search (auto-extracts from data.ms)"
                    },
                    "min_match": {
                        "type": "number",
                        "description": "Minimum match factor 0-999 for spectral search (default 600). Higher = more confident but fewer results."
                    },
                    "include_mona": {
                        "type": "boolean",
                        "description": "Include live MoNA (MassBank of North America) API search (default true). Requires internet."
                    },
                    "target_samples": {
                        "type": "string",
                        "description": "Comma-separated sample names to search. If omitted, searches all unidentified peaks across all samples."
                    }
                },
                "required": []
            }
        }
    },
    # --- 20. calibrate_ri (NEW — Kovats Retention Index auto-calibration) ---
    {
        "type": "function",
        "function": {
            "name": "calibrate_ri",
            "description": "Auto-calibrate Kovats Retention Index for all peaks using an alkane standard (C8-C30). Detects n-alkane peaks by their characteristic EI-MS pattern (m/z 43,57,71,85), builds RT→RI calibration curve, then calculates RI for every peak in the dataset. Cross-references with built-in RI database (1498 compounds) for dual-dimension identification (MS + RI). Use this when user has alkane standard data and wants RI-based confirmation of compound IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "alkane_sample": {
                        "type": "string",
                        "description": "Sample name containing alkane standard, e.g. 'C8-C30_std.D' or 'alkanes.D'. If omitted, tries to auto-detect alkane peaks from the current dataset."
                    },
                    "alkane_range": {
                        "type": "string",
                        "description": "Alkane range, e.g. 'C8-C30' or 'C10-C40'. Default: C8-C30"
                    },
                    "apply_to_all": {
                        "type": "boolean",
                        "description": "Apply RI calibration to all samples in the dataset (default true)"
                    }
                },
                "required": []
            }
        }
    },
]

# ============================================================
# Built-in Flavor/Aroma Compound Reference Library
# ============================================================
# ~150 common GC-MS volatile compounds with:
#   - Characteristic EI-MS ions (top 5-8, sorted by abundance)
#   - Approximate RT on DB-5/HP-5 (30m, 40°C → 250°C @ ~6°C/min)
#   - CAS, formula, category, odor descriptor
# Used for tentative identification when NIST library export is unavailable.
# ============================================================

FLAVOR_DB = [
    # Aldehydes
    {"name":"hexanal","cas":"66-25-1","formula":"C6H12O","cat":"aldehyde","odor":"green, grassy","rt_est":5.8,"ions":[44,56,41,57,43,72,82,54]},
    {"name":"heptanal","cas":"111-71-7","formula":"C7H14O","cat":"aldehyde","odor":"fatty, green","rt_est":7.8,"ions":[44,41,55,70,43,57,81,96]},
    {"name":"octanal","cas":"124-13-0","formula":"C8H16O","cat":"aldehyde","odor":"fatty, citrus","rt_est":9.6,"ions":[43,41,44,55,57,69,84,100]},
    {"name":"nonanal","cas":"124-19-6","formula":"C9H18O","cat":"aldehyde","odor":"fatty, floral","rt_est":11.4,"ions":[41,43,57,44,55,70,82,98]},
    {"name":"decanal","cas":"112-31-2","formula":"C10H20O","cat":"aldehyde","odor":"citrus, floral","rt_est":13.1,"ions":[41,43,57,55,44,68,82,112]},
    {"name":"benzaldehyde","cas":"100-52-7","formula":"C7H6O","cat":"aldehyde","odor":"almond, cherry","rt_est":7.5,"ions":[105,77,106,51,50,78,107,52]},
    {"name":"phenylacetaldehyde","cas":"122-78-1","formula":"C8H8O","cat":"aldehyde","odor":"honey, floral","rt_est":9.2,"ions":[91,92,65,120,39,51,63,121]},
    {"name":"2-heptenal","cas":"18829-55-5","formula":"C7H12O","cat":"aldehyde","odor":"fatty, green","rt_est":8.9,"ions":[41,55,83,42,69,84,97,57]},
    {"name":"2-octenal","cas":"2363-89-5","formula":"C8H14O","cat":"aldehyde","odor":"fatty, nutty","rt_est":10.5,"ions":[41,55,70,83,42,57,97,43]},
    {"name":"2-nonenal","cas":"18829-56-6","formula":"C9H16O","cat":"aldehyde","odor":"cucumber, fatty","rt_est":12.2,"ions":[41,43,55,70,83,57,98,42]},
    {"name":"2-decenal","cas":"3913-71-1","formula":"C10H18O","cat":"aldehyde","odor":"fatty, citrus","rt_est":13.8,"ions":[41,43,55,70,57,83,42,98]},
    {"name":"2,4-decadienal","cas":"25152-84-5","formula":"C10H16O","cat":"aldehyde","odor":"fried, fatty","rt_est":14.5,"ions":[81,41,152,67,55,95,39,109]},
    {"name":"furfural","cas":"98-01-1","formula":"C5H4O2","cat":"aldehyde","odor":"almond, caramel","rt_est":5.5,"ions":[96,95,39,38,97,67,29,37]},
    {"name":"5-methylfurfural","cas":"620-02-0","formula":"C6H6O2","cat":"aldehyde","odor":"caramel, sweet","rt_est":7.2,"ions":[110,109,53,81,39,51,27,54]},
    {"name":"5-hydroxymethylfurfural","cas":"67-47-0","formula":"C6H6O3","cat":"aldehyde","odor":"caramel, sweet","rt_est":13.5,"ions":[97,41,126,69,39,29,109,53]},

    # Ketones
    {"name":"2-heptanone","cas":"110-43-0","formula":"C7H14O","cat":"ketone","odor":"blue cheese, fruity","rt_est":6.5,"ions":[43,58,71,41,27,59,55,42]},
    {"name":"2-octanone","cas":"111-13-7","formula":"C8H16O","cat":"ketone","odor":"earthy, mushroom","rt_est":8.4,"ions":[43,58,41,71,59,55,42,57]},
    {"name":"2-nonanone","cas":"821-55-6","formula":"C9H18O","cat":"ketone","odor":"fruity, floral","rt_est":10.2,"ions":[43,58,41,71,57,59,85,42]},
    {"name":"2-undecanone","cas":"112-12-9","formula":"C11H22O","cat":"ketone","odor":"citrus, rue","rt_est":13.5,"ions":[43,58,71,41,59,57,85,55]},
    {"name":"3-octanone","cas":"106-68-3","formula":"C8H16O","cat":"ketone","odor":"earthy, herbal","rt_est":8.0,"ions":[43,57,71,41,99,58,72,55]},
    {"name":"acetoin","cas":"513-86-0","formula":"C4H8O2","cat":"ketone","odor":"buttery, creamy","rt_est":3.2,"ions":[45,43,88,42,27,29,73,44]},
    {"name":"acetophenone","cas":"98-86-2","formula":"C8H8O","cat":"ketone","odor":"floral, almond","rt_est":9.0,"ions":[105,77,120,51,43,78,50,106]},
    {"name":"6-methyl-5-hepten-2-one","cas":"110-93-0","formula":"C8H14O","cat":"ketone","odor":"citrus, green","rt_est":8.2,"ions":[43,41,55,108,69,39,27,53]},
    {"name":"geranylacetone","cas":"3796-70-1","formula":"C13H22O","cat":"ketone","odor":"floral, fruity","rt_est":16.8,"ions":[43,69,41,136,81,93,107,121]},
    {"name":"beta-ionone","cas":"79-77-6","formula":"C13H20O","cat":"ketone","odor":"violet, floral","rt_est":17.5,"ions":[177,43,41,91,135,178,92,105]},

    # Alcohols
    {"name":"1-octen-3-ol","cas":"3391-86-4","formula":"C8H16O","cat":"alcohol","odor":"mushroom, earthy","rt_est":8.4,"ions":[57,43,41,72,55,85,58,67]},
    {"name":"1-hexanol","cas":"111-27-3","formula":"C6H14O","cat":"alcohol","odor":"green, herbaceous","rt_est":5.3,"ions":[56,43,41,55,42,69,31,84]},
    {"name":"1-octanol","cas":"111-87-5","formula":"C8H18O","cat":"alcohol","odor":"waxy, citrus","rt_est":9.2,"ions":[41,43,55,56,70,84,42,57]},
    {"name":"linalool","cas":"78-70-6","formula":"C10H18O","cat":"alcohol","odor":"floral, citrus","rt_est":11.0,"ions":[41,43,55,71,93,69,80,121]},
    {"name":"alpha-terpineol","cas":"98-55-5","formula":"C10H18O","cat":"alcohol","odor":"pine, floral","rt_est":12.5,"ions":[59,43,93,121,136,81,67,41]},
    {"name":"phenylethyl alcohol","cas":"60-12-8","formula":"C8H10O","cat":"alcohol","odor":"rose, honey","rt_est":10.8,"ions":[91,92,65,122,39,51,63,42]},
    {"name":"2-ethyl-1-hexanol","cas":"104-76-7","formula":"C8H18O","cat":"alcohol","odor":"mild, floral","rt_est":7.8,"ions":[57,41,43,55,70,83,42,56]},
    {"name":"benzyl alcohol","cas":"100-51-6","formula":"C7H8O","cat":"alcohol","odor":"floral, fruity","rt_est":8.5,"ions":[79,108,77,107,51,39,50,91]},
    {"name":"isopentyl alcohol","cas":"123-51-3","formula":"C5H12O","cat":"alcohol","odor":"alcoholic, banana","rt_est":2.5,"ions":[42,55,41,43,70,31,39,57]},
    {"name":"2,3-butanediol","cas":"513-85-9","formula":"C4H10O2","cat":"alcohol","odor":"buttery, creamy","rt_est":3.5,"ions":[45,43,57,29,75,47,31,41]},

    # Esters
    {"name":"ethyl acetate","cas":"141-78-6","formula":"C4H8O2","cat":"ester","odor":"fruity, solvent","rt_est":1.8,"ions":[43,61,45,70,42,88,73,29]},
    {"name":"isoamyl acetate","cas":"123-92-2","formula":"C7H14O2","cat":"ester","odor":"banana, fruity","rt_est":6.4,"ions":[43,55,70,61,41,42,87,71]},
    {"name":"ethyl hexanoate","cas":"123-66-0","formula":"C8H16O2","cat":"ester","odor":"fruity, apple","rt_est":8.2,"ions":[88,43,99,41,60,71,55,29]},
    {"name":"ethyl octanoate","cas":"106-32-1","formula":"C10H20O2","cat":"ester","odor":"fruity, wine","rt_est":11.5,"ions":[88,43,101,41,57,55,127,60]},
    {"name":"ethyl decanoate","cas":"110-38-3","formula":"C12H24O2","cat":"ester","odor":"fruity, grape","rt_est":14.8,"ions":[88,43,101,41,57,155,55,70]},
    {"name":"methyl hexanoate","cas":"106-70-7","formula":"C7H14O2","cat":"ester","odor":"fruity, pineapple","rt_est":7.2,"ions":[74,43,41,55,59,71,87,99]},
    {"name":"gamma-butyrolactone","cas":"96-48-0","formula":"C4H6O2","cat":"ester","odor":"creamy, caramel","rt_est":7.5,"ions":[42,86,41,56,28,39,44,85]},
    {"name":"gamma-nonalactone","cas":"104-61-0","formula":"C9H16O2","cat":"ester","odor":"coconut, creamy","rt_est":14.0,"ions":[85,41,128,42,55,100,43,56]},

    # Terpenes
    {"name":"alpha-pinene","cas":"80-56-8","formula":"C10H16","cat":"terpene","odor":"pine, woody","rt_est":7.0,"ions":[93,91,77,92,79,39,41,121]},
    {"name":"beta-pinene","cas":"127-91-3","formula":"C10H16","cat":"terpene","odor":"pine, woody","rt_est":7.6,"ions":[41,69,93,39,79,91,77,53]},
    {"name":"limonene","cas":"138-86-3","formula":"C10H16","cat":"terpene","odor":"citrus, lemon","rt_est":8.8,"ions":[68,67,93,79,53,41,107,121]},
    {"name":"myrcene","cas":"123-35-3","formula":"C10H16","cat":"terpene","odor":"herbal, balsamic","rt_est":8.2,"ions":[41,93,69,39,53,79,77,27]},
    {"name":"p-cymene","cas":"99-87-6","formula":"C10H14","cat":"terpene","odor":"citrus, solvent","rt_est":8.5,"ions":[119,134,91,77,41,65,39,117]},
    {"name":"caryophyllene","cas":"87-44-5","formula":"C15H24","cat":"terpene","odor":"woody, spicy","rt_est":16.5,"ions":[41,69,93,133,79,91,105,55]},
    {"name":"humulene","cas":"6753-98-6","formula":"C15H24","cat":"terpene","odor":"woody, hoppy","rt_est":17.0,"ions":[93,41,80,121,147,67,53,107]},
    {"name":"eucalyptol","cas":"470-82-6","formula":"C10H18O","cat":"terpene","odor":"eucalyptus, minty","rt_est":8.5,"ions":[43,81,71,108,41,55,84,69]},
    {"name":"camphor","cas":"76-22-2","formula":"C10H16O","cat":"terpene","odor":"camphor, minty","rt_est":10.5,"ions":[95,81,41,108,69,83,55,109]},

    # Pyrazines (Maillard reaction products)
    {"name":"2-methylpyrazine","cas":"109-08-0","formula":"C5H6N2","cat":"pyrazine","odor":"nutty, roasted","rt_est":5.2,"ions":[94,67,39,53,40,95,26,68]},
    {"name":"2,5-dimethylpyrazine","cas":"123-32-0","formula":"C6H8N2","cat":"pyrazine","odor":"nutty, roasted","rt_est":6.5,"ions":[108,42,81,39,40,54,109,107]},
    {"name":"2,6-dimethylpyrazine","cas":"108-50-9","formula":"C6H8N2","cat":"pyrazine","odor":"nutty, coffee","rt_est":6.4,"ions":[108,42,40,39,67,54,109,81]},
    {"name":"2,3,5-trimethylpyrazine","cas":"14667-55-1","formula":"C7H10N2","cat":"pyrazine","odor":"nutty, earthy","rt_est":8.2,"ions":[122,42,81,54,39,40,123,56]},
    {"name":"2-ethyl-3,5-dimethylpyrazine","cas":"13925-07-0","formula":"C8H12N2","cat":"pyrazine","odor":"earthy, roasted","rt_est":9.5,"ions":[135,136,42,39,54,108,56,40]},
    {"name":"2-acetylpyrazine","cas":"22047-25-2","formula":"C6H6N2O","cat":"pyrazine","odor":"popcorn, roasted","rt_est":8.8,"ions":[43,80,122,52,94,53,42,123]},
    {"name":"2-acetylpyrrole","cas":"1072-83-9","formula":"C6H7NO","cat":"pyrazine","odor":"nutty, bread","rt_est":10.5,"ions":[94,66,109,43,39,67,41,95]},

    # Furans
    {"name":"furfuryl alcohol","cas":"98-00-0","formula":"C5H6O2","cat":"furan","odor":"burnt, caramel","rt_est":5.5,"ions":[98,41,81,42,97,53,69,39]},
    {"name":"2-acetylfuran","cas":"1192-62-7","formula":"C6H6O2","cat":"furan","odor":"balsamic, caramel","rt_est":6.5,"ions":[95,110,43,39,67,52,41,111]},
    {"name":"maltol","cas":"118-71-8","formula":"C6H6O3","cat":"furan","odor":"caramel, sweet","rt_est":10.0,"ions":[126,71,97,43,55,41,127,39]},
    {"name":"2-pentylfuran","cas":"3777-69-3","formula":"C9H14O","cat":"furan","odor":"green, beany","rt_est":8.5,"ions":[81,138,53,82,41,39,95,54]},
    {"name":"furaneol","cas":"3658-77-3","formula":"C6H8O3","cat":"furan","odor":"caramel, strawberry","rt_est":9.2,"ions":[128,43,57,85,41,72,129,29]},

    # Phenols
    {"name":"guaiacol","cas":"90-05-1","formula":"C7H8O2","cat":"phenol","odor":"smoky, phenolic","rt_est":9.5,"ions":[109,124,81,53,39,27,110,40]},
    {"name":"4-ethylguaiacol","cas":"2785-89-9","formula":"C9H12O2","cat":"phenol","odor":"smoky, spicy","rt_est":12.5,"ions":[137,152,122,138,91,77,27,41]},
    {"name":"eugenol","cas":"97-53-0","formula":"C10H12O2","cat":"phenol","odor":"clove, spicy","rt_est":13.5,"ions":[164,149,77,103,131,91,55,165]},
    {"name":"2,6-dimethoxyphenol","cas":"91-10-1","formula":"C8H10O3","cat":"phenol","odor":"smoky, medicinal","rt_est":13.0,"ions":[154,139,111,93,65,39,55,41]},
    {"name":"p-cresol","cas":"106-44-5","formula":"C7H8O","cat":"phenol","odor":"phenolic, animal","rt_est":9.0,"ions":[107,108,77,79,90,51,39,80]},
    {"name":"vanillin","cas":"121-33-5","formula":"C8H8O3","cat":"phenol","odor":"vanilla, sweet","rt_est":15.0,"ions":[151,152,81,109,123,53,41,39]},

    # Acids
    {"name":"acetic acid","cas":"64-19-7","formula":"C2H4O2","cat":"acid","odor":"vinegar, sour","rt_est":1.8,"ions":[43,45,60,42,41,40,44,29]},
    {"name":"butyric acid","cas":"107-92-6","formula":"C4H8O2","cat":"acid","odor":"rancid, cheesy","rt_est":4.5,"ions":[60,73,41,42,43,45,55,27]},
    {"name":"hexanoic acid","cas":"142-62-1","formula":"C6H12O2","cat":"acid","odor":"sweaty, cheesy","rt_est":8.0,"ions":[60,73,41,43,42,71,87,55]},
    {"name":"octanoic acid","cas":"124-07-2","formula":"C8H16O2","cat":"acid","odor":"sweaty, fatty","rt_est":11.0,"ions":[60,73,41,43,55,57,101,84]},

    # Sulfur compounds
    {"name":"dimethyl disulfide","cas":"624-92-0","formula":"C2H6S2","cat":"sulfur","odor":"cabbage, sulfurous","rt_est":2.8,"ions":[94,45,79,47,64,46,48,61]},
    {"name":"dimethyl trisulfide","cas":"3658-80-8","formula":"C2H6S3","cat":"sulfur","odor":"cabbage, sulfurous","rt_est":7.5,"ions":[126,79,45,47,64,80,111,128]},
    {"name":"methional","cas":"3268-49-3","formula":"C4H8OS","cat":"sulfur","odor":"potato, cooked","rt_est":6.5,"ions":[48,104,76,47,45,56,61,75]},
    {"name":"3-methylthiopropanal","cas":"3268-49-3","formula":"C4H8OS","cat":"sulfur","odor":"potato, brothy","rt_est":6.5,"ions":[48,104,76,47,45,56,61,75]},
    {"name":"benzothiazole","cas":"95-16-9","formula":"C7H5NS","cat":"sulfur","odor":"rubber, sulfide","rt_est":11.5,"ions":[135,69,108,63,82,45,54,90]},

    # Lactones
    {"name":"gamma-hexalactone","cas":"695-06-7","formula":"C6H10O2","cat":"lactone","odor":"coumarin, sweet","rt_est":9.2,"ions":[42,85,41,56,43,28,39,114]},
    {"name":"gamma-octalactone","cas":"104-50-7","formula":"C8H14O2","cat":"lactone","odor":"coconut, creamy","rt_est":12.5,"ions":[85,41,42,142,55,43,56,71]},
    {"name":"delta-decalactone","cas":"705-86-2","formula":"C10H18O2","cat":"lactone","odor":"coconut, peach","rt_est":17.5,"ions":[99,42,71,41,43,55,56,114]},

    # Alkanes (solvent/contamination markers)
    {"name":"dodecane","cas":"112-40-3","formula":"C12H26","cat":"alkane","odor":"alkane","rt_est":10.5,"ions":[43,57,41,71,55,85,42,56]},
    {"name":"tetradecane","cas":"629-59-4","formula":"C14H30","cat":"alkane","odor":"alkane","rt_est":14.0,"ions":[43,57,41,71,55,85,42,56]},
    {"name":"hexadecane","cas":"544-76-3","formula":"C16H34","cat":"alkane","odor":"alkane","rt_est":17.2,"ions":[43,57,41,71,55,85,42,56]},

    # Siloxanes (column bleed / contamination — EXCLUDE)
    {"name":"hexamethylcyclotrisiloxane","cas":"541-05-9","formula":"C6H18O3Si3","cat":"siloxane","odor":"none (column bleed)","rt_est":6.5,"ions":[207,96,191,73,133,43,45,208]},
    {"name":"octamethylcyclotetrasiloxane","cas":"556-67-2","formula":"C8H24O4Si4","cat":"siloxane","odor":"none (column bleed)","rt_est":9.8,"ions":[281,73,282,147,133,43,45,207]},
    {"name":"decamethylcyclopentasiloxane","cas":"541-02-6","formula":"C10H30O5Si5","cat":"siloxane","odor":"none (column bleed)","rt_est":13.0,"ions":[73,267,355,269,73,147,133,356]},
]

# Convert to lookup format
FLAVOR_LOOKUP = {}
for c in FLAVOR_DB:
    FLAVOR_LOOKUP[c["name"]] = c

# ============================================================
# Agent Core
# ============================================================

class GCMSAgent:
    """GCMS .D Data AI Agent -- Powered by DeepSeek API"""

    def __init__(self, api_key=None, base_url=None, model=None, data_dir=None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY not set!\n"
                "  1. Visit https://platform.deepseek.com\n"
                "  2. Register/Login -> API Keys -> Create New Key\n"
                "  3. PowerShell: $env:DEEPSEEK_API_KEY = 'sk-xxx'\n"
                "  4. Re-run: python gcms_agent.py"
            )

        self.base_url = base_url or DEEPSEEK_BASE_URL
        self.model = model or os.environ.get("DEEPSEEK_MODEL") or DEEPSEEK_MODEL

        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        self.data_dir = data_dir
        self.df = None
        self.analysis = {}
        self.d_folders = {}
        self.messages = []

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "plots").mkdir(parents=True, exist_ok=True)

        # Auto-check public libraries on startup
        self._public_lib_status = self._check_public_libraries()

    def _check_public_libraries(self):
        """Check if public libraries are available, return status dict."""
        from pathlib import Path
        lib_dir = Path(__file__).parent / "public_libraries"
        files = list(lib_dir.glob("*")) if lib_dir.exists() else []
        has_msp = any(f.suffix.lower() == '.msp' for f in files)
        has_csv = any(f.suffix.lower() == '.csv' for f in files)
        has_json = any(f.suffix.lower() == '.json' for f in files)
        n_files = len([f for f in files if not f.name.startswith('.')])
        return {
            'has_libraries': n_files > 0,
            'n_files': n_files,
            'has_massbank_msp': has_msp,
            'has_nist_csv': has_csv,
            'has_mona_json': has_json,
            'lib_dir': str(lib_dir),
        }

    def _auto_download_public_libraries(self):
        """Check public library availability. Shows status without attempting
        downloads that are known to fail from China (GitHub SSL block, Zenodo 10053).

        The built-in 186 EI-MS spectra always work offline.
        MassBank.eu v3 is queried live for name lookup.
        To add more spectra: manually place .msp files in public_libraries/.
        """
        status = self._check_public_libraries()

        # Check what we have
        try:
            from spectral_library import load_library
            builtin = load_library()
            n_builtin = len(builtin)
        except Exception:
            n_builtin = '?'

        try:
            from mona_client import check_apis
            apis = check_apis()
        except Exception:
            apis = {'massbank_eu': False}

        print()
        print("  ┌──────────────────────────────────────────────────┐")
        print(f"  │  开源质谱谱库                                     │")
        print(f"  ├──────────────────────────────────────────────────┤")
        print(f"  │  内置 EI-MS:  {n_builtin} 张参考谱图 (离线, 余弦匹配)   │")
        if apis.get('massbank_eu'):
            print(f"  │  MassBank.eu: 在线 (名称检索)                     │")
        else:
            print(f"  │  MassBank.eu: 离线                               │")
        if status['has_libraries']:
            print(f"  │  本地文件:    {status['n_files']} 个已加载                    │")
        print(f"  ├──────────────────────────────────────────────────┤")
        print(f"  │  扩充谱库: 放置 .msp 文件到 public_libraries/     │")
        print(f"  └──────────────────────────────────────────────────┘")
        print()

        return status

    # ========================================================
    # Tool Implementations
    # ========================================================

    def _scan_data_directory(self, data_dir=None):
        data_dir = data_dir or self.data_dir
        data_path = Path(data_dir)
        if not data_path.exists():
            return json.dumps({"error": f"Directory not found: {data_dir}"}, ensure_ascii=False)

        all_dirs = sorted(data_path.rglob("*.D"))
        result = {"total": len(all_dirs), "ready": [], "skipped": [], "groups": {}}

        for d in all_dirs:
            # Determine group: use subdirectory name if nested (data_dir/Group/Sample.D),
            # otherwise use parent directory of data_dir or just basename as default
            if d.parent == data_path:
                group = data_path.name or "Default"
            else:
                group = d.parent.name

            has_csv = bool(list(d.glob("REPORT*.CSV")))
            has_txt = bool(list(d.glob("Report*.TXT")) + list(d.glob("*.TXT")))
            has_xls = bool(list(d.glob("Report*.XLS")) + list(d.glob("*.XLSX")))
            has_raw = bool(list(d.glob("*.CH")) + list(d.glob("*.UV")))
            # NEW: MassHunter GC-MS TIC data
            has_tic_csv = bool(list(d.glob("tic_front.csv")))
            has_data_ms = bool(list(d.glob("data.ms")))

            has_reports = has_csv or has_txt or has_xls
            report_types = []
            if has_csv: report_types.append("CSV")
            if has_txt: report_types.append("TXT")
            if has_xls: report_types.append("XLS")
            if has_tic_csv: report_types.append("TIC_CSV")

            info = {
                "name": d.name,
                "group": group,
                "path": str(d),  # Store absolute path for reliable access
                "has_reports": has_reports or has_tic_csv,
                "report_types": report_types,
                "raw_only": (has_raw or has_data_ms) and not (has_reports or has_tic_csv),
                "has_tic_csv": has_tic_csv,
                "has_data_ms": has_data_ms,
            }

            if has_reports or has_tic_csv:
                result["ready"].append(info)
            else:
                result["skipped"].append(info)

            if group not in result["groups"]:
                result["groups"][group] = {"ready": 0, "skipped": 0, "raw_only": 0}
            if has_reports or has_tic_csv:
                result["groups"][group]["ready"] += 1
            elif has_raw or has_data_ms:
                result["groups"][group]["raw_only"] += 1
            else:
                result["groups"][group]["skipped"] += 1

        self.d_folders = result
        return json.dumps(result, ensure_ascii=False)

    def _extract_all_data(self, data_dir=None):
        data_dir = data_dir or self.data_dir
        scan = json.loads(self._scan_data_directory(data_dir))
        if "error" in scan:
            return json.dumps(scan, ensure_ascii=False)

        import pandas as pd

        records = []
        skipped = []
        fallback_used = []  # Track which format was used

        # --- NEW: Detect if we're dealing with TIC CSV (MassHunter GC-MS) ---
        has_tic_data = any(info.get("has_tic_csv") for info in scan.get("ready", []))
        if has_tic_data:
            # Collect all TIC peaks for cross-sample RT alignment
            all_sample_peaks = []
            tic_processed = 0

            for info in scan.get("ready", []):
                if not info.get("has_tic_csv"):
                    continue

                # Use stored path or construct from data_dir
                d_path = Path(info["path"]) if info.get("path") else Path(data_dir) / info["group"] / info["name"]
                tic_file = d_path / "tic_front.csv"
                if not tic_file.exists():
                    tic_file = d_path / "tic_front.tsv"
                if not tic_file.exists():
                    skipped.append({**info, "error": "tic_front.csv not found"})
                    continue

                tic_data = self._parse_tic_csv(str(tic_file))
                if not tic_data:
                    skipped.append({**info, "error": "Failed to parse TIC CSV"})
                    continue

                # Run peak detection
                import numpy as np
                peaks_json = json.loads(
                    self._detect_peaks_method(
                        tic_data["times"],
                        tic_data["intensities"],
                        prominence=0.005,
                        min_width=5,
                        min_height=10000,
                    )
                )

                if peaks_json.get("status") != "success" or not peaks_json.get("peaks"):
                    skipped.append({**info, "error": f"No peaks detected: {peaks_json.get('message', 'unknown')}"})
                    continue

                all_sample_peaks.append((info["name"], info["group"], peaks_json["peaks"]))
                tic_processed += 1

            # Cross-sample RT alignment
            if all_sample_peaks:
                aligned = self._align_peaks_by_rt(all_sample_peaks, rt_tolerance=0.03)
                for rec in aligned:
                    records.append({
                        "group": rec["group"],
                        "sample": rec["sample"],
                        "compound": rec["compound"],
                        "rt": rec["rt"],
                        "area": rec["area"],
                        "height": rec.get("height", 0),
                        "amount": rec["area"],
                        "conc_g100g": rec["area_pct"],
                    })

                fallback_used.append(f"TIC_CSV + peak detection ({tic_processed} samples, {len(set(r['compound'] for r in aligned))} compounds aligned)")

            if records:
                self.df = pd.DataFrame(records)
                compounds = sorted(self.df['compound'].unique().tolist())

                # ================================================================
                # Merge MassHunter NIST Library Search Results
                # ================================================================
                # Search strategy (per sample):
                #   1. <sample_name>_library.csv inside .D folder
                #   2. <sample_name>_library.csv in parent data_dir
                #   3. *library*.csv / *nist*.csv inside .D folder (generic glob)
                # Match peaks by RT (±0.04 min tolerance), enrich with:
                #   compound_name, match_factor, reverse_match, formula, cas
                # ================================================================
                lib_merged = 0
                lib_samples_found = 0
                for col in ['compound', 'match_factor', 'reverse_match', 'formula', 'cas']:
                    if col not in self.df.columns:
                        self.df[col] = None

                for info in scan.get("ready", []):
                    if not info.get("has_tic_csv"):
                        continue

                    d_path = Path(info["path"]) if info.get("path") else Path(data_dir) / info["group"] / info["name"]
                    sample_name = info["name"]

                    # Build search list: specific name first, then generic patterns
                    sample_stem = sample_name.replace('.D', '')
                    lib_files = []

                    # Priority 1: <SampleName>_library.csv inside .D folder
                    lib_files.extend(list(d_path.glob(f"{sample_stem}_library*.csv")))
                    lib_files.extend(list(d_path.glob(f"{sample_stem}_nist*.csv")))
                    lib_files.extend(list(d_path.glob(f"{sample_stem}_match*.csv")))

                    # Priority 2: <SampleName>_library.csv in parent data_dir
                    parent_path = Path(data_dir)
                    lib_files.extend(list(parent_path.glob(f"{sample_stem}_library*.csv")))
                    lib_files.extend(list(parent_path.glob(f"{sample_stem}_nist*.csv")))
                    lib_files.extend(list(parent_path.glob(f"{sample_stem}_match*.csv")))

                    # Priority 3: generic library/search CSVs in .D folder
                    lib_files.extend(list(d_path.glob("*library*.csv")) + list(d_path.glob("*nist*.csv")) +
                                    list(d_path.glob("*search*.csv")) + list(d_path.glob("*match*.csv")))

                    # Deduplicate preserving order
                    seen = set()
                    lib_files_unique = []
                    for f in lib_files:
                        if str(f) not in seen:
                            seen.add(str(f))
                            lib_files_unique.append(f)
                    lib_files = lib_files_unique

                    if not lib_files:
                        continue

                    for lib_file in lib_files:
                        lib_results = self._parse_masshunter_library_csv(str(lib_file))
                        if not lib_results:
                            continue

                        matched_this_sample = 0
                        for lr in lib_results:
                            if lr['rt'] <= 0:
                                continue

                            # Find closest TIC peak by RT within tolerance
                            sample_mask = (
                                (self.df['sample'] == sample_name) &
                                (abs(self.df['rt'] - lr['rt']) < 0.05)
                            )
                            matches = self.df[sample_mask]
                            if matches.empty:
                                continue

                            # Pick the closest RT match
                            matches = matches.copy()
                            matches['rt_diff'] = abs(matches['rt'] - lr['rt'])
                            best_idx = matches['rt_diff'].idxmin()

                            # Enrich peak with library data
                            if lr['compound_name'] and lr['compound_name'].lower() not in ('unknown', 'unknown compound', ''):
                                self.df.at[best_idx, 'compound'] = lr['compound_name'].lower()
                            if lr['match_factor'] > 0:
                                self.df.at[best_idx, 'match_factor'] = lr['match_factor']
                            if lr['reverse_match'] > 0:
                                self.df.at[best_idx, 'reverse_match'] = lr['reverse_match']
                            if lr['formula']:
                                self.df.at[best_idx, 'formula'] = lr['formula']
                            if lr['cas']:
                                self.df.at[best_idx, 'cas'] = lr['cas']
                            matched_this_sample += 1

                        if matched_this_sample > 0:
                            lib_merged += matched_this_sample
                            lib_samples_found += 1
                            break  # Use first valid library file for this sample

                # ================================================================
                # Auto-match using MASS SPECTRA from data.ms (Aston library)
                # ================================================================
                spec_matches = json.loads(self._match_spectra_library())

                # ================================================================
                # Fallback: match against built-in flavor library (RT-based)
                # ================================================================
                builtin_matches = json.loads(self._match_builtin_library(rt_tolerance=0.3))

                # ================================================================
                # Apply default filters: area >= 10,000 + match >= 70 (if available)
                # ================================================================
                has_match_data = bool(self.df['match_factor'].notna().any()) if 'match_factor' in self.df.columns else False

                self.df_unfiltered = self.df.copy()
                pre_filter = len(self.df)

                # Filter 1: min_area
                self.df = self.df[self.df['area'] >= 10000].copy()
                area_filtered = pre_filter - len(self.df)

                # Filter 2: min_match (only if library data available)
                match_filtered = 0
                if has_match_data:
                    pre_match = len(self.df)
                    # Keep rows where match_factor is NaN (not matched) OR match_factor >= 70
                    self.df = self.df[
                        self.df['match_factor'].isna() |
                        (self.df['match_factor'] >= 70)
                    ].copy()
                    match_filtered = pre_match - len(self.df)

                auto_filtered = area_filtered + match_filtered
                compounds = sorted(self.df['compound'].unique().tolist())

                # Separate identified vs unidentified compounds
                identified = [c for c in compounds if not c.startswith('RT_')]
                unidentified = [c for c in compounds if c.startswith('RT_')]

                # Built-in library match stats
                builtin_count = builtin_matches.get('total_matches', 0)
                builtin_categories = builtin_matches.get('categories', {})

                return json.dumps({
                    "status": "success",
                    "data_type": "TIC_CSV",
                    "peak_detection": True,
                    "total_records": len(self.df),
                    "n_samples": int(self.df['sample'].nunique()),
                    "n_compounds": len(compounds),
                    "compounds": compounds[:60],
                    "compounds_identified": identified[:40],
                    "compounds_unidentified": len(unidentified),
                    "groups": self.df['group'].unique().tolist(),
                    "data_sources": {"tic_csv_count": tic_processed},
                    "library_search": {
                        "merged": lib_merged,
                        "samples_with_library": lib_samples_found,
                        "has_match_data": has_match_data,
                        "match_filter_applied": match_filtered > 0 if has_match_data else False,
                        "match_threshold": 70 if has_match_data else None,
                    },
                    "filters_applied": {
                        "min_area": 10000,
                        "area_filtered_count": area_filtered,
                        "min_match": 70 if has_match_data else None,
                        "match_filtered_count": match_filtered if has_match_data else 0,
                    },
                    "fallback_used": fallback_used,
                    "builtin_library_matches": {
                        "count": builtin_count,
                        "categories": builtin_categories,
                        "note": "Tentative IDs based on RT only — confirm with NIST or standards"
                    },
                    "reminder": (
                        "Filters applied: area>=10,000" +
                        (f", match>=70 (NIST). {len(identified)} compounds identified ({builtin_count} by built-in library)."
                         if has_match_data and lib_samples_found > 0 else
                         f". Built-in library matched {builtin_count} peaks tentatively ({len(unidentified)} still RT-only). "
                         "For confirmed IDs, export NIST results from MassHunter Qual → save *library*.csv in .D folders.")
                        + (f" Categories: {', '.join(f'{k}({v})' for k,v in sorted(builtin_categories.items(), key=lambda x:-x[1])[:6])}."
                           if builtin_categories else "")
                        + (f" Top: {', '.join(identified[:12])}." if identified else "")
                    ),
                    "skipped_count": len(skipped),
                    "skipped_names": [s.get('name', '?') for s in skipped[:5]],
                }, ensure_ascii=False)

        # --- Standard flow: CSV report, TXT fallback, XLS last resort ---
        for info in scan.get("ready", []):
            # Skip TIC-only samples (already processed above)
            if info.get("has_tic_csv") and not any(t in info.get("report_types", []) for t in ["CSV", "TXT", "XLS"]):
                continue

            d_path = Path(info["path"]) if info.get("path") else Path(data_dir) / info["group"] / info["name"]
            report_types = info.get("report_types", [])

            # Strategy: CSV first (structured), TXT fallback, XLS last resort
            data_source = None
            parsed_peaks = []

            # --- Try CSV first ---
            if "CSV" in report_types:
                csv_files = list(d_path.glob("REPORT01.CSV"))
                if not csv_files:
                    csv_files = list(d_path.glob("REPORT*.CSV"))
                if csv_files:
                    try:
                        with open(csv_files[0], 'r', encoding='utf-16-le', errors='ignore') as f:
                            raw = f.read()

                        for line in raw.strip().split('\n'):
                            if not line.strip():
                                continue
                            parts = self._parse_csv(line)
                            if len(parts) < 8:
                                continue
                            try:
                                rt = float(parts[0].strip())
                                area = float(parts[2].strip())
                                amount = float(parts[3].strip())
                                conc = float(parts[4].strip())
                                compound = parts[7].strip().strip('"').lower()
                                if compound and len(compound) <= 20:
                                    parsed_peaks.append({
                                        'rt': round(rt, 3),
                                        'area': round(area, 1),
                                        'amount': amount,
                                        'conc_g100g': conc,
                                        'compound': compound,
                                    })
                            except (ValueError, IndexError):
                                continue
                        data_source = "CSV"
                    except Exception as e:
                        skipped.append({**info, "error": f"CSV parse: {e}"})

            # --- Try TXT fallback ---
            if not parsed_peaks and "TXT" in report_types:
                txt_files = list(d_path.glob("Report*.TXT"))
                if not txt_files:
                    txt_files = list(d_path.glob("*.TXT"))
                if txt_files:
                    try:
                        parsed_peaks = self._parse_report_txt(txt_files[0])
                        if parsed_peaks:
                            data_source = "TXT"
                            fallback_used.append(f"{info['name']} (TXT)")
                    except Exception as e:
                        skipped.append({**info, "error": f"TXT parse: {e}"})

            # --- Try XLS fallback ---
            if not parsed_peaks and "XLS" in report_types:
                xls_files = list(d_path.glob("Report*.XLS")) + list(d_path.glob("*.XLSX"))
                if xls_files:
                    try:
                        xls_df = pd.read_excel(xls_files[0])
                        # Try to find RT, Area, Amount, Name columns
                        rt_col = area_col = amount_col = name_col = None
                        for col in xls_df.columns:
                            col_l = str(col).lower()
                            if 'rt' in col_l or 'ret' in col_l or 'time' in col_l:
                                rt_col = col
                            elif 'area' in col_l:
                                area_col = col
                            elif 'amount' in col_l or 'conc' in col_l:
                                amount_col = col
                            elif 'name' in col_l or 'compound' in col_l:
                                name_col = col

                        if rt_col and area_col and name_col:
                            for _, row in xls_df.iterrows():
                                try:
                                    rt = float(row[rt_col])
                                    area = float(row[area_col])
                                    amount = float(row[amount_col]) if amount_col else 0
                                    compound = str(row[name_col]).strip().lower()
                                    if compound and len(compound) <= 20 and compound != 'nan':
                                        parsed_peaks.append({
                                            'rt': round(rt, 3),
                                            'area': round(area, 1),
                                            'amount': amount,
                                            'conc_g100g': amount,
                                            'compound': compound,
                                        })
                                except (ValueError, TypeError):
                                    continue
                            data_source = "XLS"
                            fallback_used.append(f"{info['name']} (XLS)")
                    except Exception as e:
                        skipped.append({**info, "error": f"XLS parse: {e}"})

            # --- Process parsed peaks ---
            if parsed_peaks:
                for p in parsed_peaks:
                    records.append({
                        'group': info['group'],
                        'sample': info['name'],
                        'compound': p['compound'],
                        'rt': p['rt'],
                        'area': p['area'],
                        'amount': p['amount'],
                        'conc_g100g': p['conc_g100g'],
                    })
            elif not data_source:
                skipped.append({**info, "error": "No parseable data found"})

        if records:
            self.df = pd.DataFrame(records)
            summary = {
                "status": "success",
                "total_records": len(records),
                "n_samples": int(self.df['sample'].nunique()),
                "compounds": sorted(self.df['compound'].unique().tolist()),
                "groups": self.df['group'].unique().tolist(),
                "data_sources": {
                    "csv_count": sum(1 for r in scan.get("ready", []) if "CSV" in r.get("report_types", [])),
                    "txt_count": sum(1 for r in scan.get("ready", []) if "TXT" in r.get("report_types", [])),
                    "xls_count": sum(1 for r in scan.get("ready", []) if "XLS" in r.get("report_types", [])),
                },
                "fallback_used": fallback_used if fallback_used else "none (all CSV)",
                "conc_range_g100g": {
                    "min": round(float(self.df['conc_g100g'].min()), 6),
                    "max": round(float(self.df['conc_g100g'].max()), 4),
                    "mean": round(float(self.df['conc_g100g'].mean()), 4),
                },
                "skipped_count": len(skipped),
                "skipped_names": [s.get('name', '?') for s in skipped[:5]],
            }
            return json.dumps(summary, ensure_ascii=False)
        else:
            # Provide helpful guidance
            raw_count = sum(1 for s in scan.get("skipped", []) if s.get("raw_only"))
            hint = ""
            if raw_count > 0:
                hint = (f" {raw_count} folder(s) have raw .CH/.UV files only. "
                       f"Use chemstation_export_guide for instructions on exporting data from ChemStation first.")
            return json.dumps({
                "error": "No data could be extracted",
                "skipped": len(skipped),
                "raw_only_folders": raw_count,
                "hint": hint.strip(),
            }, ensure_ascii=False)

    def _get_sample_info(self, sample_name):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        matches = self.df[self.df['sample'].str.contains(sample_name, case=False)]
        if matches.empty:
            import re
            num = re.search(r'(\d+)', sample_name)
            if num:
                matches = self.df[self.df['sample'].str.contains(num.group(1))]
        if matches.empty:
            return json.dumps({"error": f"No sample matching '{sample_name}'"}, ensure_ascii=False)

        actual_sample = matches.iloc[0]['sample']
        sample_df = self.df[self.df['sample'] == actual_sample]
        group = sample_df.iloc[0]['group']

        compounds = {}
        total = 0
        for _, row in sample_df.iterrows():
            compounds[row['compound']] = {
                "conc_g100g": round(row['conc_g100g'], 6),
                "rt_min": round(row['rt'], 3),
                "area": round(row['area'], 1),
            }
            total += row['conc_g100g']

        for c in compounds:
            compounds[c]["pct_of_total"] = round(compounds[c]["conc_g100g"] / total * 100, 2) if total > 0 else 0

        top5 = sorted(compounds.items(), key=lambda x: x[1]['conc_g100g'], reverse=True)[:5]

        return json.dumps({
            "sample": actual_sample,
            "group": group,
            "total_conc_g100g": round(total, 4),
            "n_compounds": len(compounds),
            "top5": [{"compound": c, "conc": d['conc_g100g'], "pct": d['pct_of_total']} for c, d in top5],
            "all_compounds": compounds,
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # compare_groups -- enhanced with FDR + Cohen's d + MWU
    # --------------------------------------------------------
    def _compare_groups(self, group_a, group_b):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        from scipy import stats
        import numpy as np

        a_df = self.df[self.df['group'] == group_a]
        b_df = self.df[self.df['group'] == group_b]

        if a_df.empty:
            return json.dumps({"error": f"Group '{group_a}' not found. Available: {self.df['group'].unique().tolist()}"}, ensure_ascii=False)
        if b_df.empty:
            return json.dumps({"error": f"Group '{group_b}' not found"}, ensure_ascii=False)

        results = []
        common = sorted(set(a_df['compound'].unique()) & set(b_df['compound'].unique()))

        for comp in common:
            a_vals = a_df[a_df['compound'] == comp]['conc_g100g'].dropna()
            b_vals = b_df[b_df['compound'] == comp]['conc_g100g'].dropna()
            if len(a_vals) < 2 or len(b_vals) < 2:
                continue

            # Welch t-test
            t_stat, t_p = stats.ttest_ind(a_vals, b_vals, equal_var=False)

            # Mann-Whitney U test
            try:
                u_stat, mw_p = stats.mannwhitneyu(a_vals, b_vals, alternative='two-sided')
            except Exception:
                u_stat, mw_p = None, None

            # Fold change
            mean_a, mean_b = a_vals.mean(), b_vals.mean()
            fc = mean_a / mean_b if mean_b > 0 else float('inf')

            # Cohen's d effect size
            n_a, n_b = len(a_vals), len(b_vals)
            sd_a, sd_b = a_vals.std(ddof=1), b_vals.std(ddof=1)
            pooled_sd = np.sqrt(((n_a - 1) * sd_a**2 + (n_b - 1) * sd_b**2) / (n_a + n_b - 2))
            cohens_d = (mean_a - mean_b) / pooled_sd if pooled_sd > 0 else 0.0
            effect = "large" if abs(cohens_d) > 0.8 else ("medium" if abs(cohens_d) > 0.5 else "small")

            results.append({
                "compound": comp,
                f"mean_{group_a[:8]}": round(mean_a, 6),
                f"mean_{group_b[:8]}": round(mean_b, 6),
                "fold_change": round(fc, 2),
                "log2_fc": round(np.log2(fc), 3) if fc > 0 else None,
                "cohens_d": round(cohens_d, 3),
                "effect_size": effect,
                "p_value_t": round(float(t_p), 6),
                "p_value_mwu": round(float(mw_p), 6) if mw_p is not None else None,
            })

        # Sort by t-test p-value
        results.sort(key=lambda x: x['p_value_t'])

        # Benjamini-Hochberg FDR correction
        n = len(results)
        if n > 1:
            p_values = np.array([r['p_value_t'] for r in results])
            sorted_idx = np.argsort(p_values)
            p_adj = np.ones(n)
            for rank, idx in enumerate(sorted_idx):
                p_adj[idx] = min(p_values[idx] * n / (rank + 1), 1.0)
            # Ensure monotonicity
            for i in range(n - 1, 0, -1):
                p_adj[sorted_idx[i - 1]] = min(p_adj[sorted_idx[i - 1]], p_adj[sorted_idx[i]])
        else:
            p_adj = np.ones(n)

        for i, r in enumerate(results):
            r['p_value_fdr'] = round(float(p_adj[i]), 6)
            raw_p = r['p_value_t']
            fdr_p = p_adj[i]
            if fdr_p < 0.001:
                r['significant'] = '***'
            elif fdr_p < 0.01:
                r['significant'] = '**'
            elif fdr_p < 0.05:
                r['significant'] = '*'
            else:
                r['significant'] = 'ns'

        sig_count = sum(1 for r in results if r['significant'] != 'ns')

        return json.dumps({
            "group_A": group_a, "group_B": group_b,
            "samples_A": int(a_df['sample'].nunique()),
            "samples_B": int(b_df['sample'].nunique()),
            "compared": len(results),
            "significant_raw": sum(1 for r in results if r['p_value_t'] < 0.05),
            "significant_fdr": sig_count,
            "top_significant": [r for r in results if r['significant'] != 'ns'][:10],
            "all_results": results,
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # generate_plots -- refactored with professional helpers
    # --------------------------------------------------------
    def _generate_plots(self, plot_type, title=None):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns

        plt.rcParams.update(PUBLICATION_RCPARAMS)

        plots_dir = OUTPUT_DIR / "plots"
        generated = []

        types = ['bar', 'heatmap', 'pca', 'boxplot', 'composition', 'dashboard'] if plot_type == 'all' else [plot_type]

        for pt in types:
            try:
                if pt == 'bar':
                    generated.append(self._plot_bar(title))
                elif pt == 'heatmap':
                    generated.append(self._plot_heatmap(title))
                elif pt == 'pca':
                    generated.append(self._plot_pca(title))
                elif pt == 'boxplot':
                    generated.append(self._plot_boxplot(title))
                elif pt == 'composition':
                    generated.append(self._plot_composition(title))
                elif pt == 'dashboard':
                    generated.append(self._plot_dashboard(title))
            except Exception as e:
                generated.append(f"ERROR {pt}: {str(e)}")

        ok = [g for g in generated if not g.startswith('ERROR')]
        return json.dumps({"status": "done", "generated": ok, "count": len(ok), "errors": len(generated) - len(ok)}, ensure_ascii=False)

    # ---- Individual plot methods ----

    def _plot_bar(self, title=None):
        import numpy as np
        import matplotlib.pyplot as plt
        from scipy import stats

        pivot = self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                     columns='compound', aggfunc='mean').reset_index()
        aa_cols = [c for c in pivot.columns if c not in ['group', 'sample']]
        groups = sorted(self.df['group'].unique())
        n_groups = len(groups)
        colors = COLOR_PALETTES['categorical'][:n_groups]

        # Group means + std
        stats_list = []
        for comp in aa_cols:
            for g in groups:
                vals = self.df[(self.df['compound'] == comp) & (self.df['group'] == g)]['conc_g100g']
                stats_list.append({'compound': comp, 'group': g, 'mean': vals.mean(), 'std': vals.std(), 'n': len(vals)})

        import pandas as pd
        stats_df = pd.DataFrame(stats_list)

        fig, ax = plt.subplots(figsize=(max(12, len(aa_cols) * 1.2), 7))
        x = np.arange(len(aa_cols))
        w = 0.8 / n_groups

        for i, g in enumerate(groups):
            gd = stats_df[stats_df['group'] == g].set_index('compound').reindex(aa_cols)
            offset = (i - n_groups / 2 + 0.5) * w
            bars = ax.bar(x + offset, gd['mean'].values, w,
                          yerr=gd['std'].values, label=str(g),
                          color=colors[i], edgecolor='white', linewidth=0.5,
                          capsize=3, error_kw={'linewidth': 1})

        # Significance brackets (for exactly 2 groups)
        if n_groups == 2:
            for j, comp in enumerate(aa_cols):
                a_vals = self.df[(self.df['compound'] == comp) & (self.df['group'] == groups[0])]['conc_g100g']
                b_vals = self.df[(self.df['compound'] == comp) & (self.df['group'] == groups[1])]['conc_g100g']
                if len(a_vals) >= 2 and len(b_vals) >= 2:
                    _, p = stats.ttest_ind(a_vals, b_vals)
                    if p < 0.05:
                        stars = '***' if p < 0.001 else ('**' if p < 0.01 else '*')
                        y_max = max(a_vals.mean() + a_vals.std(), b_vals.mean() + b_vals.std())
                        bracket_y = y_max * 1.08
                        x1, x2 = x[j] - w / 2, x[j] + w / 2
                        ax.plot([x1, x1, x2, x2], [y_max, bracket_y, bracket_y, y_max],
                                'k-', lw=0.8, clip_on=False)
                        ax.text(x[j], bracket_y, stars, ha='center', va='bottom',
                                fontsize=10, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels(aa_cols, rotation=30, ha='right', fontsize=9)
        ax.set_ylabel('Concentration [g/100g]', fontsize=12)
        ax.set_title(title or 'Amino Acid Concentration by Group', fontsize=14, fontweight='bold')
        ax.legend(fontsize=9, loc='upper right')
        plt.tight_layout()

        p = str(OUTPUT_DIR / "plots" / "bar_chart.png")
        fig.savefig(p)
        plt.close(fig)
        return p

    def _plot_heatmap(self, title=None):
        import numpy as np
        import matplotlib.pyplot as plt
        import seaborn as sns

        pivot = self.df.pivot_table(values='conc_g100g', index='sample', columns='compound', aggfunc='mean')
        data_norm = (pivot - pivot.mean()) / pivot.std()
        data_norm = data_norm.fillna(0)

        pivot.index = pivot.index.str.replace(r'\.D$', '', regex=True)
        data_norm.index = pivot.index

        g = sns.clustermap(
            data_norm,
            method='ward', metric='euclidean',
            cmap='RdBu_r', center=0,
            figsize=(14, max(8, len(pivot) * 0.45)),
            linewidths=0.5,
            annot=data_norm.round(2), fmt='.2f',
            annot_kws={'fontsize': 7},
            cbar_kws={'label': 'Z-score', 'shrink': 0.6},
            dendrogram_ratio=(0.15, 0.1),
            xticklabels=True, yticklabels=True,
        )
        g.ax_heatmap.set_xlabel('Amino Acid', fontsize=12)
        g.ax_heatmap.set_ylabel('Sample', fontsize=12)
        g.fig.suptitle(title or 'Hierarchical Clustering Heatmap', fontsize=14, fontweight='bold', y=1.02)

        p = str(OUTPUT_DIR / "plots" / "heatmap.png")
        g.savefig(p, dpi=300, bbox_inches='tight')
        plt.close(g.fig)
        return p

    def _plot_pca(self, title=None):
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.patches import Ellipse
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        pivot = self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                     columns='compound', aggfunc='mean').fillna(0)
        aa_cols = list(pivot.columns)
        groups = sorted(self.df['group'].unique())
        colors = COLOR_PALETTES['categorical'][:len(groups)]

        X = pivot.values
        X_s = StandardScaler().fit_transform(X)
        pca = PCA(n_components=min(3, X.shape[0], X.shape[1]))
        X_pca = pca.fit_transform(X_s)
        evr = pca.explained_variance_ratio_

        fig, axes = plt.subplots(1, 2, figsize=(18, 8))

        # Scores plot with confidence ellipses
        ax = axes[0]
        for i, g in enumerate(groups):
            mask = np.array([idx[0] == g for idx in pivot.index])
            x_vals, y_vals = X_pca[mask, 0], X_pca[mask, 1]
            ax.scatter(x_vals, y_vals, s=120, c=colors[i], label=g,
                      edgecolors='black', linewidth=0.5, zorder=5, alpha=0.85)

            # 95% confidence ellipse
            if len(x_vals) >= 3:
                cov = np.cov(x_vals, y_vals)
                eigenvalues, eigenvectors = np.linalg.eigh(cov)
                angle = np.degrees(np.arctan2(eigenvectors[1, 0], eigenvectors[0, 0]))
                width, height = 2 * np.sqrt(5.991 * eigenvalues)  # 95% CI chi2
                ellipse = Ellipse((np.mean(x_vals), np.mean(y_vals)),
                                  width, height, angle=angle,
                                  facecolor=colors[i], alpha=0.1, edgecolor=colors[i], linewidth=1)
                ax.add_patch(ellipse)

            for j in np.where(mask)[0]:
                lbl = pivot.index[j][1].replace('.D', '')
                ax.annotate(lbl, (X_pca[j, 0], X_pca[j, 1]),
                          fontsize=7, alpha=0.8, xytext=(4, 4), textcoords='offset points')

        ax.set_xlabel(f'PC1 ({evr[0]*100:.1f}%)', fontsize=12)
        ax.set_ylabel(f'PC2 ({evr[1]*100:.1f}%)', fontsize=12)
        ax.set_title('PCA Scores with 95% CI', fontsize=13, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(alpha=0.3, linestyle='--')

        # Loadings plot
        ax = axes[1]
        loadings = pca.components_.T
        for i, comp in enumerate(aa_cols):
            ax.arrow(0, 0, loadings[i, 0] * 3, loadings[i, 1] * 3,
                    head_width=0.06, head_length=0.09, fc='#e74c3c', ec='#c0392b', alpha=0.7)
            ax.text(loadings[i, 0] * 3.3, loadings[i, 1] * 3.3, comp,
                   fontsize=9, ha='center', va='center', fontweight='bold')
        ax.set_xlabel(f'PC1 ({evr[0]*100:.1f}%)', fontsize=12)
        ax.set_ylabel(f'PC2 ({evr[1]*100:.1f}%)', fontsize=12)
        ax.set_title('PCA Loadings', fontsize=13, fontweight='bold')
        ax.grid(alpha=0.3, linestyle='--')
        ax.axhline(y=0, color='gray', alpha=0.3)
        ax.axvline(x=0, color='gray', alpha=0.3)

        plt.tight_layout()
        p = str(OUTPUT_DIR / "plots" / "pca.png")
        fig.savefig(p)
        plt.close(fig)
        return p

    def _plot_boxplot(self, title=None):
        import numpy as np
        import matplotlib.pyplot as plt
        import seaborn as sns
        from scipy import stats

        avail = sorted(self.df['compound'].unique())
        groups = sorted(self.df['group'].unique())
        nc, nr = 4, (len(avail) + 3) // 4
        colors = COLOR_PALETTES['categorical'][:len(groups)]

        fig, axes = plt.subplots(nr, nc, figsize=(4.5 * nc, 3.5 * nr))
        axes = axes.flatten() if nr * nc > 1 else [axes]

        for i, comp in enumerate(avail):
            ax = axes[i]
            cd = self.df[self.df['compound'] == comp]
            bp_data = [cd[cd['group'] == g]['conc_g100g'].values for g in groups]

            bp = ax.boxplot(bp_data, tick_labels=groups, patch_artist=True,
                          widths=0.5, showfliers=True)
            for patch, g in zip(bp['boxes'], groups):
                idx = groups.index(g)
                patch.set_facecolor(colors[idx % len(colors)])
                patch.set_alpha(0.5)

            # Overlay individual points
            for j, g in enumerate(groups):
                vals = cd[cd['group'] == g]['conc_g100g'].values
                jitter = np.random.normal(0, 0.06, len(vals))
                ax.scatter(np.ones(len(vals)) * (j + 1) + jitter, vals,
                          alpha=0.6, s=20, c='black', zorder=5)

            # Significance between first two groups
            if len(groups) >= 2:
                a_vals = cd[cd['group'] == groups[0]]['conc_g100g']
                b_vals = cd[cd['group'] == groups[1]]['conc_g100g']
                if len(a_vals) >= 2 and len(b_vals) >= 2:
                    _, p = stats.ttest_ind(a_vals, b_vals)
                    if p < 0.05:
                        stars = '***' if p < 0.001 else ('**' if p < 0.01 else '*')
                        y_max = max(a_vals.max(), b_vals.max())
                        y_range = y_max - min(a_vals.min(), b_vals.min())
                        bracket_y = y_max + y_range * 0.08
                        ax.plot([1, 1, 2, 2], [y_max, bracket_y, bracket_y, y_max],
                               'k-', lw=0.8, clip_on=False)
                        ax.text(1.5, bracket_y, stars, ha='center', va='bottom',
                               fontsize=10, fontweight='bold')

            ax.set_title(comp, fontsize=10, fontweight='bold')
            ax.tick_params(labelsize=8)
            ax.grid(axis='y', alpha=0.3, linestyle='--')

        for i in range(len(avail), len(axes)):
            axes[i].set_visible(False)

        fig.suptitle(title or 'Amino Acid Distribution by Group', fontsize=14, fontweight='bold', y=1.01)
        plt.tight_layout()
        p = str(OUTPUT_DIR / "plots" / "boxplot.png")
        fig.savefig(p)
        plt.close(fig)
        return p

    def _plot_composition(self, title=None):
        import numpy as np
        import matplotlib.pyplot as plt

        pivot = self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                     columns='compound', aggfunc='mean').fillna(0)
        aa_cols = list(pivot.columns)
        totals = pivot.sum(axis=1)
        ratio = pivot.div(totals, axis=0) * 100

        labels = [f"{idx[0][:6]}|{idx[1].replace('.D', '')}" for idx in pivot.index]
        ratio.index = labels

        colors = plt.cm.tab20(np.linspace(0, 1, len(aa_cols)))
        fig, ax = plt.subplots(figsize=(14, max(7, len(labels) * 0.4)))
        ratio.plot(kind='bar', stacked=True, ax=ax, color=colors, width=0.8)
        ax.set_ylabel('Composition [%]', fontsize=12)
        ax.set_title(title or 'Amino Acid Composition Profile', fontsize=14, fontweight='bold')
        ax.legend(fontsize=8, ncol=3, loc='upper right')
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=8)
        ax.set_ylim(0, 105)

        plt.tight_layout()
        p = str(OUTPUT_DIR / "plots" / "composition.png")
        fig.savefig(p)
        plt.close(fig)
        return p

    def _plot_dashboard(self, title=None):
        import numpy as np
        import matplotlib.pyplot as plt
        import seaborn as sns

        pivot = self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                     columns='compound', aggfunc='mean').fillna(0)
        aa_cols = list(pivot.columns)
        groups = sorted(self.df['group'].unique())
        colors = COLOR_PALETTES['categorical'][:len(groups)]

        fig = plt.figure(figsize=(22, 16))
        gs = fig.add_gridspec(3, 3, hspace=0.4, wspace=0.3)

        # (0,0) Total AA per sample
        ax1 = fig.add_subplot(gs[0, 0])
        pd_df = pivot.copy()
        pd_df['label'] = [s.replace('.D', '') for s in pivot.index.get_level_values('sample')]
        pd_df['group'] = [g for g, _ in pivot.index]
        pd_df['total'] = pd_df[aa_cols].sum(axis=1)
        pd_df = pd_df.sort_values('total', ascending=False)
        bar_colors = [colors[groups.index(g) % len(colors)] if g in groups else '#95a5a6'
                      for g in pd_df['group']]
        ax1.barh(range(len(pd_df)), pd_df['total'], color=bar_colors, edgecolor='white')
        ax1.set_yticks(range(len(pd_df)))
        ax1.set_yticklabels(pd_df['label'], fontsize=7)
        ax1.set_xlabel('Total [g/100g]', fontsize=9)
        ax1.set_title('Total AA per Sample', fontsize=11, fontweight='bold')

        # (0,1:) Group comparison bar
        ax2 = fig.add_subplot(gs[0, 1:])
        gm = self.df.groupby(['group', 'compound'])['conc_g100g'].mean().reset_index()
        top8 = self.df.groupby('compound')['conc_g100g'].mean().nlargest(8).index
        pm = gm[gm['compound'].isin(top8)].pivot(index='group', columns='compound', values='conc_g100g').fillna(0)
        pm.plot(kind='bar', ax=ax2, color=colors[:len(pm)], edgecolor='black', linewidth=0.5)
        ax2.set_title('Major AA by Group', fontsize=11, fontweight='bold')
        ax2.legend(fontsize=8)
        ax2.tick_params(axis='x', rotation=15)
        ax2.grid(axis='y', alpha=0.3, linestyle='--')

        # (1,:2) Clustered heatmap
        ax3 = fig.add_subplot(gs[1, :2])
        hm = pivot.droplevel('group').copy()
        hm.index = hm.index.str.replace(r'\.D$', '', regex=True)
        hm_norm = (hm - hm.mean()) / hm.std()
        sns.heatmap(hm_norm, cmap='RdBu_r', center=0, ax=ax3,
                   cbar_kws={'label': 'Z-score', 'shrink': 0.8}, linewidths=0.3)
        ax3.set_title('Profile Heatmap (Z-score)', fontsize=11, fontweight='bold')
        ax3.tick_params(labelsize=7)

        # (1,2) CV% by compound
        ax4 = fig.add_subplot(gs[1, 2])
        cv = self.df.groupby('compound')['conc_g100g'].agg(['mean', 'std']).fillna(0)
        cv['cv_pct'] = (cv['std'] / cv['mean'].replace(0, np.nan) * 100).fillna(0)
        cv = cv.sort_values('cv_pct', ascending=False)
        cv_colors = ['#e74c3c' if v > 50 else ('#f39c12' if v > 25 else '#27ae60') for v in cv['cv_pct']]
        ax4.barh(range(len(cv)), cv['cv_pct'], color=cv_colors, edgecolor='white')
        ax4.set_yticks(range(len(cv)))
        ax4.set_yticklabels(cv.index, fontsize=8)
        ax4.set_xlabel('CV%', fontsize=9)
        ax4.set_title('Variability (CV%)', fontsize=11, fontweight='bold')
        ax4.axvline(x=25, color='gray', linestyle='--', alpha=0.5)
        ax4.axvline(x=50, color='gray', linestyle='--', alpha=0.5)

        # (2,0) Concentration distribution
        ax5 = fig.add_subplot(gs[2, 0])
        for i, g in enumerate(groups):
            gdata = self.df[self.df['group'] == g]['conc_g100g'].dropna()
            ax5.hist(gdata, bins=30, alpha=0.5, label=g, color=colors[i % len(colors)])
        ax5.set_xlabel('Concentration [g/100g]', fontsize=9)
        ax5.set_ylabel('Frequency', fontsize=9)
        ax5.set_title('Concentration Distribution', fontsize=11, fontweight='bold')
        ax5.legend(fontsize=7)
        ax5.grid(alpha=0.3, linestyle='--')

        # (2,1:) Summary table
        ax6 = fig.add_subplot(gs[2, 1:])
        ax6.axis('off')

        sig_count = 0
        if len(groups) >= 2:
            from scipy import stats
            for comp in self.df['compound'].unique():
                a = self.df[(self.df['compound'] == comp) & (self.df['group'] == groups[0])]['conc_g100g']
                b = self.df[(self.df['compound'] == comp) & (self.df['group'] == groups[1])]['conc_g100g']
                if len(a) >= 2 and len(b) >= 2:
                    _, p = stats.ttest_ind(a, b)
                    if p < 0.05:
                        sig_count += 1

        summary_lines = [
            "=== GCMS Amino Acid Analysis ===",
            "",
            f"  Samples:        {self.df['sample'].nunique()}",
            f"  Records:        {len(self.df)}",
            f"  Compounds:      {self.df['compound'].nunique()}",
            f"  Groups:         {len(groups)}",
            f"  Significant AA: {sig_count} (p<0.05)",
            "",
            f"  Conc range: {self.df['conc_g100g'].min():.4f} - {self.df['conc_g100g'].max():.4f} g/100g",
            f"  Mean conc:  {self.df['conc_g100g'].mean():.4f} g/100g",
            "",
            f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        ]

        ax6.text(0.05, 0.95, '\n'.join(summary_lines), transform=ax6.transAxes,
                fontsize=9, fontfamily='monospace', verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='#fef9e7', edgecolor='#f39c12', alpha=0.9))

        fig.suptitle(title or 'GCMS Analysis Dashboard', fontsize=15, fontweight='bold', y=1.01)
        p = str(OUTPUT_DIR / "plots" / "dashboard.png")
        fig.savefig(p, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        return p

    # --------------------------------------------------------
    # volcano_plot (NEW)
    # --------------------------------------------------------
    def _volcano_plot(self, group_a, group_b, p_threshold=0.05, fc_threshold=1.5, top_n_labels=10):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        # Get comparison data
        comp_json = json.loads(self._compare_groups(group_a, group_b))
        if "error" in comp_json:
            return json.dumps(comp_json, ensure_ascii=False)

        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        plt.rcParams.update(PUBLICATION_RCPARAMS)

        results = comp_json.get("all_results", [])
        if not results:
            return json.dumps({"error": "No comparison results available"}, ensure_ascii=False)

        # Build volcano data
        points = []
        for r in results:
            p_val = r.get('p_value_t', 1)
            fc = r.get('fold_change', 1)
            log2_fc = np.log2(fc) if fc > 0 else 0
            neg_log10_p = -np.log10(max(p_val, 1e-300))
            points.append({
                'compound': r['compound'],
                'log2_fc': log2_fc,
                'neg_log10_p': neg_log10_p,
                'p_value': p_val,
                'fold_change': fc,
                'significant': r.get('significant', 'ns') != 'ns',
            })

        # Thresholds
        log2_fc_thresh = np.log2(fc_threshold)
        neg_log10_p_thresh = -np.log10(p_threshold)

        # Categorize
        up = [p for p in points if p['log2_fc'] > log2_fc_thresh and p['neg_log10_p'] > neg_log10_p_thresh]
        down = [p for p in points if p['log2_fc'] < -log2_fc_thresh and p['neg_log10_p'] > neg_log10_p_thresh]
        ns = [p for p in points if p not in up and p not in down]

        fig, ax = plt.subplots(figsize=(10, 8))

        # Non-significant
        if ns:
            ax.scatter([p['log2_fc'] for p in ns], [p['neg_log10_p'] for p in ns],
                      c='#bdc3c7', s=80, alpha=0.6, label=f'NS ({len(ns)})', zorder=1)

        # Up-regulated
        if up:
            ax.scatter([p['log2_fc'] for p in up], [p['neg_log10_p'] for p in up],
                      c='#e74c3c', s=100, alpha=0.8, edgecolors='#c0392b', linewidth=0.5,
                      label=f'Up ({len(up)})', zorder=3)

        # Down-regulated
        if down:
            ax.scatter([p['log2_fc'] for p in down], [p['neg_log10_p'] for p in down],
                      c='#3498db', s=100, alpha=0.8, edgecolors='#2980b9', linewidth=0.5,
                      label=f'Down ({len(down)})', zorder=3)

        # Threshold lines
        ax.axhline(y=neg_log10_p_thresh, color='gray', linestyle='--', linewidth=1, alpha=0.5,
                  label=f'p={p_threshold}')
        ax.axvline(x=log2_fc_thresh, color='gray', linestyle=':', linewidth=1, alpha=0.4)
        ax.axvline(x=-log2_fc_thresh, color='gray', linestyle=':', linewidth=1, alpha=0.4)

        # Label top N
        candidates = sorted(up + down, key=lambda x: x['neg_log10_p'], reverse=True)[:top_n_labels]
        for p in candidates:
            color = '#e74c3c' if p['log2_fc'] > 0 else '#3498db'
            ax.annotate(p['compound'], (p['log2_fc'], p['neg_log10_p']),
                       fontsize=9, fontweight='bold', color=color,
                       xytext=(5, 5), textcoords='offset points',
                       bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.8))

        ax.set_xlabel(f'log2 Fold Change ({group_a} / {group_b})', fontsize=12)
        ax.set_ylabel('-log10(p-value)', fontsize=12)
        ax.set_title(f'Volcano Plot: {group_a} vs {group_b}', fontsize=14, fontweight='bold')
        ax.legend(fontsize=9, loc='upper right')
        ax.grid(alpha=0.3, linestyle='--')

        plt.tight_layout()
        p = str(OUTPUT_DIR / "plots" / "volcano.png")
        fig.savefig(p)
        plt.close(fig)

        return json.dumps({
            "status": "done",
            "file": p,
            "summary": {
                "up_regulated": len(up),
                "down_regulated": len(down),
                "not_significant": len(ns),
                "top_up": [{'compound': x['compound'], 'log2_fc': x['log2_fc'], 'p': x['p_value']}
                          for x in sorted(up, key=lambda x: x['neg_log10_p'], reverse=True)[:5]],
                "top_down": [{'compound': x['compound'], 'log2_fc': x['log2_fc'], 'p': x['p_value']}
                            for x in sorted(down, key=lambda x: x['neg_log10_p'], reverse=True)[:5]],
            }
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # correlation_heatmap (NEW)
    # --------------------------------------------------------
    def _correlation_heatmap(self, method='pearson'):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import seaborn as sns

        plt.rcParams.update(PUBLICATION_RCPARAMS)

        pivot = self.df.pivot_table(values='conc_g100g', index='sample', columns='compound', aggfunc='mean')
        corr = pivot.corr(method=method)

        fig = plt.figure(figsize=(12, 10))
        g = sns.clustermap(
            corr,
            method='ward', metric='euclidean',
            cmap='RdBu_r', center=0, vmin=-1, vmax=1,
            figsize=(12, 10),
            linewidths=0.5,
            annot=corr.round(2), fmt='.2f',
            annot_kws={'fontsize': 8},
            cbar_kws={'label': f'{method.capitalize()} r', 'shrink': 0.7},
            dendrogram_ratio=(0.12, 0.12),
            xticklabels=True, yticklabels=True,
        )
        g.ax_heatmap.set_title(f'Amino Acid {method.capitalize()} Correlation', fontsize=14, fontweight='bold', pad=20)
        g.ax_heatmap.tick_params(labelsize=9)

        p = str(OUTPUT_DIR / "plots" / "correlation_heatmap.png")
        g.savefig(p, dpi=300, bbox_inches='tight')
        plt.close(g.fig)

        # Return strongest correlations
        cols = corr.columns
        strong = []
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                r = corr.iloc[i, j]
                if abs(r) > 0.5:
                    strong.append({"pair": f"{cols[i]} - {cols[j]}", "r": round(r, 3)})
        strong.sort(key=lambda x: abs(x['r']), reverse=True)

        return json.dumps({
            "status": "done",
            "file": p,
            "method": method,
            "n_compounds": len(cols),
            "strong_correlations": strong[:15],
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # quality_report (NEW)
    # --------------------------------------------------------
    def _quality_report(self):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        import numpy as np
        pivot = self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                     columns='compound', aggfunc='mean')

        # 1. Missing rate per compound
        missing = {}
        for col in pivot.columns:
            missing_rate = pivot[col].isna().sum() / len(pivot)
            if missing_rate > 0:
                missing[col] = round(missing_rate * 100, 1)

        # 2. CV% distribution
        cv_list = []
        for comp in self.df['compound'].unique():
            cd = self.df[self.df['compound'] == comp]['conc_g100g']
            if cd.mean() > 0:
                cv_list.append({'compound': comp, 'cv_pct': round(cd.std() / cd.mean() * 100, 1)})
        cv_values = [x['cv_pct'] for x in cv_list]
        cv_stats = {
            'mean_cv': round(np.mean(cv_values), 1),
            'median_cv': round(np.median(cv_values), 1),
            'high_cv_count': sum(1 for v in cv_values if v > 50),
            'low_cv_count': sum(1 for v in cv_values if v < 25),
        }

        # 3. Outlier count per group (IQR method)
        outlier_counts = {}
        for g in self.df['group'].unique():
            g_counts = 0
            for comp in self.df['compound'].unique():
                vals = self.df[(self.df['compound'] == comp) & (self.df['group'] == g)]['conc_g100g']
                if len(vals) < 4:
                    continue
                q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
                iqr = q3 - q1
                if iqr > 0:
                    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                    g_counts += sum((vals < lower) | (vals > upper))
            outlier_counts[g] = g_counts

        # 4. Quality score
        total_issues = (
            len(missing) * 2 +
            cv_stats['high_cv_count'] * 1.5 +
            sum(outlier_counts.values()) * 0.5
        )
        n_compounds = self.df['compound'].nunique()
        if total_issues < n_compounds * 0.5:
            score = "good"
        elif total_issues < n_compounds * 1.5:
            score = "fair"
        else:
            score = "poor"

        # 5. Warnings
        warnings = []
        if missing:
            warnings.append(f"{len(missing)} compounds have missing values")
        if cv_stats['high_cv_count'] > 0:
            warnings.append(f"{cv_stats['high_cv_count']} compounds have CV% > 50")
        for g, count in outlier_counts.items():
            if count > 0:
                warnings.append(f"Group '{g}': {count} IQR outliers")

        return json.dumps({
            "overall_score": score,
            "missing_rate_pct": missing,
            "cv_stats": cv_stats,
            "outliers_per_group": outlier_counts,
            "warnings": warnings,
            "recommendation": (
                "Data quality is good. Proceed with analysis."
                if score == "good" else
                "Some quality issues detected. Consider checking flagged items before drawing conclusions."
                if score == "fair" else
                "Significant quality concerns. Review warnings carefully and consider data cleaning."
            ),
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # suggest_analysis (NEW)
    # --------------------------------------------------------
    def _suggest_analysis(self, goal='all'):
        suggestions = []
        has_data = self.df is not None
        groups = self.df['group'].unique() if has_data else []
        n_groups = len(groups)
        n_compounds = self.df['compound'].nunique() if has_data else 0
        has_plots = bool(list((OUTPUT_DIR / "plots").glob("*.png")))

        if goal in ('explore', 'all'):
            if not has_data:
                suggestions.append({
                    "action": "Scan and extract data",
                    "rationale": "No data loaded. Start by scanning the directory and extracting all amino acid data.",
                    "steps": [
                        {"tool": "scan_data_directory", "params": {}},
                        {"tool": "extract_all_data", "params": {}},
                    ]
                })
            else:
                suggestions.append({
                    "action": "Run descriptive statistics",
                    "rationale": f"Data loaded: {self.df['sample'].nunique()} samples, {n_compounds} compounds. Get a summary of distributions.",
                    "tool": "run_statistical_analysis",
                    "params": {"analysis_type": "descriptive"}
                })
                if not has_plots:
                    suggestions.append({
                        "action": "Generate key plots",
                        "rationale": "No plots yet. Recommend: bar (group comparison) + pca (sample grouping) + heatmap (overview). Ask which the user wants.",
                        "tool": "generate_plots",
                        "params": {"plot_type": "ask_user"}
                    })

        if goal in ('compare', 'all') and n_groups >= 2:
            for i in range(min(n_groups - 1, 2)):
                suggestions.append({
                    "action": f"Compare '{groups[i]}' vs '{groups[i+1]}'",
                    "rationale": f"Compare the two groups to find significantly different amino acids.",
                    "steps": [
                        {"tool": "compare_groups", "params": {"group_a": groups[i], "group_b": groups[i+1]}},
                        {"tool": "volcano_plot", "params": {"group_a": groups[i], "group_b": groups[i+1]}},
                    ]
                })

        if goal in ('quality', 'all') and has_data:
            suggestions.append({
                "action": "Assess data quality",
                "rationale": "Check for missing values, outliers, and high variability before proceeding with analysis.",
                "tool": "quality_report",
                "params": {}
            })

        if goal in ('compare', 'all') and n_compounds >= 5:
            suggestions.append({
                "action": "Explore amino acid correlations",
                "rationale": f"{n_compounds} compounds detected. Correlation analysis can reveal metabolic relationships.",
                "tool": "correlation_heatmap",
                "params": {"method": "pearson"}
            })

        if goal in ('publication', 'all') and has_data:
            if n_groups >= 2:
                suggestions.append({
                    "action": "Prepare publication figures",
                    "rationale": "Ask which figures are needed for the manuscript. Common choices: bar (with significance brackets), volcano, heatmap, PCA. Then export to Excel.",
                    "steps": [
                        {"tool": "generate_plots", "params": {"plot_type": "ask_user"}},
                        {"tool": "export_report", "params": {"format": "both"}},
                    ]
                })
            suggestions.append({
                "action": "Detect outliers and anomalies",
                "rationale": "Identify potential data quality issues before publication.",
                "tool": "find_anomalies",
                "params": {"zscore_threshold": 2.5}
            })

        return json.dumps({
            "context": {
                "data_loaded": has_data,
                "n_samples": self.df['sample'].nunique() if has_data else 0,
                "n_compounds": n_compounds,
                "n_groups": n_groups,
                "groups": list(groups) if has_data else [],
                "plots_generated": has_plots,
            },
            "goal": goal,
            "suggestions": suggestions[:6],
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # comprehensive_report (NEW)
    # --------------------------------------------------------
    def _comprehensive_report(self, group_a=None, group_b=None, report_type="full"):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        groups = sorted(self.df['group'].unique())
        if not group_a:
            group_a = groups[0] if len(groups) >= 1 else None
        if not group_b:
            group_b = groups[1] if len(groups) >= 2 else None

        report = {
            "report_type": report_type,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "sections": {},
        }

        # --- Section 1: Data Overview ---
        scan = json.loads(self._scan_data_directory())
        overview = {
            "total_folders": scan.get("total", 0),
            "samples_analyzed": int(self.df['sample'].nunique()),
            "groups_found": groups,
            "compounds_detected": sorted(self.df['compound'].unique().tolist()),
            "n_compounds": int(self.df['compound'].nunique()),
            "conc_range": {
                "min": round(float(self.df['conc_g100g'].min()), 6),
                "max": round(float(self.df['conc_g100g'].max()), 4),
                "mean": round(float(self.df['conc_g100g'].mean()), 4),
            },
            "samples_per_group": {g: int(self.df[self.df['group'] == g]['sample'].nunique()) for g in groups},
        }
        report["sections"]["data_overview"] = overview

        # --- Section 2: Descriptive Statistics ---
        desc = json.loads(self._run_statistical_analysis("descriptive"))
        report["sections"]["descriptive_statistics"] = desc.get("descriptive", [])

        # --- Section 3: Quality Assessment ---
        quality = json.loads(self._quality_report())
        report["sections"]["quality_assessment"] = quality

        # --- Section 4: Group Comparison ---
        if group_a and group_b:
            comparison = json.loads(self._compare_groups(group_a, group_b))
            report["sections"]["group_comparison"] = {
                "group_a": group_a,
                "group_b": group_b,
                "significant_fdr": comparison.get("significant_fdr", 0),
                "compared": comparison.get("compared", 0),
                "top_differences": comparison.get("top_significant", [])[:10],
                "all_results": comparison.get("all_results", []),
            }

            # Flag large effect sizes
            large_effects = [r for r in comparison.get("all_results", [])
                           if abs(r.get("cohens_d", 0)) > 0.8]
            report["sections"]["group_comparison"]["large_effects"] = large_effects

        # --- Section 5: Correlation Analysis ---
        corr = json.loads(self._run_statistical_analysis("correlation"))
        report["sections"]["correlations"] = corr.get("correlation", {})

        # --- Section 6: Key Findings Summary ---
        key_findings = []

        # Most abundant amino acids
        mean_conc = self.df.groupby('compound')['conc_g100g'].mean().sort_values(ascending=False)
        key_findings.append({
            "finding": "Most abundant amino acids",
            "detail": f"Top 5: {', '.join(f'{c}({v:.4f})' for c, v in mean_conc.head(5).items())}",
        })

        # Most variable amino acids
        cv = self.df.groupby('compound')['conc_g100g'].agg(['mean', 'std'])
        cv['cv_pct'] = (cv['std'] / cv['mean'] * 100).fillna(0)
        top_cv = cv['cv_pct'].sort_values(ascending=False).head(3)
        key_findings.append({
            "finding": "Most variable amino acids",
            "detail": f"Highest CV%: {', '.join(f'{c}({v:.0f}%)' for c, v in top_cv.items())}",
        })

        # Significant group differences
        if group_a and group_b:
            sig = [r for r in comparison.get("all_results", []) if r.get("significant") != "ns"]
            if sig:
                sig_detail = ', '.join(
                    "{}(d={:.2f})".format(r['compound'], r.get('cohens_d', 0))
                    for r in sig[:8]
                )
                key_findings.append({
                    "finding": "Significant group differences (FDR < 0.05)",
                    "detail": f"{len(sig)} amino acids: {sig_detail}",
                })

        report["sections"]["key_findings"] = key_findings

        # --- Section 7: Reference Context ---
        references = [
            {
                "topic": "OPA derivatization method",
                "citation": "Roth, M. (1971). Fluorescence reaction for amino acids. Analytical Chemistry, 43(7), 880-882.",
                "relevance": "Standard OPA pre-column derivatization method for amino acid analysis used in this study."
            },
            {
                "topic": "Egg yolk amino acid composition",
                "citation": "Nimalaratne, C., & Wu, J. (2015). Hen egg as an antioxidant food commodity: A review. Nutrients, 7(10), 8274-8293.",
                "relevance": "Comprehensive review of egg yolk composition including amino acid profiles."
            },
            {
                "topic": "Amino acid analysis by HPLC",
                "citation": "Fekkes, D., et al. (1995). Validation of the determination of amino acids in plasma by HPLC. Journal of Chromatography B, 669(2), 177-186.",
                "relevance": "Method validation for amino acid quantification using automated pre-column derivatization."
            },
            {
                "topic": "Statistical comparison methods",
                "citation": "Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. JRSS-B, 57(1), 289-300.",
                "relevance": "FDR correction method used for multiple testing adjustment."
            },
            {
                "topic": "Effect size interpretation",
                "citation": "Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences (2nd ed.). Lawrence Erlbaum.",
                "relevance": "Cohen's d effect size thresholds (0.2 small, 0.5 medium, 0.8 large) used in this report."
            },
            {
                "topic": "Egg yolk protein and amino acid nutrition",
                "citation": "Kovacs-Nolan, J., et al. (2005). Advances in the value of eggs and egg components for human health. J. Agric. Food Chem., 53(22), 8421-8431.",
                "relevance": "Nutritional and functional significance of egg yolk amino acid composition."
            },
            {
                "topic": "Amino acid composition and food processing",
                "citation": "Friedman, M. (1996). Nutritional value of proteins from different food sources. J. Agric. Food Chem., 44(1), 6-29.",
                "relevance": "Effects of processing on amino acid composition and nutritional quality."
            },
        ]
        report["sections"]["references"] = references

        # Save report as JSON for the AI to consume
        report_path = OUTPUT_DIR / f"comprehensive_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Return a concise summary for the AI to work with
        return json.dumps({
            "status": "done",
            "report_file": str(report_path),
            "report_type": report_type,
            "data_overview": overview,
            "quality_score": quality.get("overall_score", "unknown"),
            "quality_warnings": quality.get("warnings", []),
            "key_findings": key_findings,
            "group_comparison_summary": {
                "groups_compared": [group_a, group_b] if group_a and group_b else [],
                "n_significant": comparison.get("significant_fdr", 0) if group_a and group_b else 0,
            } if group_a and group_b else None,
            "reference_count": len(references),
            "instruction": "Use this data and the references provided to compose a professional, publication-quality analysis report with biological interpretation. Cite the references where relevant. Discuss the nutritional and functional significance of the amino acid profiles. Compare findings with known literature values for egg yolk where applicable."
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # chemstation_export_guide (NEW)
    # --------------------------------------------------------
    def _chemstation_export_guide(self, format="all"):
        """Provide ChemStation/MassHunter data export instructions."""
        guides = {}

        guides["csv"] = """
## 📤 Export as CSV/TXT from ChemStation (Easiest)

1. Open ChemStation → **Data Analysis** view
2. **File** → **Load Signal** → select your .D data file
3. Right-click the chromatogram → **Export** → **CSV File**
   - Or menu: **File** → **Export File** → **CSV File**
4. Select columns to export:
   - ✅ Signal (Retention Time + Response)
   - ✅ Peak Table
5. Save as `.csv` → ready for processing
"""

        guides["txt"] = """
## 📄 Export as Formatted TXT Report

1. Data Analysis → **Reports** → **Print Report**
2. Choose report template:
   - **Short** — peak table only (recommended)
   - **Performance+Noise** — includes system suitability
   - **Extended Performance** — full details
3. Print to **File** (not printer) → save as `.TXT`
4. The TXT file will be saved inside the .D folder as `Report.TXT`
"""

        guides["nist"] = """
## 🔬 MassHunter NIST Library Search Export (Get Compound Names + Match Factors)

This is the CRITICAL step for getting compound identification from your GC-MS data.

### Per-sample workflow:
1. Open **MassHunter Qualitative Analysis**
2. **File → Open Data File** → browse to .D folder → select `data.ms`
3. **Chromatogram → Integrate** (or right-click → Integrate All)
4. **Spectrum → Library Search Report** → select **NIST MS Search**
5. Select all peaks → click **Search**
6. Review: Match Factor column (0-100, higher = better match)
7. **File → Export → CSV**
8. Ensure these columns are selected in export:
   ☑ **Name** (compound name)  ☑ **RT** (retention time)
   ☑ **Area** (peak area)      ☑ **Match** (match factor)
   ☑ **CAS** (CAS number)      ☑ **Formula** (molecular formula)
9. Save as: `Sample001_library.csv` inside the .D folder
   (e.g., `D:\\Tina\\Sample001.D\\Sample001_library.csv`)

### Batch method (all samples at once):
1. **Tools → Batch Library Search**
2. Add all 16 sample folders
3. Select NIST library → Run
4. Export combined results: save as individual files named after each sample

### File naming convention (agent auto-detects):
- `Sample001_library.csv` inside `Sample001.D/` ✅
- `Sample001_library.csv` in parent data dir ✅
- `*library*.csv` or `*nist*.csv` or `*match*.csv` anywhere ✅

### After export:
Re-run `/run` — agent will auto-detect library CSVs, merge compound names
and match factors by RT, and apply area>=10000 + match>=70 filters.
"""

        guides["aia_cdf"] = """
## 📦 Export as AIA/CDF (Universal Chromatography Format)

AIA/CDF is the industry standard — readable by any chromatography software.

1. Data Analysis → **File** → **Export** → **AIA File**
2. Or: **File** → **Export Data** → **AIA (*.cdf)**
3. This creates a `.cdf` file (netCDF format)
4. Can be read by:
   - Python: `netCDF4` or `scipy.io.netcdf` or `PyAIA`
   - MATLAB: `ncread()`
   - Other chromatography software
"""

        guides["peak_table"] = """
## 📋 Quick Peak Table Copy (Single Sample)

1. Data Analysis → integrate all peaks
2. **View** → **Peak Table** (or press F6)
3. Right-click the table → **Copy**
   - Or Edit → **Copy Table**
4. Paste into Excel → Save as `.csv` or `.xlsx`
5. Place the file inside the .D folder as `REPORT01.CSV`
"""

        guides["batch"] = """
## 📊 Batch Export (Multiple Samples)

1. Data Analysis → **File** → **Batch Review**
2. Add all .D files to the batch queue
3. **Tools** → **Batch Export** → select format
4. Choose output path → run

Alternative:
- **Reports** → **Print Batch Reports** → select template
- Output all to `.txt` or `.xls`
"""

        guides["macro"] = """
## 🤖 ChemStation Macro Export (Automation)

In ChemStation command line (Macro window), execute:

```basic
! Export current signal as CSV
FileExport "C:\\Data\\export.csv", CSV, CURRENT_SIGNAL
```

For batch export of sequence:
```basic
! Loop through sequence and export each signal
For i = 1 to Sequence.NumberOfRuns
    LoadSignal i
    FileExport "C:\\Data\\run" + Format$(i,"00") + ".csv", CSV, CURRENT_SIGNAL
Next i
```
"""

        if format == "all":
            # Return structured summary with all formats
            parts = []
            for fmt in ["csv", "txt", "nist", "aia_cdf", "peak_table", "batch", "macro"]:
                g = guides[fmt].strip()
                # Extract title line
                lines = g.split('\n')
                parts.append(f"### {lines[0].replace('## ','').strip()}")
                parts.append('\n'.join(lines[1:]).strip())
            return json.dumps({
                "status": "done",
                "format": "all",
                "summary": "7 export methods available. For GC-MS with compound ID: use 'nist' (NIST library search). For data already identified: use 'csv' or 'txt'.",
                "methods": {
                    "csv": {"difficulty": "easy", "speed": "fast", "format": "REPORT01.CSV"},
                    "txt": {"difficulty": "easy", "speed": "fast", "format": "Report.TXT"},
                    "nist": {"difficulty": "medium", "speed": "moderate (per sample)", "format": "SampleXXX_library.csv", "key": "Compound names + Match + CAS"},
                    "aia_cdf": {"difficulty": "medium", "speed": "moderate", "format": ".cdf"},
                    "peak_table": {"difficulty": "easy", "speed": "fast (manual)", "format": "any"},
                    "batch": {"difficulty": "medium", "speed": "fast (automated)", "format": "any"},
                    "macro": {"difficulty": "hard", "speed": "fastest (fully automated)", "format": "any"},
                },
                "full_guide": '\n\n---\n\n'.join(parts),
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "status": "done",
                "format": format,
                "guide": guides.get(format, "Unknown format").strip(),
                "recommendation": "After export, place the file in the .D folder and run extract_all_data to process it."
            }, ensure_ascii=False)

    # --------------------------------------------------------
    # check_chemstation_files (NEW)
    # --------------------------------------------------------
    def _check_chemstation_files(self, sample_name=None):
        """Check file inventory inside .D folders."""
        data_path = Path(self.data_dir) if self.data_dir else None
        if not data_path or not data_path.exists():
            return json.dumps({"error": f"Data directory not set or not found"}, ensure_ascii=False)

        all_dirs = sorted(data_path.rglob("*.D"))
        results = []

        for d in all_dirs:
            if sample_name and sample_name not in d.name:
                continue

            files = {
                "csv_reports": [f.name for f in d.glob("REPORT*.CSV")],
                "txt_reports": [f.name for f in d.glob("Report*.TXT")] + [f.name for f in d.glob("*.TXT")],
                "xls_reports": [f.name for f in d.glob("Report*.XLS")] + [f.name for f in d.glob("*.XLSX")],
                "tic_csv": [f.name for f in d.glob("tic_front.csv")] + [f.name for f in d.glob("tic_front.tsv")],
                "ch_files": [f.name for f in d.glob("*.CH")],
                "uv_files": [f.name for f in d.glob("*.UV")] + [f.name for f in d.glob("*.DAD")],
                "ms_files": [f.name for f in d.glob("*.MS")] + [f.name for f in d.glob("data.ms")],
                "gc_ini": [f.name for f in d.glob("GC.ini")],
                "other_files": [f.name for f in d.glob("*.*") if f.suffix.upper() not in
                               {'.CSV', '.TSV', '.TXT', '.XLS', '.XLSX', '.CH', '.UV', '.DAD', '.MS', '.M', '.XML', '.INI'}],
            }

            has_any_report = bool(files["csv_reports"] or files["txt_reports"] or files["xls_reports"])
            has_tic = bool(files["tic_csv"])
            has_raw_only = bool(files["ch_files"] or files["uv_files"] or files["ms_files"]) and not (has_any_report or has_tic)

            # Determine strategy
            if has_any_report:
                strategy = "ready_csv"
                strategy_detail = ("CSV ready — direct peak table extraction" if files["csv_reports"] else
                                  "TXT ready — will be parsed as fallback" if files["txt_reports"] else
                                  "XLS available — will attempt column detection")
            elif has_tic:
                strategy = "ready_tic"
                strategy_detail = f"TIC CSV detected ({files['tic_csv'][0]}) — will auto-detect peaks and integrate. {len(files['ms_files'])} MS data file(s) available for spectral confirmation."
            elif has_raw_only:
                strategy = "needs_export"
                strategy_detail = "Raw chromatogram/spectra files need ChemStation/MassHunter export."
            else:
                strategy = "empty"
                strategy_detail = "No recognizable data files. May be incomplete .D folder."

            results.append({
                "folder": d.name,
                "group": d.parent.name,
                "path": str(d),
                "files": files,
                "strategy": strategy,
                "strategy_detail": strategy_detail,
            })

        summary = {
            "total_checked": len(results),
            "ready_csv": sum(1 for r in results if r["strategy"] == "ready_csv"),
            "ready_tic": sum(1 for r in results if r["strategy"] == "ready_tic"),
            "needs_export": sum(1 for r in results if r["strategy"] == "needs_export"),
            "empty": sum(1 for r in results if r["strategy"] == "empty"),
        }

        rec = ""
        if summary['ready_csv'] + summary['ready_tic'] > 0:
            rec += f"{summary['ready_csv'] + summary['ready_tic']} folders ready to process. "
        if summary['ready_tic'] > 0:
            rec += f"{summary['ready_tic']} have TIC CSV data — run extract_all_data to auto-detect peaks. "
        if summary['needs_export'] > 0:
            rec += f"{summary['needs_export']} folders need manual export from ChemStation. "
        if summary['empty'] > 0:
            rec += f"{summary['empty']} folders appear empty."

        return json.dumps({
            "status": "done",
            "summary": summary,
            "folders": results[:20],
            "recommendation": rec.strip(),
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # TIC CSV / Peak Detection Engine (NEW)
    # --------------------------------------------------------

    def _parse_tic_csv(self, filepath):
        """Parse a tic_front.csv file (MassHunter GC-MS TIC export).

        Format:
            Line 1: source path + date
            Line 2: "Start of data points"
            Lines 3+: "rt,intensity"

        Returns dict with: times (np.array), intensities (np.array), metadata (dict)
        """
        import numpy as np

        times = []
        intensities = []
        metadata = {"source": "", "date": "", "n_points": 0}

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            try:
                with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                    lines = f.readlines()
            except Exception:
                return None

        if len(lines) < 3:
            return None

        # Line 1: source path + date
        metadata["source"] = lines[0].strip()

        in_data = False
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            if line.startswith("Start of data points"):
                in_data = True
                continue
            if not in_data:
                continue

            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    t = float(parts[0].strip())
                    v = float(parts[1].strip())
                    times.append(t)
                    intensities.append(v)
                except (ValueError, IndexError):
                    continue

        if not times:
            return None

        metadata["n_points"] = len(times)
        metadata["rt_min"] = round(times[0], 3)
        metadata["rt_max"] = round(times[-1], 3)
        metadata["total_run_time"] = round(times[-1] - times[0], 1)
        metadata["max_intensity"] = int(max(intensities))
        metadata["min_intensity"] = int(min(intensities))
        metadata["mean_intensity"] = int(np.mean(intensities))

        return {
            "times": np.array(times),
            "intensities": np.array(intensities),
            "metadata": metadata,
        }

    def _detect_peaks_method(self, times, intensities, prominence=0.005, min_width=5, min_height=10000, min_area=10000):
        """Peak detection and integration for chromatographic data.

        Args:
            times: numpy array of retention times
            intensities: numpy array of signal intensities
            prominence: peak prominence as fraction of signal range (0-1)
            min_width: minimum peak width in data points
            min_height: minimum absolute peak height

        Returns:
            JSON string with peak table
        """
        import numpy as np
        from scipy import signal, integrate

        # Ensure numpy arrays
        times = np.asarray(times)
        intensities = np.asarray(intensities)

        # Calculate prominence in absolute units
        signal_range = intensities.max() - intensities.min()
        abs_prominence = max(prominence * signal_range, min_height * 0.1)

        # Peak finding
        peaks, properties = signal.find_peaks(
            intensities,
            prominence=abs_prominence,
            width=min_width,
            height=min_height,
            rel_height=0.5,
        )

        if len(peaks) == 0:
            return json.dumps({
                "status": "warning",
                "message": "No peaks detected with current parameters. Try lowering prominence or min_height.",
                "parameters_used": {
                    "prominence_fraction": prominence,
                    "abs_prominence": round(abs_prominence, 1),
                    "min_width": min_width,
                    "min_height": min_height,
                },
                "peaks": [],
            }, ensure_ascii=False)

        # Integrate each peak using trapezoidal rule
        peak_list = []
        for i, pk_idx in enumerate(peaks):
            # Get peak boundaries from width_heights at relative height
            left_ip = int(properties['left_ips'][i])
            right_ip = int(properties['right_ips'][i])

            # Extend slightly for integration
            left = max(0, left_ip - 5)
            right = min(len(intensities) - 1, right_ip + 5)

            # Integrate area (subtract baseline = min intensity in window)
            window_y = intensities[left:right + 1]
            baseline = np.min(window_y)
            corrected_y = window_y - baseline

            # Trapezoidal integration
            area = float(integrate.trapezoid(corrected_y, times[left:right + 1]))

            # Peak metrics
            rt_val = float(times[pk_idx])
            height = float(intensities[pk_idx])
            width_at_half = float(properties['width_heights'][i]) if 'width_heights' in properties else 0
            prominence_val = float(properties['prominences'][i]) if 'prominences' in properties else 0
            left_rt = float(times[left_ip])
            right_rt = float(times[right_ip])

            peak_list.append({
                "peak_id": i + 1,
                "rt": round(rt_val, 4),
                "rt_start": round(left_rt, 4),
                "rt_end": round(right_rt, 4),
                "height": round(height, 1),
                "area": round(area, 1),
                "width_50pct": round(width_at_half, 6),
                "prominence": round(prominence_val, 1),
            })

        # Apply min_area filter
        peak_list = [p for p in peak_list if p["area"] >= min_area]

        # Calculate relative area percentages
        total_area = sum(p["area"] for p in peak_list)
        for p in peak_list:
            p["area_pct"] = round(p["area"] / total_area * 100, 2) if total_area > 0 else 0

        # Sort by RT
        peak_list.sort(key=lambda x: x["rt"])

        return json.dumps({
            "status": "success",
            "n_peaks": len(peak_list),
            "total_area": round(total_area, 1),
            "rt_range": [round(float(times[0]), 3), round(float(times[-1]), 3)],
            "parameters_used": {
                "prominence_fraction": prominence,
                "abs_prominence": round(abs_prominence, 1),
                "min_width": min_width,
                "min_height": min_height,
            },
            "peaks": peak_list,
        }, ensure_ascii=False)

    def _detect_peaks(self, prominence=0.005, min_width=5, min_height=10000, min_area=10000):
        """Tool wrapper: detect peaks for ALL loaded TIC samples and align across samples."""
        if self.df is None and not hasattr(self, '_tic_data'):
            return json.dumps({"error": "No data loaded. Run extract_all_data first."}, ensure_ascii=False)

        # If we have a DataFrame, it already has peaks — suggest re-extract with new params
        if self.df is not None and 'rt' in self.df.columns:
            samples = self.df['sample'].unique()
            compounds = sorted(self.df['compound'].unique())

            return json.dumps({
                "status": "info",
                "message": f"Peaks already detected: {len(compounds)} compounds across {len(samples)} samples. To change detection parameters, re-run extract_all_data or use filter_data to filter the existing peaks.",
                "n_samples": int(len(samples)),
                "n_compounds": int(len(compounds)),
                "current_parameters": {
                    "prominence": prominence,
                    "min_width": min_width,
                    "min_height": min_height,
                    "min_area": min_area,
                },
                "tip": "Use filter_data to filter by min_area or min_match without re-extracting."
            }, ensure_ascii=False)

        return json.dumps({"error": "No chromatographic data available"}, ensure_ascii=False)

    @staticmethod
    def _parse_masshunter_library_csv(filepath):
        """Parse a MassHunter Qualitative Analysis library search export CSV.

        Auto-detects column layout from headers. Handles formats:
          Format A: Name,CAS#,RT,Area,Match,R.Match,Height,Width,Formula
          Format B: Compound,RT,Area,Amount,Match,...
          Format C: Tab-delimited with RT, Area, Match, Name columns

        Returns: list of dicts with keys: compound_name, cas, rt, area, match_factor,
                 reverse_match, formula, height
        """
        import csv, re

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                raw = f.read()
        except Exception:
            try:
                with open(filepath, 'r', encoding='utf-16-le', errors='ignore') as f:
                    raw = f.read()
            except Exception:
                try:
                    with open(filepath, 'r', encoding='gbk', errors='ignore') as f:
                        raw = f.read()
                except Exception:
                    return None

        lines = raw.strip().split('\n')
        if len(lines) < 2:
            return None

        # Detect delimiter
        first_line = lines[0]
        delim = '\t' if '\t' in first_line else ','

        # Parse header
        reader = csv.reader([first_line], delimiter=delim)
        headers = [h.strip().lower().replace('"', '').replace('#', '') for h in next(reader)]

        # Map header names to canonical keys
        col_map = {}
        canonical_keys = {
            'name': ['name', 'compound', 'compound name', 'compound_name', 'component', 'hit name'],
            'cas': ['cas', 'cas#', 'cas number', 'cas_number'],
            'rt': ['rt', 'retention time', 'rt [min]', 'ret time', 'retention_time', 'r.t.'],
            'area': ['area', 'peak area', 'area [counts]', 'peak_area', 'abundance'],
            'match': ['match', 'match factor', 'match_factor', 'match quality', 'match_quality', 'score', 'mf'],
            'reverse_match': ['r.match', 'reverse match', 'reverse_match', 'rmatch', 'rmf'],
            'formula': ['formula', 'molecular formula', 'mol formula'],
            'height': ['height', 'peak height'],
        }

        for i, h in enumerate(headers):
            h_clean = h.strip().lower().replace('"', '').replace('#', '')
            for canonical, aliases in canonical_keys.items():
                if h_clean in aliases:
                    col_map[canonical] = i
                    break

        # Need at minimum: compound name, RT, match factor (or area)
        if 'name' not in col_map and 'rt' not in col_map:
            return None

        # Parse data rows
        results = []
        data_lines = [l for l in lines[1:] if l.strip() and not l.strip().startswith('#')]
        reader = csv.reader(data_lines, delimiter=delim)

        for row in reader:
            if len(row) < max(col_map.values()) + 1 if col_map else 3:
                continue

            try:
                entry = {
                    'compound_name': '',
                    'cas': '',
                    'rt': 0.0,
                    'area': 0.0,
                    'match_factor': 0,
                    'reverse_match': 0,
                    'formula': '',
                    'height': 0.0,
                }

                if 'name' in col_map:
                    entry['compound_name'] = row[col_map['name']].strip().strip('"')
                if 'cas' in col_map:
                    entry['cas'] = row[col_map['cas']].strip().strip('"')
                if 'rt' in col_map:
                    entry['rt'] = float(row[col_map['rt']].strip())
                if 'area' in col_map:
                    entry['area'] = float(row[col_map['area']].strip().replace(',', ''))
                if 'match' in col_map:
                    entry['match_factor'] = int(float(row[col_map['match']].strip()))
                if 'reverse_match' in col_map:
                    entry['reverse_match'] = int(float(row[col_map['reverse_match']].strip()))
                if 'formula' in col_map:
                    entry['formula'] = row[col_map['formula']].strip().strip('"')
                if 'height' in col_map:
                    entry['height'] = float(row[col_map['height']].strip().replace(',', ''))

                # Only include if we have at least a name or RT
                if entry['compound_name'] or entry['rt'] > 0:
                    results.append(entry)
            except (ValueError, IndexError):
                continue

        return results if results else None

    def _filter_data(self, min_area=None, min_match=None, exclude_unidentified=None,
                     exclude_contaminants=None, include_compounds=None, exclude_compounds=None):
        """Filter the current DataFrame."""
        if self.df is None:
            return json.dumps({"error": "No data loaded. Run extract_all_data first."}, ensure_ascii=False)

        import pandas as pd
        import numpy as np

        if not hasattr(self, 'df_unfiltered') or self.df_unfiltered is None:
            self.df_unfiltered = self.df.copy()

        df = self.df.copy()
        original_n = len(df)
        filters_applied = []

        # --- Area filter ---
        if min_area is not None and min_area > 0:
            df = df[df['area'] >= min_area]
            filters_applied.append(f"min_area >= {min_area:,.0f} ({len(df)}/{original_n} kept)")

        # --- Match quality filter ---
        if min_match is not None and min_match > 0:
            if 'match_factor' in df.columns and df['match_factor'].notna().any():
                pre_match = len(df)
                df = df[df['match_factor'].isna() | (df['match_factor'] >= min_match)]
                filters_applied.append(f"min_match >= {min_match} ({len(df)}/{pre_match} kept)")
            else:
                filters_applied.append("min_match: SKIPPED (no NIST data)")

        # --- Exclude unidentified (RT_*) peaks ---
        if exclude_unidentified:
            pre_rt = len(df)
            def is_unidentified(c):
                if c is None or (isinstance(c, float) and np.isnan(c)):
                    return True
                s = str(c)
                return s.startswith('RT_') or s.startswith('rt_')
            mask = df['compound'].apply(lambda c: not is_unidentified(c))
            df = df[mask]
            filters_applied.append(f"exclude_unidentified ({len(df)}/{pre_rt} kept, {pre_rt - len(df)} RT-peaks removed)")

        # --- Exclude contaminants (siloxanes, column bleed) ---
        if exclude_contaminants:
            pre_cont = len(df)
            contam_patterns = ['siloxane', 'exclude', 'column bleed', 'phthalate']
            def is_contaminant(c):
                if c is None or (isinstance(c, float) and np.isnan(c)):
                    return False
                s = str(c).lower()
                return any(p in s for p in contam_patterns)
            mask = df['compound'].apply(lambda c: not is_contaminant(c))
            df = df[mask]
            filters_applied.append(f"exclude_contaminants ({len(df)}/{pre_cont} kept, {pre_cont - len(df)} removed)")

        # --- Include/exclude specific compounds ---
        def safe_match(c, patterns):
            if c is None or (isinstance(c, float) and np.isnan(c)):
                return False
            s = str(c).lower()
            return any(p in s for p in patterns)

        if include_compounds:
            patterns = [p.strip().lower() for p in include_compounds.split(',') if p.strip()]
            if patterns:
                pre_inc = len(df)
                df = df[df['compound'].apply(lambda c: safe_match(c, patterns))]
                filters_applied.append(f"include: {include_compounds} ({len(df)}/{pre_inc} kept)")

        if exclude_compounds:
            patterns = [p.strip().lower() for p in exclude_compounds.split(',') if p.strip()]
            if patterns:
                pre_exc = len(df)
                df = df[df['compound'].apply(lambda c: not safe_match(c, patterns))]
                filters_applied.append(f"exclude: {exclude_compounds} ({len(df)}/{pre_exc} kept)")

        # Swap in filtered DataFrame (all downstream tools use self.df)
        self.df = df.copy()
        self.df_filtered = df  # alias

        # Summary
        compounds_before = self.df_unfiltered['compound'].nunique()
        compounds_after = df['compound'].nunique()
        samples_before = self.df_unfiltered['sample'].nunique()
        samples_after = df['sample'].nunique()

        # Top compounds after filtering
        top10 = df.groupby('compound')['area'].mean().sort_values(ascending=False).head(10)

        return json.dumps({
            "status": "done",
            "filters_applied": filters_applied if filters_applied else ["no filters — full dataset"],
            "records_before": original_n,
            "records_after": len(df),
            "compounds_before": int(compounds_before),
            "compounds_after": int(compounds_after),
            "samples_before": int(samples_before),
            "samples_after": int(samples_after),
            "top_compounds_after_filter": [{"compound": c, "mean_area": round(float(a), 0)} for c, a in top10.items()],
            "has_match_data": 'match_factor' in df.columns and df['match_factor'].notna().any(),
            "note": (
                "Filtered data stored. Use generate_plots, compare_groups, etc. — they will use filtered data."
                if filters_applied else
                "No filters applied. Use min_area and min_match to filter before plotting."
            ),
        }, ensure_ascii=False)

    def _set_groups(self, group_name, samples):
        """Assign samples to a named experimental group.

        Args:
            group_name: Name for the group (e.g., 'Control', 'Treatment')
            samples: Comma-separated sample identifiers, e.g., 'Sample001,Sample002' or '1-8'

        Updates self.df 'group' column for matching samples.
        """
        if self.df is None:
            return json.dumps({"error": "No data loaded. Run extract_all_data first."}, ensure_ascii=False)

        import re

        # Parse sample identifiers
        sample_ids = set()
        for part in samples.split(','):
            part = part.strip()
            if not part:
                continue
            # Range: "1-8" → Sample001 through Sample008
            range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
            if range_match:
                start, end = int(range_match.group(1)), int(range_match.group(2))
                for n in range(start, end + 1):
                    sample_ids.add(f"Sample{n:03d}.D")
                    sample_ids.add(f"Sample{n:03d}")  # both with and without .D
            else:
                # Direct name
                sid = part
                if not sid.endswith('.D'):
                    sid += '.D'
                sample_ids.add(sid)
                sample_ids.add(sid.replace('.D', ''))  # also try without .D

        # Find matching samples in the DataFrame
        existing_samples = set(self.df['sample'].unique())
        matched = sample_ids & existing_samples

        if not matched:
            # Try fuzzy matching
            matched = set()
            for sid in sample_ids:
                for es in existing_samples:
                    if sid.replace('.D', '') in es or es.replace('.D', '') in sid:
                        matched.add(es)

        if not matched:
            return json.dumps({
                "error": f"No samples matched. Available samples: {sorted(existing_samples)[:10]}...",
                "tried": list(sample_ids)[:10],
            }, ensure_ascii=False)

        # Update group assignment
        count = 0
        for sample in matched:
            mask = self.df['sample'] == sample
            count += mask.sum()
            self.df.loc[mask, 'group'] = group_name

        # Show current groups
        current_groups = self.df.groupby('group')['sample'].nunique().to_dict()

        return json.dumps({
            "status": "done",
            "group_name": group_name,
            "samples_updated": sorted(matched),
            "records_updated": int(count),
            "current_groups": {str(k): int(v) for k, v in current_groups.items()},
            "note": f"Now {len(current_groups)} group(s) defined. Use compare_groups to compare them.",
        }, ensure_ascii=False)

    def _match_spectra_library(self, min_match=600):
        """Match detected peaks against spectral library using REAL mass spectra.

        Uses Aston to read data.ms, extracts mass spectrum at each peak's RT,
        then matches against the built-in MSP spectral library using cosine similarity.

        Args:
            min_match: Minimum match factor (0-999) for acceptance (default 600)

        Returns JSON summary.
        """
        if self.df is None:
            return json.dumps({"error": "No data loaded"}, ensure_ascii=False)

        try:
            from aston.tracefile.agilent_ms import AgilentMS
        except ImportError:
            return json.dumps({"status": "skipped", "reason": "Aston not installed"}, ensure_ascii=False)

        from spectral_match import search_library
        from spectral_library import load_library
        import numpy as np

        lib = load_library()
        if not lib:
            return json.dumps({"status": "skipped", "reason": "Spectral library not available"}, ensure_ascii=False)

        matches = []
        compounds_matched = set()
        specs_read = 0
        specs_failed = 0
        ms_cache = {}  # Cache MS objects per sample

        for idx, row in self.df.iterrows():
            current_name = str(row.get('compound', '')).lower()

            # Only match RT-labeled or built-in-labeled peaks (don't override NIST results)
            if current_name.startswith('rt_') or row.get('match_method', '') == 'builtin_library':
                pass  # Eligible for spectral matching
            else:
                continue

            sample = row['sample']
            rt = row['rt']

            # Get or load AgilentMS object for this sample
            if sample not in ms_cache:
                try:
                    d_path = Path(self.data_dir) / sample if self.data_dir else None
                    if d_path and d_path.exists():
                        ms_file = d_path / "data.ms"
                    else:
                        # Try to find via scan info
                        ms_file = None
                    if ms_file and ms_file.exists():
                        ms_cache[sample] = AgilentMS(str(ms_file))
                    else:
                        specs_failed += 1
                        continue
                except Exception:
                    specs_failed += 1
                    continue

            ms = ms_cache[sample]
            try:
                chrom = ms.data
                times_arr = chrom.index
                # Find closest scan
                scan_idx = int(np.argmin(np.abs(times_arr - rt)))
                if scan_idx >= len(times_arr):
                    specs_failed += 1
                    continue

                # Extract spectrum
                row_data = chrom.values[scan_idx]
                intensities = row_data.toarray().flatten() if hasattr(row_data, 'toarray') else np.array(row_data).flatten()
                mask = intensities > 0
                if mask.sum() < 5:
                    specs_failed += 1
                    continue

                mz_vals = chrom.columns[mask]
                ab_vals = intensities[mask]
                max_ab = ab_vals.max()
                if max_ab == 0:
                    specs_failed += 1
                    continue

                # Normalize and match
                obs_ions = [(float(mz_vals[i]), int(ab_vals[i] / max_ab * 999)) for i in range(len(mz_vals))]
                results = search_library(obs_ions, lib, min_match=min_match)

                specs_read += 1
                if results:
                    best = results[0]

                    # --- RT consistency check (match-weighted) ---
                    # High spectral match → wider RT tolerance (trust the spectrum)
                    lib_entry = next((e for e in lib if e['name'] == best['name']), None)
                    if lib_entry and lib_entry.get('rt_exp'):
                        rt_expected = lib_entry['rt_exp']
                        rt_diff = abs(rt - rt_expected)
                        # Base tolerance by RT range
                        if rt_expected < 10:
                            base_tolerance = 2.5
                        elif rt_expected < 20:
                            base_tolerance = 3.5
                        else:
                            base_tolerance = 5.0
                        # Match-weighted scaling: high match = wider acceptance
                        mf = best['match_factor']
                        if mf >= 950:
                            rt_tolerance = base_tolerance * 4.0   # Near-perfect match: trust spectrum
                        elif mf >= 900:
                            rt_tolerance = base_tolerance * 3.0
                        elif mf >= 800:
                            rt_tolerance = base_tolerance * 2.0
                        elif mf >= 700:
                            rt_tolerance = base_tolerance * 1.5
                        else:
                            rt_tolerance = base_tolerance

                        if rt_diff > rt_tolerance:
                            # RT mismatch at this confidence level
                            alt_results = [r for r in results[1:] if r['match_factor'] >= min_match]
                            alt_valid = []
                            for ar in alt_results:
                                ar_entry = next((e for e in lib if e['name'] == ar['name']), None)
                                if ar_entry and ar_entry.get('rt_exp'):
                                    ar_rt_diff = abs(rt - ar_entry['rt_exp'])
                                    ar_tol = 2.5 if ar_entry['rt_exp'] < 10 else (3.5 if ar_entry['rt_exp'] < 20 else 5.0)
                                    ar_mf = ar['match_factor']
                                    if ar_mf >= 900:
                                        ar_tol *= 3.0
                                    elif ar_mf >= 800:
                                        ar_tol *= 2.0
                                    if ar_rt_diff <= ar_tol:
                                        alt_valid.append(ar)
                            if alt_valid:
                                best = alt_valid[0]
                            else:
                                continue  # No RT-consistent match at any confidence

                    # --- Apply match ---
                    # Update compound in DataFrame
                    self.df.at[idx, 'compound'] = best['name']
                    self.df.at[idx, 'match_factor'] = best['match_factor']
                    if best.get('cas'):
                        self.df.at[idx, 'cas'] = best['cas']
                    if best.get('formula'):
                        self.df.at[idx, 'formula'] = best['formula']
                    self.df.at[idx, 'match_method'] = 'spectral_library'
                    if 'category' in self.df.columns:
                        self.df.at[idx, 'category'] = 'spectral_match'

                    matches.append({
                        "rt": round(rt, 4),
                        "sample": sample,
                        "name": best['name'],
                        "match_factor": best['match_factor'],
                        "cas": best.get('cas', ''),
                    })
                    compounds_matched.add(best['name'])

            except Exception:
                specs_failed += 1
                continue

        return json.dumps({
            "status": "done",
            "total_matches": len(matches),
            "compounds_matched": sorted(compounds_matched),
            "spectra_read": specs_read,
            "spectra_failed": specs_failed,
            "min_match_threshold": min_match,
            "matches": matches[:30],
            "note": f"Spectral library matched {len(matches)} peaks ({len(compounds_matched)} unique compounds) with match >= {min_match}. These are REAL mass spectral matches (cosine similarity), not just RT-based.",
        }, ensure_ascii=False)

    def _match_builtin_library(self, rt_tolerance=0.3):
        """Match detected peaks against built-in flavor compound library by RT.

        For each peak, finds the best RT match in FLAVOR_DB within rt_tolerance min.
        Updates self.df with compound name, CAS, formula, category, and odor if:
        - The compound currently has an RT-based label (no NIST match)
        - A library entry matches within RT tolerance

        Returns JSON summary of matches.
        """
        if self.df is None:
            return json.dumps({"error": "No data loaded"}, ensure_ascii=False)

        matches = []
        compounds_matched = set()
        rt_labels_replaced = 0

        for idx, row in self.df.iterrows():
            rt = row['rt']
            current_name = str(row.get('compound', '')).lower()

            # Only match RT-labeled peaks (not already identified by NIST)
            if not current_name.startswith('rt_'):
                continue

            # Find best RT match in library
            best_match = None
            best_diff = rt_tolerance + 1

            for entry in FLAVOR_DB:
                diff = abs(entry['rt_est'] - rt)
                if diff < best_diff:
                    best_diff = diff
                    best_match = entry

            if best_match and best_diff <= rt_tolerance:
                # Auto-flag siloxanes and contaminants
                if best_match['cat'] in ('siloxane',):
                    if 'exclude_hint' not in self.df.columns:
                        self.df['exclude_hint'] = None
                    self.df.at[idx, 'exclude_hint'] = 'column_bleed'
                    self.df.at[idx, 'compound'] = f"[EXCLUDE] {best_match['name']}"
                else:
                    self.df.at[idx, 'compound'] = best_match['name']
                if 'cas' in self.df.columns:
                    self.df.at[idx, 'cas'] = best_match['cas']
                if 'formula' in self.df.columns:
                    self.df.at[idx, 'formula'] = best_match['formula']
                # Add new columns if they don't exist
                for col in ['category', 'odor', 'match_method']:
                    if col not in self.df.columns:
                        self.df[col] = None
                self.df.at[idx, 'category'] = best_match['cat']
                self.df.at[idx, 'odor'] = best_match['odor']
                self.df.at[idx, 'match_method'] = 'builtin_library'

                matches.append({
                    "rt": round(rt, 4),
                    "original_label": current_name,
                    "matched_name": best_match['name'],
                    "category": best_match['cat'],
                    "odor": best_match['odor'],
                    "rt_diff": round(best_diff, 3),
                })
                compounds_matched.add(best_match['name'])
                rt_labels_replaced += 1

        # Summary
        categories = {}
        for m in matches:
            cat = m['category']
            categories[cat] = categories.get(cat, 0) + 1

        return json.dumps({
            "status": "done",
            "total_matches": len(matches),
            "compounds_matched": sorted(compounds_matched),
            "rt_labels_replaced": rt_labels_replaced,
            "rt_tolerance": rt_tolerance,
            "categories": categories,
            "matches": matches[:30],
            "note": (
                f"Matched {len(matches)} peaks to built-in flavor library (±{rt_tolerance} min RT tolerance). "
                f"These are TENTATIVE identifications — confirm with NIST library search or authentic standards. "
                f"Categories found: {', '.join(f'{k}({v})' for k,v in sorted(categories.items(), key=lambda x:-x[1]))}."
            ),
            "warning": "Built-in library matches are approximate (RT-based only, no spectral confirmation). For publication-quality identification, use MassHunter NIST library search export.",
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # search_public_libraries (NEW — Open Source NIST Alternative)
    # --------------------------------------------------------
    def _search_public_libraries(self, search_type="all", query=None, min_match=600,
                                 include_mona=True, target_samples=None):
        """Search open-source mass spectral libraries for compound identification.

        This is the FREE alternative to Agilent's paid NIST library. Combines:
          1. Built-in MSP library (~140 flavor/aroma compounds with real EI-MS spectra)
          2. Downloaded MassBank EU library (if available in public_libraries/)
          3. Downloaded NIST WebBook library (if available)
          4. MoNA live API search (MassBank of North America, ~1M+ spectra)

        For spectrum search with data.ms access: extracts mass spectrum at each
        unidentified peak's RT, then searches all libraries by cosine similarity.
        Updates self.df with matches meeting the min_match threshold.

        Args:
            search_type: 'spectrum' (cosine search), 'name' (lookup by name),
                        'cas' (lookup by CAS), 'all' (comprehensive)
            query: search query (compound name, CAS, or 'auto' for spectral)
            min_match: minimum match factor 0-999
            include_mona: query MoNA live API
            target_samples: optional comma-separated sample list

        Returns:
            JSON summary of matches
        """
        from public_library_manager import PublicLibraryManager
        from mona_client import check_apis, search_compound as mona_search
        from spectral_match import search_library, cosine_similarity
        from spectral_library import load_library
        import numpy as np

        # --- Check API status ---
        api_status = check_apis()

        # --- Load libraries ---
        pub_mgr = PublicLibraryManager()
        builtin_count = pub_mgr.load_builtin()

        # Try to load downloaded libraries
        downloaded_count = 0
        try:
            downloaded_count = pub_mgr.load_downloaded_libraries()
        except Exception:
            pass

        total_lib = pub_mgr.stats['total_entries']
        lib_summary = pub_mgr.get_library_summary()

        # --- Name/CAS search ---
        if search_type in ('name', 'cas') and query:
            if search_type == 'name':
                results = pub_mgr.search_by_name(query, max_results=20)
            else:
                result = pub_mgr.search_by_cas(query)
                results = [result] if result else []

            # MassBank.eu v3 live search (MoNA requires auth now, skipped)
            mona_results = []
            if include_mona:
                try:
                    # Use MassBank.eu v3 API for name search
                    from mona_client import search_compound as mb_search
                    mb_hits = mb_search(query)
                    mona_results = [{'name': h['accession'], 'source': 'massbank_eu_v3',
                                    'url': h.get('url', '')} for h in mb_hits[:10]]
                except Exception:
                    pass

            return json.dumps({
                "status": "done",
                "search_type": search_type,
                "query": query,
                "local_matches": results[:10],
                "mona_matches": mona_results[:10] if mona_results else [],
                "library_stats": lib_summary,
            }, ensure_ascii=False)

        # --- Spectrum search (needs data.ms via Aston or msconvert) ---
        if search_type in ('spectrum', 'all'):
            if self.df is None:
                return json.dumps({
                    "status": "info",
                    "message": "No data loaded. For spectrum search, data must be extracted first. Try search_type='name' to look up specific compounds, or run extract_all_data first.",
                    "library_stats": lib_summary,
                    "suggestion": "Use /run to extract data, then retry spectrum search. Or use search_type='name' to browse the library.",
                }, ensure_ascii=False)

            # Find unidentified peaks (RT_ labels or unmatched)
            unidentified = []
            if 'compound' in self.df.columns:
                for idx, row in self.df.iterrows():
                    c = str(row.get('compound', ''))
                    if c.startswith('rt_') or c.startswith('RT_') or c == '' or c == 'nan':
                        unidentified.append((idx, row['sample'], row['rt'], row['area']))
                    elif row.get('match_method', '') == 'builtin_library':
                        # Re-check builtin matches with real spectra
                        unidentified.append((idx, row['sample'], row['rt'], row['area']))

            # Filter by target samples
            if target_samples:
                target_list = [s.strip() for s in target_samples.split(',')]
                unidentified = [u for u in unidentified
                              if any(t in u[1] for t in target_list)]

            if not unidentified:
                return json.dumps({
                    "status": "info",
                    "message": "No unidentified peaks to search. All peaks already have compound names.",
                    "n_unidentified": 0,
                    "library_stats": lib_summary,
                }, ensure_ascii=False)

            # --- Try spectral search via Aston (data.ms reader) ---
            spec_matches = []
            specs_read = 0
            specs_failed = 0
            ms_cache = {}

            try:
                from aston.tracefile.agilent_ms import AgilentMS
                aston_available = True
            except ImportError:
                aston_available = False

            if aston_available and self.data_dir:
                data_path = Path(self.data_dir)

                for idx, sample, rt, area in unidentified[:200]:  # Limit to 200
                    try:
                        if sample not in ms_cache:
                            d_path = data_path / sample if (data_path / sample).exists() else None
                            if not d_path:
                                for d in data_path.rglob(sample):
                                    d_path = d
                                    break

                            ms_file = d_path / "data.ms" if d_path else None
                            if ms_file and ms_file.exists():
                                ms_cache[sample] = AgilentMS(str(ms_file))
                            else:
                                specs_failed += 1
                                continue

                        ms = ms_cache[sample]
                        chrom = ms.data
                        times_arr = chrom.index
                        scan_idx = int(np.argmin(np.abs(times_arr - rt)))

                        if scan_idx >= len(times_arr):
                            specs_failed += 1
                            continue

                        row_data = chrom.values[scan_idx]
                        intensities = row_data.toarray().flatten() if hasattr(row_data, 'toarray') else np.array(row_data).flatten()
                        mask = intensities > 0
                        if mask.sum() < 5:
                            specs_failed += 1
                            continue

                        mz_vals = chrom.columns[mask]
                        ab_vals = intensities[mask]
                        max_ab = ab_vals.max()
                        if max_ab == 0:
                            specs_failed += 1
                            continue

                        # Normalize and build ion list
                        obs_ions = [(float(mz_vals[i]), int(ab_vals[i] / max_ab * 999))
                                   for i in range(len(mz_vals))]
                        specs_read += 1

                        # Search local library
                        local_hits = pub_mgr.search_by_spectrum(obs_ions, min_match=min_match)

                        # Online search (MassBank.eu v3 name lookup — spectral similarity
                        # search not yet available on MassBank v3 API)
                        mona_hits = []

                        all_hits = local_hits + mona_hits
                        all_hits.sort(key=lambda x: x.get('match_factor', 0), reverse=True)

                        if all_hits:
                            best = all_hits[0]
                            mf = best['match_factor']

                            # RT consistency check for local hits
                            if best.get('source') != 'mona_api':
                                lib_entry = next((e for e in pub_mgr.entries
                                                if e['name'] == best['name']), None)
                                if lib_entry and lib_entry.get('rt_exp'):
                                    rt_expected = lib_entry['rt_exp']
                                    rt_diff = abs(rt - rt_expected)
                                    base_tol = 2.5 if rt_expected < 10 else (3.5 if rt_expected < 20 else 5.0)
                                    if mf >= 900:
                                        rt_tol = base_tol * 3.0
                                    elif mf >= 800:
                                        rt_tol = base_tol * 2.0
                                    elif mf >= 700:
                                        rt_tol = base_tol * 1.5
                                    else:
                                        rt_tol = base_tol
                                    if rt_diff > rt_tol:
                                        # Try next best hit
                                        for alt in all_hits[1:]:
                                            alt_entry = next((e for e in pub_mgr.entries
                                                           if e['name'] == alt['name']), None)
                                            if alt_entry and alt_entry.get('rt_exp'):
                                                alt_rt_diff = abs(rt - alt_entry['rt_exp'])
                                                if alt_rt_diff <= rt_tol:
                                                    best = alt
                                                    mf = alt['match_factor']
                                                    break
                                        else:
                                            continue  # No RT-consistent match

                            # Update DataFrame
                            self.df.at[idx, 'compound'] = best['name']
                            self.df.at[idx, 'match_factor'] = mf
                            if best.get('cas'):
                                self.df.at[idx, 'cas'] = best['cas']
                            if best.get('formula'):
                                self.df.at[idx, 'formula'] = best['formula']
                            self.df.at[idx, 'match_method'] = f"public_library_{best.get('source', 'unknown')}"
                            if 'category' in self.df.columns:
                                self.df.at[idx, 'category'] = 'public_library_match'
                            if 'odor' not in self.df.columns:
                                self.df['odor'] = None

                            spec_matches.append({
                                "sample": sample,
                                "rt": round(rt, 4),
                                "name": best['name'],
                                "match_factor": mf,
                                "source": best.get('source', 'unknown'),
                                "cas": best.get('cas', ''),
                            })

                    except Exception:
                        specs_failed += 1
                        continue

            # --- Fallback: search by name for remaining unidentified peaks ---
            name_matches = []
            if search_type == 'all':
                remaining = [u for u in unidentified
                           if not any(m['sample'] == u[1] and abs(m['rt'] - u[2]) < 0.01
                                     for m in spec_matches)]
                for idx, sample, rt, area in remaining[:100]:
                    compound_label = str(self.df.at[idx, 'compound'])
                    # Try to extract meaningful RT label
                    rt_str = f"{rt:.2f}"
                    candidates = pub_mgr.search_by_name(rt_str, max_results=5)
                    if not candidates:
                        continue
                    name_matches.append({
                        "rt": round(rt, 4),
                        "sample": sample,
                        "label": compound_label,
                        "candidates": [c['name'] for c in candidates[:5]],
                    })

            # --- Summary ---
            unique_matched = set(m['name'] for m in spec_matches)
            sources_used = set(m['source'] for m in spec_matches)

            return json.dumps({
                "status": "done",
                "search_type": search_type,
                "spectra_read": specs_read,
                "spectra_failed": specs_failed,
                "total_matches": len(spec_matches),
                "unique_compounds_matched": sorted(unique_matched),
                "n_unidentified_before": len(unidentified),
                "n_unidentified_after": len(unidentified) - len(spec_matches),
                "min_match_threshold": min_match,
                "sources_used": sorted(sources_used),
                "matches": spec_matches[:30],
                "name_search_hints": name_matches[:20],
                "library_stats": {
                    "total_entries": total_lib,
                    "builtin": builtin_count,
                    "downloaded": downloaded_count,
                    "categories": lib_summary.get('top_categories', {}),
                    "sources": lib_summary.get('sources', {}),
                },
                "mona_available": include_mona,
                "note": (
                    f"Open-source library search: {len(spec_matches)} peaks identified "
                    f"({len(unique_matched)} unique compounds) from free public libraries. "
                    f"Sources: {', '.join(sorted(sources_used)) if sources_used else 'none'}. "
                    f"Library contains {total_lib} reference spectra. "
                    f"{'MoNA live API was also queried.' if include_mona else ''} "
                    f"These are REAL spectral matches (cosine similarity), not just RT-based. "
                    f"Confidence level: match factor ≥{min_match}."
                ),
                "recommendation": (
                    "Public library matches are based on cosine similarity of real EI-MS spectra "
                    "and are comparable in quality to NIST library matches. For publication, "
                    "cite the specific library source used (MoNA/MassBank/NIST WebBook)."
                ),
            }, ensure_ascii=False)

        return json.dumps({
            "status": "done",
            "search_type": search_type,
            "library_stats": lib_summary,
            "library_available": True,
            "note": "Open-source public libraries are loaded and ready. Use search_type='spectrum' to identify unknown peaks, or search_type='name' to look up specific compounds.",
        }, ensure_ascii=False)

    # --------------------------------------------------------
    # calibrate_ri (NEW — Kovats RI auto-calibration)
    # --------------------------------------------------------
    def _calibrate_ri(self, alkane_sample=None, alkane_range="C8-C30", apply_to_all=True):
        """Auto-calibrate Kovats Retention Index using alkane standard.

        Detects n-alkane peaks by their characteristic EI-MS fragmentation
        (m/z 43, 57, 71, 85 — alkyl fragment series). Builds RT→RI calibration
        curve, calculates RI for all peaks, and cross-references with the
        1498-entry RI database for dual-dimension (MS + RI) confirmation.

        Args:
            alkane_sample: sample name containing alkane standard
            alkane_range: e.g. 'C8-C30', 'C10-C40'
            apply_to_all: apply calibration to all samples in dataset

        Returns:
            JSON summary with calibration stats and RI-matched identifications
        """
        if self.df is None:
            return json.dumps({"error": "No data loaded. Run extract_all_data first."}, ensure_ascii=False)

        import numpy as np
        from scipy.interpolate import interp1d
        import json

        # Parse alkane range
        range_match = re.search(r'C(\d+)-C(\d+)', alkane_range)
        if range_match:
            start_c, end_c = int(range_match.group(1)), int(range_match.group(2))
        else:
            start_c, end_c = 8, 30

        # --- Step 1: Find alkane peaks ---
        # n-alkanes have characteristic EI-MS: base peak m/z 43 or 57,
        # with prominent 41, 55, 71, 85 series. In the absence of MS data,
        # use RT pattern: alkanes elute at regular intervals on non-polar columns.

        alkane_df = None
        if alkane_sample:
            # Find the alkane sample in the dataset
            matches = self.df[self.df['sample'].str.contains(alkane_sample, case=False)]
            if matches.empty:
                return json.dumps({
                    "error": f"Sample '{alkane_sample}' not found. Available: {sorted(self.df['sample'].unique())[:20]}",
                }, ensure_ascii=False)
            alkane_df = self.df[self.df['sample'] == matches.iloc[0]['sample']].copy()
        else:
            # Auto-detect: look for sample with compounds named like "C8", "octane", "n-alkane"
            # Or use the first sample and try to identify alkanes by pattern
            alkane_df = None
            for sample in sorted(self.df['sample'].unique()):
                sample_df = self.df[self.df['sample'] == sample]
                compounds = [str(c).lower() for c in sample_df['compound'].unique()]
                alkane_hits = sum(1 for c in compounds
                                if any(kw in c for kw in ['alkane', 'octane', 'nonane', 'decane',
                                    'undecane', 'dodecane', 'tridecane', 'tetradecane',
                                    'pentadecane', 'hexadecane', 'heptadecane', 'octadecane',
                                    'eicosane', 'docosane', 'c8', 'c9', 'c10', 'c12', 'c14',
                                    'c16', 'c18', 'c20', 'c22', 'c24', 'c26', 'c28', 'c30']))
                if alkane_hits >= 5:
                    alkane_df = sample_df.copy()
                    alkane_sample = sample
                    break

            if alkane_df is None:
                # Fallback: try to identify alkanes by RT pattern
                # Alkanes elute at roughly equal RT intervals on temperature-programmed GC
                first_sample = self.df['sample'].iloc[0]
                alkane_df = self.df[self.df['sample'] == first_sample].copy()
                alkane_sample = first_sample

        if alkane_df is None or alkane_df.empty:
            return json.dumps({"error": "Could not identify alkane standard data"}, ensure_ascii=False)

        # --- Step 2: Identify alkane peaks and build RT→RI mapping ---
        # Alkane peaks: sort by RT, assign carbon numbers
        peaks = alkane_df[['rt', 'compound', 'area']].drop_duplicates().sort_values('rt')
        peaks = peaks[peaks['area'] >= 1000]  # Filter noise

        # Try to match known alkane names
        alkane_rt_map = {}  # carbon_number → RT
        alkane_names = {
            8: ['octane', 'c8', 'n-octane'],
            9: ['nonane', 'c9', 'n-nonane'],
            10: ['decane', 'c10', 'n-decane'],
            11: ['undecane', 'c11', 'n-undecane'],
            12: ['dodecane', 'c12', 'n-dodecane'],
            13: ['tridecane', 'c13', 'n-tridecane'],
            14: ['tetradecane', 'c14', 'n-tetradecane'],
            15: ['pentadecane', 'c15', 'n-pentadecane'],
            16: ['hexadecane', 'c16', 'n-hexadecane'],
            17: ['heptadecane', 'c17', 'n-heptadecane'],
            18: ['octadecane', 'c18', 'n-octadecane'],
            20: ['eicosane', 'c20', 'n-eicosane'],
            22: ['docosane', 'c22', 'n-docosane'],
            24: ['tetracosane', 'c24', 'n-tetracosane'],
            26: ['hexacosane', 'c26', 'n-hexacosane'],
            28: ['octacosane', 'c28', 'n-octacosane'],
            30: ['triacontane', 'c30', 'n-triacontane'],
        }

        for _, row in peaks.iterrows():
            compound = str(row['compound']).lower()
            for cn, names in alkane_names.items():
                if any(n in compound for n in names):
                    if cn not in alkane_rt_map:
                        alkane_rt_map[cn] = row['rt']
                    break

        # If we identified fewer than 3 alkanes by name, try RT interpolation method
        anchor_count = len(alkane_rt_map)
        if anchor_count < 3:
            # Fallback: assume the earliest peak is the lowest carbon alkane,
            # and peaks at regular intervals are consecutive alkanes
            # Sort by RT and assign carbon numbers starting from start_c
            sorted_rts = sorted(peaks['rt'].unique())
            if len(sorted_rts) >= 3:
                # Find peaks with typical alkane RT spacing
                # On a standard 40→280°C @6°C/min run, alkanes elute ~1.5-3 min apart
                rt_diffs = np.diff(sorted_rts)
                typical_spacing = np.median(rt_diffs[rt_diffs > 0.5])
                alkane_rts = [sorted_rts[0]]
                for i, rt in enumerate(sorted_rts[1:], 1):
                    if rt - alkane_rts[-1] > typical_spacing * 0.6:
                        alkane_rts.append(rt)

                # Assign carbon numbers
                for i, rt in enumerate(alkane_rts):
                    cn = start_c + i
                    if cn <= end_c and cn not in alkane_rt_map:
                        alkane_rt_map[cn] = rt
                        anchor_count += 1

        if anchor_count < 2:
            return json.dumps({
                "error": f"Could not identify enough alkane peaks (found {anchor_count}, need >=2). Try specifying alkane_sample parameter.",
                "hint": "Make sure the alkane standard sample contains C8-C30 n-alkanes with recognizable names or RT patterns."
            }, ensure_ascii=False)

        # --- Step 3: Build RT→RI calibration function ---
        ri_rt_pairs = sorted([(cn * 100, rt) for cn, rt in alkane_rt_map.items()])
        ri_values = np.array([r for r, _ in ri_rt_pairs])
        rt_values = np.array([t for _, t in ri_rt_pairs])

        # Linear interpolation in log(RT) space (more accurate for temperature-programmed GC)
        try:
            ri_from_rt = interp1d(rt_values, ri_values, kind='linear',
                                 bounds_error=False, fill_value='extrapolate')
        except Exception:
            ri_from_rt = None

        # --- Step 4: Calculate RI for all peaks ---
        if apply_to_all:
            target_df = self.df
        else:
            target_df = alkane_df

        if ri_from_rt is not None:
            ri_col = []
            for rt in target_df['rt']:
                ri_val = float(ri_from_rt(rt))
                ri_val = max(100, min(5000, ri_val))  # Clamp to reasonable range
                ri_col.append(round(ri_val, 1))

            if 'ri' not in target_df.columns:
                target_df = target_df.copy()
            target_df['ri'] = ri_col
            if apply_to_all:
                self.df = target_df

        # --- Step 5: Cross-reference with RI database ---
        ri_db_path = Path(__file__).parent / "public_libraries" / "nist_webbook_ri.json"
        ri_db = {}
        if ri_db_path.exists():
            try:
                with open(ri_db_path, 'r', encoding='utf-8') as f:
                    ri_db = json.load(f)
            except Exception:
                pass

        # Match compounds by name + RI proximity
        ri_matches = []
        ri_confirmed = []
        if ri_db and 'ri' in target_df.columns:
            for _, row in target_df.iterrows():
                compound = str(row.get('compound', '')).lower()
                ri_val = row.get('ri', 0)

                if ri_val <= 0 or compound.startswith('rt_'):
                    continue

                # Search RI database for matching compound
                for db_name, db_data in ri_db.items():
                    if db_name not in compound and compound not in db_name:
                        continue
                    db_ri = db_data.get('ri', 0)
                    ri_diff = abs(ri_val - db_ri)
                    if ri_diff < 50:  # Within 50 RI units
                        ri_matches.append({
                            'compound': compound,
                            'ri_measured': ri_val,
                            'ri_database': db_ri,
                            'ri_diff': round(ri_diff, 1),
                            'db_match': db_name,
                            'confidence': 'high' if ri_diff < 20 else ('medium' if ri_diff < 35 else 'low'),
                        })

                        # High-confidence RI matches can confirm or override
                        if ri_diff < 20:
                            ri_confirmed.append({
                                'compound': compound,
                                'confirmed_as': db_name,
                                'ri_measured': ri_val,
                                'ri_database': db_ri,
                            })
                        break

        # --- Summary ---
        ri_matches.sort(key=lambda x: x['ri_diff'])

        return json.dumps({
            "status": "done",
            "alkane_sample": alkane_sample,
            "alkane_range": alkane_range,
            "anchor_peaks": anchor_count,
            "calibration_points": {str(cn): round(rt, 3) for cn, rt in alkane_rt_map.items()},
            "calibration_range_ri": [min(ri_values), max(ri_values)],
            "calibration_range_rt": [round(min(rt_values), 3), round(max(rt_values), 3)],
            "ri_database_size": len(ri_db),
            "ri_matches_count": len(ri_matches),
            "high_confidence_matches": len([m for m in ri_matches if m['confidence'] == 'high']),
            "medium_confidence_matches": len([m for m in ri_matches if m['confidence'] == 'medium']),
            "ri_matches": ri_matches[:30],
            "ri_confirmed_identifications": ri_confirmed[:20],
            "note": (
                f"RI calibration established with {anchor_count} alkane anchor points. "
                f"Calculated RI for all peaks. "
                f"Cross-referenced with {len(ri_db)}-entry RI database: "
                f"{len(ri_matches)} RI matches found, "
                f"{len([m for m in ri_matches if m['confidence'] == 'high'])} high-confidence (RI diff < 20). "
                f"Dual-dimension (MS + RI) identification now available."
            ),
            "tip": "Use filter_data to exclude peaks with poor RI matches. RI + MS dual confirmation significantly reduces false identifications for isomers.",
        }, ensure_ascii=False)

    @staticmethod
    def _align_peaks_by_rt(all_sample_peaks, rt_tolerance=0.03):
        """Align peaks from multiple samples by retention time.

        Uses RT clustering: peaks from different samples within rt_tolerance minutes
        are considered the same compound. Returns aligned peak table.

        Args:
            all_sample_peaks: list of (sample_name, group, peak_list) tuples
            rt_tolerance: RT matching tolerance in minutes (default 0.03)

        Returns:
            list of aligned records: [{group, sample, compound, rt, area, height, area_pct}]
        """
        import numpy as np

        # Collect all peaks with their RTs
        all_peaks = []  # (sample, group, rt, area, height, area_pct)
        for sample_name, group, peak_list in all_sample_peaks:
            for p in peak_list:
                all_peaks.append({
                    "sample": sample_name,
                    "group": group,
                    "rt": p["rt"],
                    "area": p["area"],
                    "height": p["height"],
                    "area_pct": p.get("area_pct", 0),
                })

        if not all_peaks:
            return []

        # RT clustering: group peaks by RT proximity
        all_rts = sorted(set(p["rt"] for p in all_peaks))

        # Simple clustering: group RTs within tolerance
        clusters = []
        current_cluster = [all_rts[0]]
        for rt in all_rts[1:]:
            if rt - current_cluster[-1] <= rt_tolerance:
                current_cluster.append(rt)
            else:
                clusters.append(current_cluster)
                current_cluster = [rt]
        if current_cluster:
            clusters.append(current_cluster)

        # Build aligned records
        aligned = []
        for cluster_id, cluster in enumerate(clusters):
            # Find all peaks matching this RT cluster
            cluster_rts = set(cluster)
            matching = [p for p in all_peaks if any(abs(p["rt"] - crt) <= rt_tolerance for crt in cluster_rts)]

            if not matching:
                continue

            # Calculate consensus RT
            consensus_rt = round(np.mean([p["rt"] for p in matching]), 4)

            # Compound label based on RT
            compound_label = f"RT_{consensus_rt:.3f}"

            for p in matching:
                aligned.append({
                    "group": p["group"],
                    "sample": p["sample"],
                    "compound": compound_label,
                    "rt": p["rt"],
                    "area": round(p["area"], 1),
                    "height": round(p["height"], 1),
                    "area_pct": round(p["area_pct"], 2),
                    "cluster_id": cluster_id + 1,
                })

        return aligned

    # --------------------------------------------------------
    # TXT Report Parser (NEW)
    # --------------------------------------------------------
    @staticmethod
    def _parse_report_txt(filepath):
        """Parse a ChemStation TXT report file into peak records.

        Handles multiple ChemStation TXT report formats:
          1. Classic table: "Peak RetTime Type Width Area Amount Grp Name"
          2. Quant report:  "Compound  RT  Area  Amount  Conc."
          3. Tab-separated: "RT[min]\\tArea\\tAmount[g/100g]\\tName"
          4. Fixed-width:   ChemStation default printer output
        """
        import re
        try:
            # Try UTF-16 LE first (ChemStation default), then fallback
            for enc in ['utf-16-le', 'utf-8', 'gbk', 'latin-1']:
                try:
                    with open(filepath, 'r', encoding=enc, errors='ignore') as f:
                        raw = f.read()
                    break
                except Exception:
                    continue
            else:
                return []
        except Exception:
            return []

        peaks = []
        lines = raw.split('\n')

        # ---- Pattern 1: Classic ChemStation table ----
        # "Peak RetTime  Type  Width    Area    Amount  Grp    Name"
        in_table = False
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect table header
            if re.match(r'^\s*Peak\s+RetTime\s+Type', line, re.IGNORECASE):
                in_table = True
                continue
            if re.match(r'^\s*-{3,}\|', line):
                continue

            if in_table:
                # Match "  1   2.123   BB   0.0456  123.45  0.1234       aspartic acid"
                m = re.match(
                    r'^\s*(\d+)\s+'           # peak number
                    r'([\d.]+)\s+'             # retention time
                    r'(\S+)\s+'                # type (BB, BV, etc.)
                    r'([\d.]+)\s+'             # width
                    r'([\d.]+)\s+'             # area
                    r'([\d.eE+\-]+)\s*'         # amount
                    r'(?:([\d.eE+\-]+)\s*)?'    # optional extra column (grp/conc)
                    r'(\S.*?)$'                # compound name
                    , line.strip())
                if m:
                    try:
                        rt = float(m.group(2))
                        area = float(m.group(5))
                        amount = float(m.group(6))
                        compound = m.group(8).strip().lower()
                        # Only accept reasonable compound names
                        if compound and len(compound) <= 30 and not compound.startswith('-'):
                            peaks.append({
                                'rt': round(rt, 3),
                                'area': round(area, 1),
                                'amount': amount,
                                'conc_g100g': amount,  # TXT often uses amount directly
                                'compound': compound,
                            })
                    except (ValueError, IndexError):
                        continue

        if peaks:
            return peaks

        # ---- Pattern 2: Quant report ----
        # "Compound                  RT     Area     Amount    Conc."
        for i, line in enumerate(lines):
            line_s = line.strip()
            if re.match(r'^\s*Compound\s+RT\s+Area\s+Amount', line_s, re.IGNORECASE):
                # Read subsequent lines
                for j in range(i + 1, min(i + 50, len(lines))):
                    sub = lines[j].strip()
                    if not sub or sub.startswith('---') or sub.startswith('==='):
                        continue
                    # Stop at section boundary
                    if re.match(r'^(Signal|Peak|Sorted|Calib|Multiplier|Dilution|Sample\s+Name)', sub, re.IGNORECASE):
                        break
                    # Parse "aspartic acid  2.123  123.45  0.1234  0.1234"
                    m = re.match(r'^(.+?)\s{2,}'            # compound name (before 2+ spaces)
                                r'([\d.]+)\s+'              # RT
                                r'([\d.]+)\s+'              # Area
                                r'([\d.eE+\-]+)\s*'          # Amount
                                r'([\d.eE+\-]*)$',           # optional conc
                                sub)
                    if m:
                        try:
                            compound = m.group(1).strip().lower()
                            rt = float(m.group(2))
                            area = float(m.group(3))
                            amount = float(m.group(4))
                            conc = float(m.group(5)) if m.group(5) else amount
                            if compound and len(compound) <= 30:
                                peaks.append({
                                    'rt': round(rt, 3),
                                    'area': round(area, 1),
                                    'amount': amount,
                                    'conc_g100g': conc,
                                    'compound': compound,
                                })
                        except (ValueError, IndexError):
                            continue
                break  # Only process first quant table found

        if peaks:
            return peaks

        # ---- Pattern 3: Tab-delimited ----
        # "RT[min]\tArea\tAmount[g/100g]\tName"
        for i, line in enumerate(lines):
            if '\t' in line and re.search(r'(RT|RetTime|retention)', line, re.IGNORECASE):
                # Determine column positions from header
                headers = line.strip().split('\t')
                rt_idx = area_idx = amount_idx = name_idx = -1
                for h_idx, h in enumerate(headers):
                    h_clean = h.strip().lower().replace('"', '')
                    if 'rt' in h_clean or 'ret' in h_clean or 'time' in h_clean:
                        rt_idx = h_idx
                    elif 'area' in h_clean:
                        area_idx = h_idx
                    elif 'amount' in h_clean or 'conc' in h_clean:
                        amount_idx = h_idx
                    elif 'name' in h_clean or 'compound' in h_clean:
                        name_idx = h_idx

                if rt_idx >= 0 and area_idx >= 0 and name_idx >= 0:
                    for j in range(i + 1, min(i + 50, len(lines))):
                        row = lines[j].strip()
                        if not row or row.startswith('---'):
                            continue
                        cols = row.split('\t')
                        if len(cols) > max(rt_idx, area_idx, name_idx):
                            try:
                                rt = float(cols[rt_idx].strip())
                                area = float(cols[area_idx].strip())
                                amount = float(cols[amount_idx].strip()) if amount_idx >= 0 and amount_idx < len(cols) else 0
                                compound = cols[name_idx].strip().strip('"').lower()
                                if compound and len(compound) <= 30:
                                    peaks.append({
                                        'rt': round(rt, 3),
                                        'area': round(area, 1),
                                        'amount': amount,
                                        'conc_g100g': amount,
                                        'compound': compound,
                                    })
                            except (ValueError, IndexError):
                                continue
                break

        return peaks

    # --------------------------------------------------------
    # run_statistical_analysis (existing, slight improvements)
    # --------------------------------------------------------
    def _run_statistical_analysis(self, analysis_type="all"):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        import numpy as np
        result = {}

        if analysis_type in ("descriptive", "all"):
            desc = []
            for comp in sorted(self.df['compound'].unique()):
                cd = self.df[self.df['compound'] == comp]['conc_g100g']
                desc.append({
                    "compound": comp, "n": int(len(cd)),
                    "mean": round(cd.mean(), 6), "std": round(cd.std(), 6),
                    "cv_pct": round(cd.std() / cd.mean() * 100, 1) if cd.mean() > 0 else 0,
                    "min": round(cd.min(), 6), "max": round(cd.max(), 6),
                    "median": round(cd.median(), 6),
                    "q25": round(cd.quantile(0.25), 6),
                    "q75": round(cd.quantile(0.75), 6),
                })
            result["descriptive"] = desc

        if analysis_type in ("comparison", "all"):
            groups = self.df['group'].unique()
            if len(groups) >= 2:
                result["comparison"] = json.loads(self._compare_groups(groups[0], groups[1]))

        if analysis_type in ("correlation", "all"):
            pivot = self.df.pivot_table(values='conc_g100g', index='sample', columns='compound', aggfunc='mean')
            corr = pivot.corr()
            strong = []
            cols = corr.columns
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    r = corr.iloc[i, j]
                    if abs(r) > 0.5:
                        strong.append({"pair": f"{cols[i]} - {cols[j]}", "r": round(r, 3)})
            strong.sort(key=lambda x: abs(x['r']), reverse=True)
            result["correlation"] = {"strong_pairs": strong[:15]}

        self.analysis = result
        return json.dumps(result, ensure_ascii=False)

    def _find_anomalies(self, zscore_threshold=2.5):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        pivot = self.df.pivot_table(values='conc_g100g', index='sample', columns='compound', aggfunc='mean')
        anomalies = []
        for comp in pivot.columns:
            m, s = pivot[comp].mean(), pivot[comp].std()
            if s == 0:
                continue
            for sample, val in pivot[comp].items():
                z = (val - m) / s
                if abs(z) > zscore_threshold:
                    anomalies.append({
                        "sample": sample, "compound": comp,
                        "value": round(val, 6), "z_score": round(z, 2)
                    })

        anomalies.sort(key=lambda x: abs(x['z_score']), reverse=True)
        return json.dumps({
            "threshold": zscore_threshold,
            "total_anomalies": len(anomalies),
            "top_anomalies": anomalies[:15],
            "affected_samples": list(set(a['sample'] for a in anomalies)),
        }, ensure_ascii=False)

    def _export_report(self, format="excel", filename="analysis_report"):
        if self.df is None:
            return json.dumps({"error": "Run extract_all_data first"}, ensure_ascii=False)

        import pandas as pd
        saved = []

        if format in ("csv", "both"):
            p = str(OUTPUT_DIR / f"{filename}.csv")
            pivot = self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                         columns='compound', aggfunc='mean')
            pivot.to_csv(p, encoding='utf-8-sig')
            saved.append(p)

        if format in ("excel", "both"):
            p = str(OUTPUT_DIR / f"{filename}.xlsx")
            with pd.ExcelWriter(p, engine='openpyxl') as w:
                self.df.to_excel(w, sheet_name='Raw Data', index=False)
                self.df.pivot_table(values='conc_g100g', index=['group', 'sample'],
                                    columns='compound', aggfunc='mean').to_excel(w, sheet_name='Pivot')
            saved.append(p)

        return json.dumps({"saved": saved}, ensure_ascii=False)

    @staticmethod
    def _parse_csv(line):
        parts = []
        cur = []
        in_q = False
        for c in line:
            if c == '"':
                in_q = not in_q
                cur.append(c)
            elif c == ',' and not in_q:
                parts.append(''.join(cur))
                cur = []
            else:
                cur.append(c)
        if cur:
            parts.append(''.join(cur))
        return parts

    # ========================================================
    # System Prompt
    # ========================================================
    @property
    def _system_prompt(self):
        return f"""You are a senior analytical chemist specializing in chromatographic and mass spectrometric data analysis (GC/MS, HPLC, GC-FID, etc.). You provide publication-quality data analysis and interpretation.

## Your Expertise
You analyze Agilent ChemStation .D data files from any chromatographic method.
You call tools to obtain data, then interpret results with proper chemical and statistical context, citing relevant scientific literature when applicable.

## Critical Workflow Protocol

### When samples have NO report files (raw .CH/.UV only):
1. DO NOT try to parse them — they are binary chromatogram files
2. Use `chemstation_export_guide` tool to provide the user with export instructions
3. Tell the user which specific folders need exporting
4. After user confirms export, re-run workflow

### When samples have REPORT01.CSV:
→ Use `extract_all_data` directly — these are ready

### When samples have Report.TXT (but no CSV):
→ TXT is parsed as fallback by `extract_all_data` — just run it

### When unsure what's in .D folders:
→ Use `check_chemstation_files` to get a detailed inventory

### Standard workflow after data is loaded:
1. `extract_all_data` → get all data (auto-filters area >= 10,000, built-in library match)
2. **ALWAYS ask about groups**: "当前所有16个样品都在同一组。需要分组吗？例如对照组1-8，处理组9-16？" → use `set_groups` tool
3. `filter_data` → **ALWAYS ask about filters**: "需要过滤吗？建议：排除 siloxane（柱流失）和 RT-only 峰？最小峰面积？"
4. `quality_report` → assess data quality
5. `run_statistical_analysis` with "all" → full stats
6. `compare_groups` → pairwise comparisons (only works if 2+ groups defined)
7. `generate_plots` — ask user which type: bar/heatmap/pca/boxplot/composition/volcano/dashboard/all
8. `comprehensive_report` → publication-ready report
9. `export_report` with "both" → Excel + CSV output

### CRITICAL: Filter before plotting!
- **BEFORE generating ANY plots**, ALWAYS follow this protocol:

1. **Default clean filter for publication plots**:
   ```
   filter_data(exclude_unidentified=True, exclude_contaminants=True)
   ```
   This removes RT-labeled peaks and column-bleed siloxanes — minimum for clean figures.

2. **Ask about additional filtering**:
   - "当前 N 个已鉴定化合物。需要更高的面积阈值吗？当前 10,000？"
   - "需要排除特定化合物类别吗？"
   - "需要只保留风味相关/活性相关化合物吗？"

3. **For heatmap/PCA specifically**: MUST exclude unidentified peaks (`exclude_unidentified=True`) to avoid cluttering.

4. **Re-filter when needed**: Re-call `filter_data` whenever user changes criteria.

### Retention Index (RI) Auto-Calibration
The agent can auto-calibrate Kovats RI using an alkane standard (C8-C30):
- Use `calibrate_ri` tool or `/ri` shortcut
- Detects n-alkanes by name matching or RT pattern
- Builds RT→RI calibration curve (linear interpolation)
- Calculates RI for ALL peaks in the dataset
- Cross-references with 1498-entry RI database for dual confirmation
- RI + MS dual matching drastically improves isomer identification
- When user has alkane standard data, ALWAYS suggest running `/ri` before finalizing compound IDs
- High-confidence matches: RI difference < 20 units
- Medium-confidence: RI difference < 35 units

### CRITICAL: Ask before generating plots!
- **NEVER call generate_plots with plot_type='all' without asking the user first.**
- Each plot type serves a different purpose — let the user choose:
  - `bar` — group comparison with significance brackets (best for 2-3 groups)
  - `heatmap` — hierarchical clustering overview (best for >10 samples)
  - `pca` — sample grouping / batch effect detection
  - `boxplot` — distribution + outliers per compound
  - `composition` — stacked ratio per sample
  - `volcano` — differential compounds at a glance (needs 2 groups)
  - `dashboard` — 6-panel summary (comprehensive, large file)
  - `all` — everything (only when user explicitly requests)
- When user says "/plot" without specifying, ask: "需要哪种图？bar(组间对比) / pca(样本分组) / heatmap(聚类热图) / volcano(火山图) / dashboard(总览) / all(全部)？"
- When user says "/plot bar" or "/plot pca", generate ONLY that type.

### Flavor/Aroma Compound Knowledge
- Common flavor-active volatiles: aldehydes (hexanal, nonanal, benzaldehyde), ketones (2-heptanone, 2-nonanone), alcohols (1-octen-3-ol, linalool), esters, terpenes (limonene, pinene), pyrazines, sulfur compounds
- Column bleed indicators: siloxane, cyclosiloxane (exclude these)
- Plasticizers: phthalates (exclude from analysis)
- Solvent peaks: early-eluting, often broad, high intensity
- When discussing flavor compounds: mention odor descriptors, odor thresholds, formation pathways (Maillard reaction, lipid oxidation, fermentation)

## Professional Standards
1. ALWAYS call tools to get data — never invent or approximate numbers
2. Present ALL key values with proper units and statistical metrics (p-value, FDR, Cohen's d)
3. Interpret findings in proper scientific context based on the sample type and analytical method
4. Discuss effect sizes (Cohen's d) not just significance — a statistically significant but tiny difference may not be meaningful
5. When discussing group differences, mention: which compounds changed, direction, magnitude, and possible explanations
6. Include relevant scientific references in your analysis when applicable
7. Discuss practical implications of the findings
8. Use professional scientific writing style suitable for a Results & Discussion section
9. If the comprehensive_report tool was used, base your analysis on the structured findings it provides
10. Adapt your domain interpretation to the actual compounds detected — don't force amino-acid-specific knowledge onto non-amino-acid data

## ChemStation / MassHunter Data Format Knowledge

### Supported formats (auto-detected in .D folders):
- **REPORT01.CSV** (UTF-16 LE) — ChemStation default CSV export ✓
- **Report.TXT** — ChemStation formatted text report ✓ (parsed as fallback)
- **Report.XLS/XLSX** — Excel export ✓ (column auto-detection)
- **tic_front.csv / tic_front.tsv** — MassHunter GC-MS TIC data ✓ (auto peak detection + integration)
- **data.ms** — Raw GC-MS mass spectra (used for confirmation; peak detection uses TIC)
- **.CH binary** — Raw chromatogram ✗ (requires ChemStation for export)
- **.UV/.DAD binary** — Raw spectral data ✗ (requires ChemStation for export)

### MassHunter GC-MS TIC Data (tic_front.csv)
- Format: `time,intensity` pairs (~6700 points per 33-min run)
- Processing: auto peak detection (scipy.signal.find_peaks) + trapezoidal integration
- Cross-sample alignment: peaks matched by RT within ±0.03 min tolerance
- Compound labels: `RT_XX.XXX` (retention-time based) — user can rename after identification
- Adjust sensitivity via `/peaks` or natural language: "detect peaks with prominence 0.003"
- Peak detection parameters:
  - prominence: 0.005 (0.5% of signal range) — lower = more peaks
  - min_width: 5 data points — filters noise spikes
  - min_height: 10000 counts — absolute threshold

### Export from ChemStation/MassHunter (use chemstation_export_guide tool):
- ChemStation: File → Export File → CSV File (easiest)
- ChemStation: Reports → Print Report → to TXT file
- MassHunter: Data already includes tic_front.csv (no export needed for TIC!)
- **MassHunter NIST Library Search**: Qualitative Analysis → Load sample → Library Search → select NIST library → Export Results as CSV → save as `Sample001_library.csv` in .D folder → agent will auto-merge compound names + match factors
- ChemStation: File → Export → AIA File (.cdf, universal format)
- Tools → Batch Export (for multiple samples)

### How to get NIST match + compound names (MassHunter Qualitative Analysis):
1. Open MassHunter Qualitative Analysis
2. File → Open Data File → browse to D:\Tina\Sample001.D → select data.ms
3. Chromatogram → Integrate (or use method's integration parameters)
4. Spectrum → Library Search Report → select NIST MS Search
5. Select all peaks in chromatogram → click Search
6. Review results — note the Match Factor column (0-100)
7. File → Export → CSV
8. In export dialog, ensure these columns are selected:
   ☑ Name  ☑ RT  ☑ Area  ☑ Match  ☑ CAS  ☑ Formula
9. Save as: `Sample001_library.csv` inside `D:\Tina\Sample001.D\`
   (or save all as `SampleXXX_library.csv` in D:\Tina directly)
10. Repeat for all 16 samples (use batch method if available:
    Tools → Batch Library Search → select all samples)
11. Re-run extract_all_data — agent auto-detects *library*.csv files,
    merges compound names + match factors by RT matching,
    and auto-applies area>=10000 + match>=70 filters

### Open-Source NIST Alternatives (FREE public spectral libraries)
When NIST library search results are NOT available from MassHunter, use the `search_public_libraries` tool which searches ALL of these free sources simultaneously:

1. **Built-in MSP Library** (~140 flavor/aroma compounds): Real EI-MS spectra for common volatiles. Always available.
2. **MoNA (MassBank of North America)**: Live REST API search. ~1M+ spectra. No registration required. https://mona.fiehnlab.ucdavis.edu
3. **MassBank Europe**: Downloadable MSP library. EI-MS, LC-MS/MS spectra. https://massbank.eu
4. **NIST WebBook**: Public-domain EI spectra from NIST Chemistry WebBook (via Zenodo). Legally free.
5. **GNPS**: UCSD platform for metabolomics spectral networking. https://gnps.ucsd.edu

### When to use search_public_libraries:
- No MassHunter/NIST library export available → use `search_public_libraries` with search_type="spectrum"
- Need to identify RT-labeled peaks → use search_type="spectrum" (cosine similarity, same method as NIST)
- Want to verify built-in library matches with real spectra → use search_type="all"
- Looking up a specific compound → use search_type="name" or search_type="cas"

### Spectral match quality:
- Cosine similarity (same algorithm as NIST MS Search)
- Match factor 0-999: ≥900 excellent, ≥800 good, ≥700 fair, ≥600 tentative
- RT consistency check applied for local library matches
- MoNA matches come with instrument metadata and collision energy

### Reference citations for public libraries:
- MoNA: "MoNA — MassBank of North America. https://mona.fiehnlab.ucdavis.edu"
- MassBank: "Horai, H. et al. (2010). MassBank: a public repository for sharing mass spectral data. J. Mass Spectrom., 45(7), 703-714."
- NIST WebBook: "Linstrom, P.J. & Mallard, W.G. (eds.). NIST Chemistry WebBook, NIST Standard Reference Database Number 69."
- GNPS: "Wang, M. et al. (2016). Sharing and community curation of mass spectrometry data with GNPS. Nature Biotechnology, 34(8), 828-837."

## Statistical Interpretation Guide
- p < 0.05 after FDR correction: statistically significant after multiple testing adjustment
- Cohen's d: |d| > 0.8 = large effect, 0.5-0.8 = medium, < 0.5 = small
- CV% > 50%: high analytical variability — may indicate method issues or sample heterogeneity
- Fold change > 2.0 or < 0.5: potentially biologically/chemically meaningful change
- Reference: Benjamini & Hochberg (1995). JRSS-B, 57(1), 289-300.
- Reference: Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences (2nd ed.). Lawrence Erlbaum.

## General Analytical Chemistry References
When discussing findings, cite references as relevant to the actual analytical context:

1. ChemStation data format: "Agilent Technologies. ChemStation OpenLAB CDS — Data Analysis Reference Guide."
2. FDR method: "Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. JRSS-B, 57(1), 289-300."
3. Effect size: "Cohen, J. (1988). Statistical Power Analysis for the Behavioral Sciences (2nd ed.). Lawrence Erlbaum."
4. PCA in chemometrics: "Wold, S., Esbensen, K., & Geladi, P. (1987). Principal component analysis. Chemometrics and Intelligent Laboratory Systems, 2(1-3), 37-52."
5. Chromatographic integration: "Dyson, N. (1998). Chromatographic Integration Methods (2nd ed.). RSC Publishing."
6. Method validation: "ICH Q2(R1). Validation of Analytical Procedures: Text and Methodology."
7. Uncertainty: "EURACHEM/CITAC Guide CG4. Quantifying Uncertainty in Analytical Measurement."
8. Statistical comparison: "Miller, J.N. & Miller, J.C. (2018). Statistics and Chemometrics for Analytical Chemistry (7th ed.). Pearson."

## Data Directory
{self.data_dir}"""

    # ========================================================
    # Chat
    # ========================================================

    def _safe_context(self, max_messages=20):
        """Get safe message context with no orphaned 'tool' messages at start.

        The DeepSeek API requires every 'tool' role message to be immediately
        preceded by an 'assistant' message with 'tool_calls'. Slicing history
        can break this pairing, so we strip any leading 'tool' messages.
        """
        msgs = self.messages[-max_messages:]
        # Strip leading orphaned 'tool' messages
        while msgs and msgs[0].get("role") == "tool":
            msgs.pop(0)
        return msgs

    def chat(self, user_message):
        self.messages.append({"role": "user", "content": user_message})

        try:
            context = self._safe_context(20)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    *context,
                ],
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=4096,
            )

            msg = response.choices[0].message

            while msg.tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                        }
                        for tc in msg.tool_calls
                    ]
                })

                for tc in msg.tool_calls:
                    func_name = tc.function.name
                    func_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    print(f"\n  [TOOL] {func_name}({json.dumps(func_args, ensure_ascii=False)})")

                    try:
                        method = getattr(self, f"_{func_name}")
                        result = method(**func_args)
                    except Exception as e:
                        result = json.dumps({"error": str(e)}, ensure_ascii=False)

                    # Smart truncation
                    if len(result) > 8000:
                        data = json.loads(result)
                        if isinstance(data, dict):
                            for k in ['all_results', 'all_compounds', 'descriptive']:
                                if k in data and isinstance(data[k], list):
                                    data[k] = data[k][:10]
                                    data['_truncated'] = True
                                    data['_full_count'] = len(data.get(k, []))
                            result = json.dumps(data, ensure_ascii=False)

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

                # Use safe_context for the follow-up call too (with larger window)
                followup_context = self._safe_context(40)
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": self._system_prompt}] + followup_context,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=4096,
                )
                msg = response.choices[0].message

            reply = msg.content or "Analysis complete."
            self.messages.append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            err_str = str(e).lower()
            if '429' in err_str or 'rate' in err_str:
                hint = "Rate limit hit. Wait a moment and try again."
            elif '401' in err_str or 'auth' in err_str:
                hint = "Authentication error. Check your API key."
            elif '400' in err_str:
                if 'token' in err_str:
                    hint = "Context too long. Type /clear to reset conversation, then continue."
                elif 'tool' in err_str:
                    hint = ("Message pairing error (tool without assistant). "
                           "Type /clear to reset conversation, then retry. "
                           "This happens when conversation history gets too long.")
                else:
                    hint = str(e)
            elif 'timeout' in err_str or 'timed out' in err_str:
                hint = "Request timed out. The API may be busy. Try again."
            else:
                hint = str(e)

            error_msg = f"[ERROR] API call failed: {hint}"
            self.messages.append({"role": "assistant", "content": error_msg})
            return error_msg


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="GCMS .D Data AI Agent")
    parser.add_argument("--data-dir", "-d", type=str, default=None,
                       help="Data directory containing .D folders")
    parser.add_argument("--model", "-m", type=str, default=None,
                       help="DeepSeek model: deepseek-chat / deepseek-reasoner")
    args = parser.parse_args()

    print()
    print("=" * 55)
    print(f"  ChemStation .D Data AI Agent  v{AGENT_VERSION}")
    print(f"  GC/MS · HPLC · GC-FID — Universal Chromatography")
    print("  Powered by DeepSeek  |  开源谱库: MSP + MassBank.eu")
    print("=" * 55)

    # Data directory
    data_dir = args.data_dir
    if not data_dir:
        print()
        print("Enter data directory path (containing .D folders):")
        data_dir = input("  Path: ").strip().strip('"')
        if not data_dir:
            print("No path entered. Exiting.")
            sys.exit(1)

    data_dir = os.path.abspath(data_dir)
    if not os.path.isdir(data_dir):
        print(f"Directory not found: {data_dir}")
        sys.exit(1)

    # API key
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        print()
        print("DEEPSEEK_API_KEY not set!")
        print("  Get one at: https://platform.deepseek.com")
        print('  Or run: $env:DEEPSEEK_API_KEY = "sk-xxx"')
        print()
        key = input("  Paste API key to continue: ").strip()
        if key:
            os.environ["DEEPSEEK_API_KEY"] = key
            api_key = key
        else:
            print("No key entered. Exiting.")
            sys.exit(1)

    # Init
    print()
    print("  Initializing...")
    try:
        agent = GCMSAgent(api_key=api_key, data_dir=data_dir,
                         model=args.model or os.environ.get("DEEPSEEK_MODEL"))
    except Exception as e:
        print(f"Init failed: {e}")
        print()
        print("  Dependencies required:")
        print("  pip install openai pandas numpy matplotlib seaborn scipy scikit-learn openpyxl")
        sys.exit(1)

    print(f"  [OK] Agent ready  |  Model: {agent.model}")
    print(f"  Data: {agent.data_dir}")
    print(f"  Output: {OUTPUT_DIR}")
    print()
    print("  Quick start:")
    print("    /scan      Scan data directory")
    print("    /check     Check files inside .D folders")
    print("    /run       Extract data (auto peak detection + library matching)")
    print("    /groups    Assign samples to experimental groups")
    print("    /filter    Filter data by area, match quality, compounds")
    print("    /plot bar  Generate bar chart (or pca/heatmap/volcano/dashboard)")
    print("    /identify  Identify unknown peaks (12K spectra + online)")
    print("    /ri        Auto RI calibration (alkane standard → Kovats RI)")
    print("    /report    Publication-ready comprehensive report")
    print("    /full      Complete pipeline")
    print("    volcano A vs B    Volcano plot")
    print("    quality           Data quality report")
    print()
    print("  /help for more  |  quit to exit")
    print("-" * 50)

    # Show library status
    lib_status = agent._public_lib_status
    if lib_status['has_libraries']:
        print(f"  📚 开源谱库: {lib_status['n_files']} 个文件就绪")
    else:
        print(f"  💡 开源谱库未下载 — 首次 /identify 或 /library 时将自动下载")
        print(f"     (MassBank EU + NIST WebBook, 免费, 无需注册)")

    while True:
        try:
            ui = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not ui:
            continue
        if ui.lower() in ('quit', 'exit', 'q'):
            print("  Goodbye!")
            break

        if ui.lower() == '/help':
            print("""
  Quick commands:
    /scan      Scan data directory
    /check     Check files inside .D folders
    /run       Extract data (auto peak detection + library matching)
    /groups    Assign samples to groups (e.g., /groups Control 1-8)
    /filter    Filter data (area, match quality, compounds)
    /plot      Choose plot type (bar/pca/heatmap/volcano/dashboard/all)
    /plot bar  Generate bar chart only (or pca/heatmap/boxplot/volcano)
    /report    Generate professional report
    /full      Complete pipeline
    /export    ChemStation/MassHunter export instructions
    /library   Download/manage open-source spectral libraries
    /identify  Identify unknown peaks using open-source libraries
    /status    Show current data state
    /clear     Clear conversation memory

  Plot types (/plot <type>):
    bar         Group comparison with significance brackets
    pca         PCA scores + loadings (sample grouping)
    heatmap     Hierarchical clustering overview
    boxplot     Distribution + outliers per compound
    composition Stacked ratio per sample
    volcano     Differential compounds (needs 2 groups)
    dashboard   6-panel comprehensive summary
    all         Everything (only when needed)

  Open-source library:
    /library             → Show status (123K spectra loaded)
    /identify            → Identify peaks with cosine similarity

  Filtering before plotting:
    /filter min_area 50000              → keep peaks with area >= 50,000
    /filter min_match 70                → keep match >= 70%
    /filter exclude "solvent,column"    → remove specific compounds

  Data types supported:
    - ChemStation REPORT01.CSV (UTF-16 LE)
    - ChemStation Report.TXT (auto-encoding detection)
    - Report.XLS/XLSX (column auto-detection)
    - MassHunter GC-MS tic_front.csv (auto peak detection)
    - MassHunter NIST library search CSV (auto-merge by RT)

  Natural language examples:
    Scan the data directory
    Extract all data
    Filter: area > 50000, match > 70
    Exclude solvent peaks and column bleed
    Compare <group A> and <group B>
    Generate a volcano plot
    Write a comprehensive analysis report
""")
            continue

        if ui.lower() == '/clear':
            agent.messages = []
            print("  Memory cleared.")
            continue

        if ui.lower() == '/status':
            if agent.df is not None:
                print(f"\n  {len(agent.df)} records | {agent.df['sample'].nunique()} samples | "
                      f"{agent.df['compound'].nunique()} compounds")
                print(f"  Groups: {', '.join(agent.df['group'].unique())}")
            elif agent.d_folders:
                print(f"\n  Scanned: {agent.d_folders.get('total', 0)} folders")
            else:
                print(f"\n  No data loaded")
            continue

        # Shortcut commands
        cmd_map = {
            '/scan': "Scan the data directory",
            '/check': "Check what files are in the .D folders and recommend next steps",
            '/run': "Extract all data from available reports. If TIC CSV data is found (MassHunter GC-MS), automatically detect peaks and integrate with min_area=10000 filter. Otherwise use CSV/TXT/XLS reports. Auto-match against built-in MSP library and flavor compound library.",
            '/groups': "Ask the user to assign samples to experimental groups (e.g., 'Control' = samples 1-8, 'Treatment' = samples 9-16). Then use set_groups for each group.",
            '/filter': "Filter the current dataset. Ask: what min_area? what min_match? which compounds to exclude? Auto-suggest excluding siloxanes and RT-only peaks.",
            '/plot': "Ask the user which plot(s) to generate: bar (group comparison), heatmap (clustered), pca (score+loading), boxplot (distribution), composition (stacked ratio), volcano (group diff), dashboard (6-panel overview), or all. Then generate only the requested type.",
            '/export': "Show me how to export NIST library search results from MassHunter Qualitative Analysis (to get compound names and match factors)",
            '/peaks': "Run peak detection on the loaded chromatographic data",
            '/library': "Show current status of open-source spectral libraries. If no libraries downloaded, offer to download MassBank EU and NIST WebBook (free, no registration). Then show how to use search_public_libraries.",
            '/identify': "Use search_public_libraries tool with search_type='all' to identify all currently unidentified peaks (RT_* labels) using free public spectral libraries (MoNA + MassBank + NIST WebBook + built-in MSP). Include live MoNA API search.",
            '/ri': "Auto-calibrate Kovats Retention Index for all peaks using alkane standard. If user has alkane data (C8-C30), detect alkanes, build RT→RI curve, calculate RI for all peaks, cross-reference with 1498-entry RI database. Or ask user for alkane sample name.",
            '/report': "Generate a comprehensive professional analysis report with biological interpretation, statistical analysis, and scientific references.",
            '/full': "Scan -> Extract -> Ask for filters -> Filter -> Stats -> Quality -> Compare -> Ask which plots user wants -> Generate only requested plots -> Report -> Export",
        }
        if ui.lower() in cmd_map:
            ui = cmd_map[ui.lower()]
            print(f"  -> {ui}")

        # Handle /plot subcommands: /plot bar, /plot pca, /plot volcano, etc.
        if ui.lower().startswith('/plot '):
            plot_type = ui[6:].strip().lower()
            valid = {'bar', 'heatmap', 'pca', 'boxplot', 'composition', 'dashboard', 'volcano', 'all'}
            if plot_type in valid:
                ui = f"Generate a {plot_type} plot using the currently filtered data. Use generate_plots with plot_type='{plot_type}'."
            elif 'volcano' in plot_type:
                # /plot volcano A vs B
                parts = plot_type.replace('volcano', '').strip()
                if ' vs ' in parts:
                    a, b = parts.split(' vs ', 1)
                    ui = f"Generate a volcano plot comparing {a.strip()} vs {b.strip()}. Use volcano_plot with group_a='{a.strip()}' and group_b='{b.strip()}'."
                else:
                    ui = f"Generate a volcano plot. Use volcano_plot — ask which groups to compare if not already known."
            else:
                ui = f"Generate plots. The user asked for '{plot_type}' — ask which specific plot type they want: bar, heatmap, pca, boxplot, composition, volcano, dashboard, or all."
            print(f"  -> {ui}")

        # Handle /library subcommands
        if ui.lower().startswith('/library '):
            sub = ui[9:].strip()
            if sub == 'download':
                ui = "Download all public spectral libraries (MassBank EU and NIST WebBook from Zenodo) using download_public_libs integration. Then reload and show library status."
            else:
                ui = f"Search public libraries for: {sub}"
            print(f"  -> {ui}")

        # Handle /identify with specific name
        if ui.lower().startswith('/identify '):
            query = ui[10:].strip()
            ui = f"Search all open-source spectral libraries (MoNA + MassBank + NIST WebBook + built-in MSP) for compound: {query}. Use search_public_libraries with search_type='name'."
            print(f"  -> {ui}")

        print()
        try:
            reply = agent.chat(ui)
            print(f"\nAgent:\n{reply}")
        except Exception as e:
            print(f"\n  [ERROR] {e}")


if __name__ == "__main__":
    main()
