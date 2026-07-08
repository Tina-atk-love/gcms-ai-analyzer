#!/usr/bin/env python3
"""
Workflow Tools: RT Alignment + Analysis Templates
==================================================
1. RT Drift Correction — align retention times across batches/runs
2. Analysis Templates — save/load/share analysis workflow configurations

Both are essential for production-grade GC-MS data processing.
"""

import json
import os
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict


# ================================================================
# RT Drift Correction
# ================================================================
def detect_rt_drift(df, reference_batch=1, batch_col='batch', sample_col='sample',
                    compound_col='compound', rt_col='rt'):
    """Detect retention time drift across batches.

    Uses common compounds (present in all batches) as internal RT standards
    to measure systematic RT shift.

    Args:
        df: DataFrame with batch and RT columns
        reference_batch: batch number to use as reference
        batch_col, sample_col, compound_col, rt_col: column names

    Returns:
        dict with drift statistics per batch and per compound
    """
    batches = sorted(df[batch_col].unique())
    if len(batches) < 2:
        return {'status': 'single_batch', 'message': 'Only one batch, no drift to correct'}

    # Find compounds present in ALL batches
    batch_compounds = {}
    for b in batches:
        batch_compounds[b] = set(df[df[batch_col] == b][compound_col].unique())

    common = batch_compounds[batches[0]]
    for b in batches[1:]:
        common = common & batch_compounds[b]

    if len(common) < 3:
        return {
            'status': 'insufficient_common',
            'n_common': len(common),
            'message': f'Only {len(common)} compounds present in all batches — need >= 3 for reliable alignment'
        }

    # Calculate RT drift per compound per batch vs reference
    drift_data = []
    ref_rt = {}
    ref_df = df[df[batch_col] == reference_batch]

    for comp in common:
        ref_vals = ref_df[ref_df[compound_col] == comp][rt_col]
        if ref_vals.empty:
            continue
        ref_rt[comp] = ref_vals.mean()

    for b in batches:
        if b == reference_batch:
            continue
        bdf = df[df[batch_col] == b]
        shifts = []
        for comp in common:
            if comp not in ref_rt:
                continue
            b_vals = bdf[bdf[compound_col] == comp][rt_col]
            if b_vals.empty:
                continue
            shift = float(b_vals.mean() - ref_rt[comp])
            shifts.append(shift)

        drift_data.append({
            'batch': int(b),
            'mean_shift_min': round(float(np.mean(shifts)), 4),
            'std_shift_min': round(float(np.std(shifts)), 4),
            'max_shift_min': round(float(max(abs(s) for s in shifts)), 4),
            'n_compounds_used': len(shifts),
            'direction': 'later' if np.mean(shifts) > 0 else 'earlier',
        })

    overall_max = max(d['max_shift_min'] for d in drift_data) if drift_data else 0
    severity = 'severe' if overall_max > 1.0 else 'moderate' if overall_max > 0.1 else 'minimal'

    return {
        'status': 'done',
        'reference_batch': reference_batch,
        'n_common_compounds': len(common),
        'n_batches_corrected': len(drift_data),
        'drift_per_batch': drift_data,
        'max_overall_shift_min': round(overall_max, 4),
        'severity': severity,
        'recommendation': (
            'Drift is negligible. No correction needed.'
            if severity == 'minimal' else
            'Moderate drift detected. Consider RT alignment for quantitative comparison.'
            if severity == 'moderate' else
            'Severe RT drift! Alignment strongly recommended before any cross-batch analysis.'
        ),
    }


def correct_rt_drift(df, reference_batch=1, batch_col='batch', compound_col='compound',
                     rt_col='rt', area_col='area', min_common=3):
    """Correct retention time drift by aligning all batches to the reference.

    Uses a LOWESS/linear interpolation model: for each batch, fits RT_shift vs RT
    using common compounds as anchor points, then applies the correction.

    Args:
        df: DataFrame
        reference_batch: batch number to align everything to
        (other params as above)

    Returns:
        DataFrame with 'rt_corrected' column added
    """
    result = df.copy()
    result['rt_corrected'] = result[rt_col]

    batches = sorted(df[batch_col].unique())
    if len(batches) < 2:
        return result

    # Find common compounds
    batch_compounds = {}
    for b in batches:
        batch_compounds[b] = set(df[df[batch_col] == b][compound_col].unique())

    common = batch_compounds[batches[0]]
    for b in batches[1:]:
        common = common & batch_compounds[b]

    if len(common) < min_common:
        return result

    # Reference RTs
    ref_rt = {}
    ref_df = df[df[batch_col] == reference_batch]
    for comp in common:
        ref_vals = ref_df[ref_df[compound_col] == comp][rt_col]
        if not ref_vals.empty:
            ref_rt[comp] = ref_vals.mean()

    # Correct each batch
    for b in batches:
        if b == reference_batch:
            continue

        bmask = result[batch_col] == b
        anchors_rt = []
        anchors_shift = []

        for comp in common:
            if comp not in ref_rt:
                continue
            b_vals = df[bmask & (df[compound_col] == comp)][rt_col]
            if b_vals.empty:
                continue
            anchors_rt.append(b_vals.mean())
            anchors_shift.append(ref_rt[comp] - b_vals.mean())

        if len(anchors_rt) < 3:
            continue

        # Fit shift vs RT: linear model (simple but effective)
        anchors_rt = np.array(anchors_rt)
        anchors_shift = np.array(anchors_shift)

        coeffs = np.polyfit(anchors_rt, anchors_shift, 1)
        correction = np.polyval(coeffs, result.loc[bmask, rt_col].values)
        result.loc[bmask, 'rt_corrected'] = result.loc[bmask, rt_col] + correction

    return result


