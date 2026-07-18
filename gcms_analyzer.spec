# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for GC-MS AI Analyzer
Build with: pyinstaller gcms_analyzer.spec
"""

import sys
from pathlib import Path

ROOT = Path('.').absolute()

a = Analysis(
    ['launcher.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ('app.py', '.'),
        ('gcms_agent.py', '.'),
        ('flavor_tools.py', '.'),
        ('spectral_match.py', '.'),
        ('spectral_match_fast.py', '.'),
        ('deconvolution.py', '.'),
        ('public_library_manager.py', '.'),
        ('spectral_library.py', '.'),
        ('core_utils.py', '.'),
        ('workflow_tools.py', '.'),
        ('quantitation.py', '.'),
        ('identification_engine.py', '.'),
        ('mass_spectra_reader.py', '.'),
        ('requirements.txt', '.'),
        ('tools/demo_data.py', 'tools'),
        ('tools/advanced_peak_detection.py', 'tools'),
        ('tools/interactive_viz.py', 'tools'),
        ('.streamlit/config.toml', '.streamlit'),
    ],
    hiddenimports=[
        'streamlit',
        'streamlit.runtime',
        'streamlit.runtime.scriptrunner',
        'streamlit.web',
        'pandas',
        'numpy',
        'matplotlib',
        'plotly',
        'plotly.express',
        'scipy',
        'scipy.signal',
        'scipy.sparse',
        'scipy.sparse.linalg',
        'scipy.stats',
        'scipy.interpolate',
        'scipy.ndimage',
        'sklearn',
        'sklearn.decomposition',
        'sklearn.preprocessing',
        'sklearn.ensemble',
        'openpyxl',
        'docx',
        'openai',
        'seaborn',
        'PIL',
        'requests',
        'urllib3',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'IPython',
        'jupyter',
        'notebook',
        'sqlalchemy',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GCMS-AI-Analyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'icon.ico') if (ROOT / 'icon.ico').exists() else None,
)
