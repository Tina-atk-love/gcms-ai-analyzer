#!/usr/bin/env python3
"""
NIST WebBook EI-MS Spectrum Downloader
=======================================
Downloads free EI-MS spectra from the NIST Chemistry WebBook
(https://webbook.nist.gov/chemistry/). These are legally free
and can be used without a NIST license.

The WebBook contains EI-MS spectra for thousands of common compounds.
This tool downloads them and saves as JCAMP/MSP format for use with
the gcms_analyzer spectral search.

Usage:
  python tools/download_nist_webbook_spectra.py --max 5000

This closes the EI-MS gap — combined with MassBank (139K MS2) and
MoNA (1M+), we get comprehensive spectral coverage without needing
to decode the NIST .L binary format.
"""

import os
import sys
import json
import time
import re
import ssl
from pathlib import Path
from urllib.request import urlopen, Request, ProxyHandler, build_opener, install_opener
from urllib.parse import quote
from urllib.error import HTTPError, URLError

# Setup SSL context that doesn't verify (for networks with SSL inspection)
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

# Setup proxy if available
PROXY_URL = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY') or 'http://127.0.0.1:7897'
if PROXY_URL:
    proxy_handler = ProxyHandler({'https': PROXY_URL, 'http': PROXY_URL})
    opener = build_opener(proxy_handler)
    install_opener(opener)


# NIST WebBook base URL
WEBBOOK_BASE = "https://webbook.nist.gov/cgi/cbook.cgi"

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "public_libraries" / "nist_webbook"


def search_compound(name):
    """Search NIST WebBook for a compound by name. Returns list of (name, formula, cas, url)."""
    url = f"{WEBBOOK_BASE}?Name={quote(name)}&Units=SI"
    try:
        req = Request(url, headers={'User-Agent': 'GCMS-AI-Analyzer/3.5'})
        with urlopen(req, timeout=30, context=ssl_ctx) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"  HTTP error for '{name}': {e}")
        return []

    results = []
    # Parse search results table
    # Pattern: <li><a href="?ID=C...&amp;Units=SI">Compound Name</a>
    pattern = re.compile(
        r'<li><a\s+href="(\?ID=[^"]+?)">([^<]+)</a>.*?'
        r'<li><strong>Formula:</strong>\s*<!\[CDATA\[([^\]]+)\]\]>',
        re.DOTALL
    )
    for match in pattern.finditer(html):
        href = match.group(1)
        title = match.group(2).strip()
        formula = match.group(3).strip()
        cas_match = re.search(r'(\d{2,7}-\d{2}-\d)', html[match.start():match.start()+500])
        cas = cas_match.group(1) if cas_match else ''
        results.append({
            'name': title,
            'formula': formula,
            'cas': cas,
            'url': f"{WEBBOOK_BASE}{href}&Units=SI",
        })

    return results


