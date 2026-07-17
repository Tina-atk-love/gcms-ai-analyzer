#!/usr/bin/env python3
"""
GC-MS AI Analyzer — Open-Source NIST Alternative
==================================================
One-command installation for the GC-MS AI Analyzer.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme = Path(__file__).parent / 'README.md'
long_description = readme.read_text(encoding='utf-8') if readme.exists() else ''

# Core dependencies
install_requires = [
    'numpy>=1.24',
    'pandas>=2.0',
    'matplotlib>=3.7',
    'seaborn>=0.12',
    'scipy>=1.10',
    'scikit-learn>=1.3',
    'plotly>=5.15',
    'streamlit>=1.25',
    'openai>=1.0',
    'openpyxl>=3.1',
    'python-docx>=0.8',
    'urllib3>=2.0',
]

# Optional: spectral data readers
extras_require = {
    'spectra': ['matchms>=0.33'],
    'all': ['matchms>=0.33'],
}

setup(
    name='gcms-ai-analyzer',
    version='3.5.0',
    description='Open-Source NIST Alternative — AI-Powered GC-MS Data Analysis',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='GC-MS AI Analyzer Contributors',
    url='https://github.com/Tina-atk-love/gcms-ai-analyzer',
    license='MIT',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'Topic :: Scientific/Engineering :: Chemistry',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
    ],
    python_requires='>=3.10',
    packages=find_packages(include=['tools', 'tools.*']),
    py_modules=[],
    install_requires=install_requires,
    extras_require=extras_require,
    entry_points={
        'console_scripts': [
            'gcms-analyzer=gcms_agent:main_cli',
        ],
    },
    include_package_data=True,
)