# ================================================================
# Analysis Template System
# ================================================================

TEMPLATE_DIR = Path(__file__).parent / "templates"

DEFAULT_TEMPLATE = {
    "name": "default",
    "description": "Default GC-MS analysis template",
    "version": 1,
    "created": "",
    "filters": {
        "min_area": 10000,
        "min_match": 0,
        "exclude_unidentified": True,
        "exclude_contaminants": True,
        "include_compounds": "",
        "exclude_compounds": "siloxane,phthalate,column bleed"
    },
    "identification": {
        "search_mode": "hybrid",
        "min_match": 600,
        "use_ri": True,
        "use_nist": False,
        "use_mona": True
    },
    "statistics": {
        "anova_alpha": 0.05,
        "posthoc_method": "tukey",
        "min_replicates": 2
    },
    "plots": {
        "default_types": ["bar", "heatmap", "pca", "volcano"],
        "dpi": 300,
        "figure_width": 8,
        "significance_brackets": True
    },
    "export": {
        "formats": ["excel", "csv"],
        "include_raw_data": True,
        "include_stats": True
    }
}

PRESET_TEMPLATES = {
    "flavor_analysis": {
        "name": "flavor_analysis",
        "description": "Flavor & aroma compound analysis with OAV calculation",
        "version": 1,
        "created": "",
        "filters": {
            "min_area": 5000,
            "min_match": 0,
            "exclude_unidentified": True,
            "exclude_contaminants": True,
            "include_compounds": "",
            "exclude_compounds": "siloxane,phthalate,column bleed"
        },
        "identification": {
            "search_mode": "hybrid",
            "min_match": 600,
            "use_ri": True,
            "use_nist": False,
            "use_mona": True
        },
        "statistics": {
            "anova_alpha": 0.05,
            "posthoc_method": "tukey",
            "min_replicates": 2
        },
        "plots": {
            "default_types": ["bar", "heatmap", "pca", "volcano", "flavor_wheel"],
            "dpi": 300,
            "figure_width": 8,
            "significance_brackets": True
        },
        "export": {
            "formats": ["excel", "word", "html"],
            "include_raw_data": True,
            "include_stats": True,
            "include_oav": True
        },
        "auto_actions": ["calculate_oav", "tag_pathways", "off_flavor_check"]
    },
    "metabolomics": {
        "name": "metabolomics",
        "description": "Untargeted metabolomics profiling",
        "version": 1,
        "created": "",
        "filters": {
            "min_area": 5000,
            "min_match": 0,
            "exclude_unidentified": False,
            "exclude_contaminants": True,
            "include_compounds": "",
            "exclude_compounds": "siloxane,phthalate"
        },
        "identification": {
            "search_mode": "hybrid",
            "min_match": 500,
            "use_ri": True,
            "use_nist": False,
            "use_mona": True
        },
        "statistics": {
            "anova_alpha": 0.05,
            "posthoc_method": "tukey",
            "min_replicates": 3
        },
        "plots": {
            "default_types": ["pca", "plsda", "heatmap", "volcano", "rf_importance"],
            "dpi": 300,
            "figure_width": 10,
            "significance_brackets": False
        },
        "export": {
            "formats": ["excel", "csv"],
            "include_raw_data": True,
            "include_stats": True
        },
        "auto_actions": ["run_plsda", "run_random_forest", "run_anova"]
    },
    "pesticide_residue": {
        "name": "pesticide_residue",
        "description": "Pesticide residue screening with MRM-style verification",
        "version": 1,
        "created": "",
        "filters": {
            "min_area": 1000,
            "min_match": 700,
            "exclude_unidentified": True,
            "exclude_contaminants": True,
            "include_compounds": "",
            "exclude_compounds": "siloxane,phthalate,fatty acid"
        },
        "identification": {
            "search_mode": "hybrid",
            "min_match": 700,
            "use_ri": True,
            "use_nist": True,
            "use_mona": False
        },
        "statistics": {
            "anova_alpha": 0.05,
            "posthoc_method": "tukey",
            "min_replicates": 2
        },
        "plots": {
            "default_types": ["bar", "volcano"],
            "dpi": 300,
            "figure_width": 8,
            "significance_brackets": True
        },
        "export": {
            "formats": ["excel", "word"],
            "include_raw_data": True,
            "include_stats": True
        },
        "auto_actions": ["subtract_blank", "normalize_istd"]
    },
    "environmental": {
        "name": "environmental",
        "description": "Environmental sample analysis (water/soil/air)",
        "version": 1,
        "created": "",
        "filters": {
            "min_area": 3000,
            "min_match": 600,
            "exclude_unidentified": False,
            "exclude_contaminants": True,
            "include_compounds": "",
            "exclude_compounds": "siloxane,phthalate"
        },
        "identification": {
            "search_mode": "hybrid",
            "min_match": 600,
            "use_ri": True,
            "use_nist": True,
            "use_mona": True
        },
        "statistics": {
            "anova_alpha": 0.05,
            "posthoc_method": "games_howell",
            "min_replicates": 3
        },
        "plots": {
            "default_types": ["bar", "pca", "heatmap", "volcano"],
            "dpi": 300,
            "figure_width": 10,
            "significance_brackets": True
        },
        "export": {
            "formats": ["excel", "csv"],
            "include_raw_data": True,
            "include_stats": True
        },
        "auto_actions": ["subtract_blank", "quality_report"]
    }
}


