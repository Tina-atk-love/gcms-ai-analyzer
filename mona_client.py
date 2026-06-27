#!/usr/bin/env python3
"""
Public Mass Spectral Library Client
====================================
Lightweight client for open-access mass spectral databases.

Status (June 2026, tested from China):
  - MassBank.eu v3 API:     OK (search by name, ~139K records)
  - MoNA REST API:          Requires authentication now (HTTP 401)
  - Zenodo NIST WebBook:    Blocked by network (10053)
  - GitHub MassBank assets: May be blocked
  - Built-in MSP library:   ALWAYS available (186 EI-MS spectra, offline)

Primary use: name-based compound lookup on MassBank.eu v3.
Spectral matching uses the built-in MSP library (offline, fast).

Usage:
    from mona_client import check_apis, search_compound
    status = check_apis()
    results = search_compound("hexanal")
"""

import requests
import time
from pathlib import Path

MASSBANK_API = "https://massbank.eu/MassBank-api"
TIMEOUT = 10

_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            'User-Agent': 'GCMS-Analyzer-Agent/3.1',
            'Accept': 'application/json',
        })
    return _session


def check_apis():
    """Quick check which public APIs are available. Returns dict."""
    result = {
        'massbank_eu': False,
        'massbank_eu_msg': '',
        'mona': False,
        'mona_msg': '',
        'builtin_msp': True,  # Always available
        'builtin_msp_msg': '186 EI-MS reference spectra (offline)',
        'best_available': 'builtin_msp',
    }

    # Test MassBank.eu
    try:
        r = _get_session().get(
            f"{MASSBANK_API}/records/search",
            params={'query': 'hexanal', 'size': 1},
            timeout=8,
        )
        if r.status_code == 200:
            result['massbank_eu'] = True
            result['massbank_eu_msg'] = 'MassBank.eu v3 online'
            result['best_available'] = 'massbank_eu + builtin_msp'
    except Exception as e:
        result['massbank_eu_msg'] = str(e)[:60]

    return result


def search_compound(query, max_results=20):
    """Search MassBank.eu v3 for compound by name.

    Returns list of {accession, title, compound_name} dicts.
    Fast — only returns metadata, not full spectra.
    """
    try:
        r = _get_session().get(
            f"{MASSBANK_API}/records/search",
            params={'query': query, 'size': max_results},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []

        data = r.json()
        results = []
        for item in data.get('data', [])[:max_results]:
            results.append({
                'accession': item.get('accession', ''),
                'source': 'massbank_eu_v3',
                'url': f'https://massbank.eu/MassBank/RecordDisplay?id={item.get("accession", "")}',
            })

        return results
    except Exception:
        return []


def get_record(accession):
    """Fetch a single MassBank record with full details (slower)."""
    try:
        r = _get_session().get(
            f"{MASSBANK_API}/records/{accession}",
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None

        data = r.json()
        compound = data.get('compound', {})
        names = compound.get('names', [])
        acquisition = data.get('acquisition', {})
        peak = data.get('peak', {})

        # Extract peaks if available
        peaks = []
        annotation = peak.get('annotation', {})
        values = annotation.get('values', [])
        for row in values:
            if row:
                try:
                    mz = float(row[0])
                    peaks.append((mz, 999))
                except (ValueError, IndexError):
                    pass

        return {
            'name': names[0].strip().lower() if names else data.get('title', ''),
            'names': names,
            'accession': accession,
            'formula': compound.get('formula', ''),
            'instrument_type': acquisition.get('instrument_type', ''),
            'ion_mode': acquisition.get('mass_spectrometry', {}).get('ms_type', ''),
            'peaks': peaks,
            'n_peaks': len(peaks),
            'source': 'massbank_eu_v3',
            'url': f'https://massbank.eu/MassBank/RecordDisplay?id={accession}',
        }
    except Exception:
        return None


# CLI
if __name__ == "__main__":
    import sys
    print("Public Mass Spectral Library Status:")
    status = check_apis()
    for k, v in status.items():
        if isinstance(v, bool):
            print(f"  {'OK' if v else '--'} {k}")
        elif isinstance(v, str) and k.endswith('_msg'):
            print(f"     {v}")

    if len(sys.argv) > 1:
        print(f"\nSearching: {sys.argv[1]}")
        results = search_compound(sys.argv[1])
        print(f"  {len(results)} records found on MassBank.eu")
        for r in results[:10]:
            print(f"  - {r['accession']} -> {r['url']}")
