#!/usr/bin/env python3
"""
RI Expansion via PubChem InChIKey → NIST WebBook
==================================================
Two-stage lookup for compounds with known CAS numbers:
  1. PubChem: CAS → InChIKey
  2. NIST WebBook: InChIKey → Kovats RI values

This is more reliable than name-based NIST queries because:
- InChIKey is a unique structural identifier (no name ambiguity)
- NIST WebBook supports direct InChIKey lookup
- CAS numbers from PubChem are verified (no false positives)

Usage:
    python ri_from_cas.py              # Process all compounds with CAS
    python ri_from_cas.py --max 50     # Limit to N compounds
    python ri_from_cas.py --status     # Show progress
"""

import json
import re
import time
import argparse
import sys
from pathlib import Path
from urllib.parse import quote

try:
    import requests
    HAS_REQUESTS = True
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    HAS_REQUESTS = False

MSP_PATH = Path(__file__).parent / "public_libraries" / "ei_ms_with_ri.msp"
RI_PATH = Path(__file__).parent / "public_libraries" / "nist_webbook_ri.json"
STATE_PATH = Path(__file__).parent / "public_libraries" / "ri_cas_state.json"

REQUEST_DELAY = 0.5  # seconds between NIST requests
BATCH_SIZE = 25


def load_state():
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'checked': [], 'found': 0, 'total_checked': 0}


def save_state(state):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def load_ri_database():
    if RI_PATH.exists():
        try:
            with open(RI_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_ri_database(ri_db):
    tmp = RI_PATH.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(ri_db, f, indent=2, ensure_ascii=False)
    tmp.replace(RI_PATH)


def pubchem_cas_to_inchikey(cas):
    """Get InChIKey from PubChem using CAS number.

    Returns InChIKey string or empty string.
    """
    try:
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{quote(cas)}/property/InChIKey/JSON"
        )
        if HAS_REQUESTS:
            r = requests.get(url,
                headers={'User-Agent': 'GCMS/3.1'},
                timeout=10, verify=False)
            if r.status_code != 200:
                return ''
            data = r.json()
        else:
            import urllib.request, ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url,
                headers={'User-Agent': 'GCMS/3.1'})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))

        props = data.get('PropertyTable', {}).get('Properties', [])
        if props:
            return props[0].get('InChIKey', '')
        return ''
    except Exception:
        return ''