def get_mass_spectrum(compound_url):
    """Download EI-MS spectrum from compound page. Returns list of (mz, intensity) pairs."""
    try:
        req = Request(compound_url + "&Type=IR-SPEC&Index=0",
                      headers={'User-Agent': 'GCMS-AI-Analyzer/3.5'})
        with urlopen(req, timeout=30, context=ssl_ctx) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return []

    # First get the mass spectrum page
    mass_url = ''
    # Look for "Mass spectrum" link
    mass_match = re.search(r'href="(\?ID=[^"]*?MassSpec[^"]*?)"', html)
    if mass_match:
        mass_url = f"{WEBBOOK_BASE}{mass_match.group(1)}"
    else:
        # Another pattern
        mass_match = re.search(r'href="(/cgi/cbook\.cgi\?ID=[^"]*?Mask=200[^"]*?)"', html)
        if mass_match:
            mass_url = f"https://webbook.nist.gov{mass_match.group(1)}"

    if not mass_url:
        return []

    try:
        req = Request(mass_url, headers={'User-Agent': 'GCMS-AI-Analyzer/3.5'})
        with urlopen(req, timeout=30, context=ssl_ctx) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return []

    # Parse mass spectrum data
    # NIST WebBook format: m/z values and intensities in <pre> or <table> tags
    # Pattern 1: XY pairs in JavaScript array
    peaks_match = re.search(r'var\s+xy\s*=\s*\[(.*?)\]', html, re.DOTALL)
    if peaks_match:
        raw = peaks_match.group(1)
        pairs = re.findall(r'(\d+),\s*(\d+)', raw)
        return [(int(mz), int(intensity)) for mz, intensity in pairs]

    # Pattern 2: Table rows
    table_match = re.search(r'<table[^>]*class="spectrum"[^>]*>(.*?)</table>', html, re.DOTALL)
    if table_match:
        pairs = re.findall(r'>(\d+)</td>\s*<td[^>]*>(\d+)<', table_match.group(1))
        return [(int(mz), int(intensity)) for mz, intensity in pairs]

    # Pattern 3: pre-formatted text
    pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', html, re.DOTALL)
    if pre_match:
        lines = pre_match.group(1).strip().split('\n')
        peaks = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    mz, intensity = int(parts[0]), int(parts[1])
                    peaks.append((mz, intensity))
                except ValueError:
                    pass
        return peaks

    return []