def save_template(name, config, template_dir=None):
    """Save an analysis template to disk.

    Args:
        name: template name (used as filename)
        config: dict with template configuration
        template_dir: directory (default: ./templates/)

    Returns:
        dict with status and file path
    """
    tdir = Path(template_dir) if template_dir else TEMPLATE_DIR
    tdir.mkdir(parents=True, exist_ok=True)

    config['name'] = name
    config['version'] = config.get('version', 1)
    config['created'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    filepath = tdir / f'{name}.json'
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return {'status': 'saved', 'file': str(filepath), 'name': name}


def load_template(name, template_dir=None):
    """Load a saved analysis template.

    Args:
        name: template name (without .json extension)
        template_dir: directory

    Returns:
        template dict, or default template if not found
    """
    # Check presets first
    if name in PRESET_TEMPLATES:
        return PRESET_TEMPLATES[name]

    tdir = Path(template_dir) if template_dir else TEMPLATE_DIR
    filepath = tdir / f'{name}.json'

    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    return DEFAULT_TEMPLATE


def list_templates(template_dir=None):
    """List all available templates (presets + saved)."""
    templates = {}

    # Presets
    for name, cfg in PRESET_TEMPLATES.items():
        templates[name] = {
            'name': name,
            'description': cfg['description'],
            'type': 'preset',
            'created': cfg.get('created', 'built-in'),
        }

    # Saved
    tdir = Path(template_dir) if template_dir else TEMPLATE_DIR
    if tdir.exists():
        for f in sorted(tdir.glob('*.json')):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    cfg = json.load(fp)
                name = cfg.get('name', f.stem)
                templates[name] = {
                    'name': name,
                    'description': cfg.get('description', ''),
                    'type': 'saved',
                    'created': cfg.get('created', ''),
                    'file': str(f),
                }
            except Exception:
                pass

    return templates


def apply_template(agent, template_name, template_dir=None):
    """Apply a template to the agent's current state.

    Loads the template and applies its settings (filters, etc.) to the agent.

    Args:
        agent: GCMSAgent instance
        template_name: name of template to apply
        template_dir: directory

    Returns:
        dict with applied actions
    """
    tmpl = load_template(template_name, template_dir)
    applied = []

    # Apply filters
    filters = tmpl.get('filters', {})
    if filters and agent.df is not None:
        agent._filter_data(
            min_area=filters.get('min_area', 10000),
            min_match=filters.get('min_match', 0),
            exclude_unidentified=filters.get('exclude_unidentified', True),
            exclude_contaminants=filters.get('exclude_contaminants', True),
            include_compounds=filters.get('include_compounds', ''),
            exclude_compounds=filters.get('exclude_compounds', ''),
        )
        applied.append('filters_applied')

    # Run auto actions
    for action in tmpl.get('auto_actions', []):
        try:
            method = getattr(agent, f'_{action}', None)
            if method:
                method()
                applied.append(f'action:{action}')
        except Exception:
            pass

    return {
        'status': 'applied',
        'template': template_name,
        'description': tmpl.get('description', ''),
        'actions_applied': applied,
    }


def generate_workflow_script(agent, template_name, data_dir, output_dir=None):
    """Generate a standalone Python script that reproduces the analysis.

    Creates a .py file that, when run, will reproduce the entire analysis
    workflow — useful for publication reproducibility and sharing methods.

    Args:
        agent: GCMSAgent instance
        template_name: template to use
        data_dir: data directory path
        output_dir: output directory

    Returns:
        dict with script path
    """
    tmpl = load_template(template_name)
    script_path = f'workflow_{template_name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.py'

    lines = [
        '#!/usr/bin/env python3',
        f'# Auto-generated analysis workflow: {template_name}',
        f'# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        f'# Template: {tmpl.get("description", "")}',
        '',
        'import os, json',
        'from gcms_agent import GCMSAgent',
        '',
        f"agent = GCMSAgent(data_dir=r'{data_dir}')",
        '',
        '# Load data',
        f"agent._extract_all_data(r'{data_dir}')",
        '',
    ]

    # Sample renaming (if available)
    if hasattr(agent, '_sample_labels') and agent._sample_labels:
        mapping = ','.join(f'{k}={v}' for k, v in agent._sample_labels.items())
        lines.append(f'# Rename samples')
        lines.append(f"agent._rename_samples('{mapping}')")
        lines.append('')

    # Groups (if available)
    if hasattr(agent, '_group_assignments') and agent._group_assignments:
        lines.append('# Assign groups')
        for sample, group in agent._group_assignments.items():
            lines.append(f"agent._set_groups('{group}', '{sample}')")
        lines.append('')

    # Filters
    f = tmpl.get('filters', {})
    lines.append('# Apply filters')
    lines.append(f"agent._filter_data(min_area={f.get('min_area',10000)}, "
                 f"exclude_unidentified={f.get('exclude_unidentified',True)}, "
                 f"exclude_contaminants={f.get('exclude_contaminants',True)})")
    lines.append('')

    # Auto actions
    for action in tmpl.get('auto_actions', []):
        lines.append(f'agent._{action}()  # auto-action from template')
    lines.append('')

    # Plots
    lines.append('# Generate plots')
    for pt in tmpl.get('plots', {}).get('default_types', ['bar', 'pca']):
        if pt == 'volcano':
            lines.append('# agent._volcano_plot(group_a="Group1", group_b="Group2")')
        elif pt == 'flavor_wheel':
            lines.append("agent._flavor_wheel(title='Flavor Profile')")
        elif pt == 'plsda':
            lines.append('agent._run_plsda()')
        elif pt == 'rf_importance':
            lines.append('agent._run_random_forest()')
        else:
            lines.append(f"agent._generate_plots(plot_type='{pt}')")
    lines.append('')

    lines.append("print('Workflow complete!')")

    with open(script_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    return {'status': 'generated', 'script': script_path, 'note': f'Run: python {script_path}'}


# ================================================================
# CLI Test
# ================================================================
if __name__ == "__main__":
    print("Workflow Tools — unit tests")
    print("=" * 50)

    # Test template listing
    templates = list_templates()
    print(f'Templates available: {len(templates)}')
    for name, info in templates.items():
        print(f'  {name:25s} [{info["type"]}] {info["description"]}')

    # Test RT drift detection on synthetic data
    print()
    print('RT drift test (synthetic):')
    import pandas as pd
    np.random.seed(42)
    data = []
    for b in [1, 2]:
        for s in range(4):
            for c in ['A', 'B', 'C', 'D', 'E']:
                rt = np.random.uniform(5, 20) + (b - 1) * 0.15  # 0.15 min drift
                data.append({'batch': b, 'sample': f'S{s}', 'compound': c,
                           'rt': rt, 'area': np.random.uniform(1000, 10000)})
    test_df = pd.DataFrame(data)
    drift = detect_rt_drift(test_df)
    print(f'  Status: {drift["status"]}, Severity: {drift.get("severity","?")}')
    if drift.get('drift_per_batch'):
        for d in drift['drift_per_batch']:
            print(f'  Batch {d["batch"]}: mean shift={d["mean_shift_min"]:.4f} min')

    corrected = correct_rt_drift(test_df)
    print(f'  RT corrected column: {"rt_corrected" in corrected.columns}')

    print()
    print('Module ready.')
