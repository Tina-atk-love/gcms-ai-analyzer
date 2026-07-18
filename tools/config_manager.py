#!/usr/bin/env python3
"""
Configuration Manager — Auto-Save/Restore user settings
=========================================================
Saves API keys, NIST paths, data paths, and preferences
to a local JSON file. Auto-loads on app start.

File: .gcms_user_config.json (in project root, gitignored)
"""

import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / '.gcms_user_config.json'

DEFAULTS = {
    'api_key': '',
    'nist_path': '',
    'nist_mode': 'NIST .L Folder (Recommended)',
    'nist_loaded': False,
    'data_dir': '',
    'language': 'en',
    'last_data_dirs': [],
    'filter_min_area': 10000,
    'filter_min_match': 0,
    'filter_exclude_unidentified': True,
    'filter_exclude_contaminants': True,
}


def load_config():
    """Load saved configuration. Returns dict with defaults for missing keys."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
            # Merge with defaults
            cfg = DEFAULTS.copy()
            cfg.update(data)
            return cfg
        except Exception:
            pass
    return DEFAULTS.copy()


def save_config(cfg_dict):
    """Save configuration to file."""
    # Don't save the actual API key if it's empty
    to_save = {k: v for k, v in cfg_dict.items()
               if k in DEFAULTS or k.startswith('nist_') or k.startswith('filter_')}
    # Filter out None values and empty containers
    clean = {}
    for k, v in to_save.items():
        if v is None:
            continue
        if isinstance(v, (list, dict, str)) and not v:
            continue
        clean[k] = v
    CONFIG_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding='utf-8')


def delete_config():
    """Delete saved configuration."""
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