def download_spectra(compound_list, output_dir, delay=0.5, max_spectra=5000):
    """Download EI-MS spectra for a list of compounds.

    Args:
        compound_list: list of compound names
        output_dir: where to save JCAMP files
        delay: seconds between requests (be nice to NIST server)
        max_spectra: maximum number to download
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    failed = 0
    skipped = 0

    print(f"Downloading up to {max_spectra} EI-MS spectra from NIST WebBook...")
    print(f"Output: {output_dir}")
    print()

    for i, name in enumerate(compound_list):
        if downloaded >= max_spectra:
            break

        # Check if already downloaded
        safe_name = re.sub(r'[<>:"/\\|?*\s]', '_', name).strip('_')[:80]
        out_file = output_dir / f"{safe_name}.jdx"
        if out_file.exists():
            skipped += 1
            continue

        # Search compound
        results = search_compound(name)
        if not results:
            failed += 1
            continue

        # Get spectrum from first result
        spectrum = get_mass_spectrum(results[0]['url'])
        if not spectrum or len(spectrum) < 3:
            failed += 1
            time.sleep(delay)
            continue

        # Save as JCAMP
        try:
            _write_jcamp(out_file, results[0], spectrum)
            downloaded += 1
        except Exception:
            failed += 1

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(compound_list)}] Downloaded: {downloaded}, "
                  f"Failed: {failed}, Skipped: {skipped}")

        time.sleep(delay)

    print(f"\nDone! Downloaded: {downloaded}, Failed: {failed}, Skipped: {skipped}")
    return output_dir


def _write_jcamp(filepath, compound, spectrum):
    """Write JCAMP-DX file."""
    name = compound.get('name', 'Unknown')
    formula = compound.get('formula', '')
    cas = compound.get('cas', '')

    max_int = max(p[1] for p in spectrum)
    normalized = [(mz, int(i / max_int * 9999)) for mz, i in spectrum]

    lines = [
        f'##TITLE={name}',
        f'##JCAMP-DX=4.24',
        f'##DATA TYPE=MASS SPECTRUM',
        f'##ORIGIN=NIST Chemistry WebBook (free, no license required)',
        f'##OWNER=NIST',
    ]
    if formula:
        lines.append(f'##MOLFORM={formula}')
    if cas:
        lines.append(f'##CAS REGISTRY NUMBER={cas}')
    lines.append(f'##XUNITS=M/Z')
    lines.append(f'##YUNITS=RELATIVE INTENSITY')
    lines.append(f'##NPOINTS={len(normalized)}')
    lines.append(f'##PEAK TABLE=(XY..XY)')

    for i in range(0, len(normalized), 8):
        chunk = normalized[i:i+8]
        lines.append(' '.join(f'{mz},{intensity}' for mz, intensity in chunk))

    lines.append('##END=')
    Path(filepath).write_text('\n'.join(lines), encoding='utf-8')


def get_top_flavor_compounds():
    """Return list of ~200 common flavor/aroma compounds to download spectra for."""
    return [
        # Aldehydes
        'hexanal', 'heptanal', 'octanal', 'nonanal', 'decanal', 'benzaldehyde',
        'phenylacetaldehyde', 'furfural', 'cinnamaldehyde', 'citral', 'citronellal',
        '2-heptenal', '2-octenal', '2-nonenal', '2-decenal', '2,4-decadienal',
        '2,4-heptadienal', '2,6-nonadienal', '5-methylfurfural', 'vanillin',
        # Ketones
        '2-heptanone', '2-octanone', '2-nonanone', '2-undecanone', 'acetoin',
        'acetophenone', '2,3-butanedione', '2,3-pentanedione', 'beta-ionone',
        'geranylacetone', 'carvone', 'menthone', 'camphor', 'sotolon', 'nootkatone',
        'furaneol', '2-tridecanone',
        # Alcohols
        '1-hexanol', '1-octen-3-ol', '1-nonanol', 'linalool', 'alpha-terpineol',
        'geraniol', 'nerol', 'citronellol', 'borneol', 'phenylethyl alcohol',
        'benzyl alcohol', 'furfuryl alcohol', 'maltol', 'farnesol', 'nerolidol',
        'isopentyl alcohol',
        # Esters
        'ethyl acetate', 'isoamyl acetate', 'ethyl butyrate', 'ethyl hexanoate',
        'ethyl octanoate', 'ethyl decanoate', 'hexyl acetate', 'benzyl acetate',
        'phenylethyl acetate', 'gamma-butyrolactone', 'gamma-hexalactone',
        'gamma-octalactone', 'gamma-nonalactone', 'gamma-decalactone',
        # Acids
        'acetic acid', 'butanoic acid', 'hexanoic acid', 'octanoic acid',
        '3-methylbutanoic acid', 'propanoic acid', 'isovaleric acid',
        # Pyrazines
        '2-methylpyrazine', '2,3-dimethylpyrazine', '2,5-dimethylpyrazine',
        '2-ethylpyrazine', '2-ethyl-3-methylpyrazine', '2,3,5-trimethylpyrazine',
        '2-acetylpyrazine', 'pyrazine',
        # Sulfur compounds
        'dimethyl disulfide', 'dimethyl trisulfide', 'methional', 'methanethiol',
        '2-furanmethanethiol',
        # Terpenes
        'limonene', 'alpha-pinene', 'beta-pinene', 'myrcene', 'beta-caryophyllene',
        'alpha-humulene', 'p-cymene', 'terpinolene',
        # Phenols
        'guaiacol', '4-ethylguaiacol', '4-vinylguaiacol', 'p-cresol', 'eugenol',
        'isoeugenol', 'phenol', '4-methylphenol',
        # Lactones
        'gamma-valerolactone', 'delta-decalactone', 'gamma-dodecalactone',
        # Miscellaneous
        'indole', 'skatole', 'caffeine', 'theobromine', 'maltol',
        '2-acetylpyrrole', '2-acetylfuran', '2-acetylthiazole',
        '2-methylbutanal', '3-methylbutanal', '2-methylpropanal',
        '2,3-butanediol', 'oct-1-en-3-one', 'nonanoic acid',
    ]


if __name__ == '__main__':
    compounds = get_top_flavor_compounds()
    print(f"Target: up to {len(compounds)} flavor/aroma compounds")
    download_spectra(compounds, OUTPUT_DIR, max_spectra=200)