def nist_inchikey_to_ri(inchikey):
    """Query NIST WebBook for Kovats RI using InChIKey.

    Returns list of RI values.
    """
    try:
        url = (
            f"https://webbook.nist.gov/cgi/cbook.cgi?"
            f"InChI={inchikey}&Units=SI&Mask=2000"
        )
        if HAS_REQUESTS:
            r = requests.get(url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; GCMS-Research/3.1)'},
                timeout=10)
            if r.status_code != 200:
                return []
            text = r.text
        else:
            import urllib.request
            req = urllib.request.Request(url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; GCMS-Research/3.1)'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode('utf-8', errors='ignore')

        if 'Gas Chromatography' not in text and 'Kovats' not in text:
            return []

        matches = re.findall(
            r'<td class="right-nowrap">\s*(\d{2,4}\.\d{1,2})\s*</td>',
            text
        )
        ri_values = []
        for m in matches:
            val = float(m)
            if 400 < val < 4000:
                ri_values.append(round(val, 1))

        return sorted(set(ri_values))

    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(
        description="RI expansion via PubChem InChIKey -> NIST WebBook"
    )
    parser.add_argument('--max', type=int, default=0)
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--delay', type=float, default=REQUEST_DELAY)
    args = parser.parse_args()

    if args.status:
        state = load_state()
        ri_db = load_ri_database()
        print(f"RI database: {len(ri_db)} entries")
        print(f"Checked: {state['total_checked']}")
        print(f"Found: {state['found']}")
        if state['total_checked'] > 0:
            print(f"Hit rate: {state['found']/state['total_checked']*100:.1f}%")
        return

    # Load library, find compounds with CAS but without RI
    from public_library_manager import parse_msp_file

    print("Loading library...")
    lib = parse_msp_file(str(MSP_PATH))
    ri_db = load_ri_database()
    state = load_state()

    # Find compounds: have CAS, don't have RI (in library), not already checked
    candidates = [e for e in lib
                  if e.get('cas', '').strip()
                  and not e.get('ri_exp')
                  and e['name'] not in state.get('checked', [])]

    if args.max > 0:
        candidates = candidates[:args.max]

    print(f"Candidates (have CAS, no RI, not checked): {len(candidates)}")
    if not candidates:
        print("Nothing to do!")
        return

    eta_h = len(candidates) * args.delay / 3600
    print(f"ETA: {eta_h:.1f}h ({args.delay}s/NIST query)")
    print()

    ri_new = 0
    start_time = time.time()

    try:
        for i, entry in enumerate(candidates):
            name = entry['name']
            cas = entry.get('cas', '')

            # Step 1: CAS → InChIKey (PubChem)
            inchikey = pubchem_cas_to_inchikey(cas)

            if not inchikey:
                state['checked'].append(name)
                state['total_checked'] += 1
                time.sleep(args.delay)
                continue

            # Step 2: InChIKey → RI (NIST WebBook)
            ri_values = nist_inchikey_to_ri(inchikey)

            if ri_values:
                median_ri = ri_values[len(ri_values) // 2]
                ri_db[name.lower()] = {
                    'ri': median_ri,
                    'all_ri': ri_values,
                    'n': len(ri_values),
                    'cas': cas,
                    'inchikey': inchikey,
                }
                entry['ri_exp'] = median_ri
                ri_new += 1
                state['found'] += 1

            state['checked'].append(name)
            state['total_checked'] += 1

            # Progress
            if (i + 1) % BATCH_SIZE == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / max(elapsed, 0.001)
                remaining = len(candidates) - (i + 1)
                eta_h = remaining / max(rate, 0.001) / 3600

                save_ri_database(ri_db)
                save_state(state)

                print(f"  [{i+1}/{len(candidates)}] "
                      f"RI={len(ri_db)} (+{ri_new}) "
                      f"({state['found']/max(state['total_checked'],1)*100:.1f}%) "
                      f"ETA={eta_h:.1f}h")
                ri_new = 0

            time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n  Interrupted. Saving...")
        save_ri_database(ri_db)
        save_state(state)
        save_enriched_library(lib)
        return

    # Final save
    save_ri_database(ri_db)
    save_state(state)
    save_enriched_library(lib)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  RI EXPANSION COMPLETE")
    print(f"{'='*60}")
    print(f"  RI entries: {len(ri_db)}")
    print(f"  Added: {state['found']}")
    print(f"  Time: {elapsed/3600:.1f}h")


def save_enriched_library(lib):
    """Update MSP file with new RI values."""
    out = MSP_PATH
    with open(out, 'w', encoding='utf-8') as f:
        for e in lib:
            f.write(f'NAME: {e["name"]}\n')
            if e.get('cas'):
                f.write(f'CASNO: {e["cas"]}\n')
            f.write(f'FORMULA: {e.get("formula", "")}\n')
            if e.get('ri_exp'):
                f.write(f'RETENTIONINDEX: {e["ri_exp"]}\n')
            if e.get('compound_class'):
                f.write(f'COMPOUND_CLASS: {e["compound_class"]}\n')
            f.write(f'SOURCE: {e.get("source", "msp_file")}\n')
            f.write(f'NUM PEAKS: {e["num_peaks"]}\n')
            for mz, intensity in e.get('peaks', []):
                f.write(f'{mz} {intensity}; ')
            f.write('\n\n')


if __name__ == "__main__":
    main()
