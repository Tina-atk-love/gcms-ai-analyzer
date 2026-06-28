#!/usr/bin/env python3
"""
Batch PubChem CAS Lookup
=========================
Queries PubChem REST API to fill in missing CAS numbers for compounds
in the MSP spectral library. Rate-limited to respect PubChem servers.

Usage:
    python pubchem_cas_lookup.py           # Start/resume batch lookup
    python pubchem_cas_lookup.py --max 200 # Limit to N queries
    python pubchem_cas_lookup.py --status  # Show progress
"""

import json
import time
import argparse
import sys
from pathlib import Path
from public_library_manager import parse_msp_file

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

MSP_PATH = Path(__file__).parent / "public_libraries" / "ei_ms_with_ri.msp"
STATE_PATH = Path(__file__).parent / "public_libraries" / "cas_lookup_state.json"
REQUEST_DELAY = 0.3  # PubChem allows ~5/sec, be conservative at 3/sec
BATCH_SIZE = 100      # save every N lookups


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


def query_pubchem_cas(name):
    """Query PubChem for CAS number of a compound by name.

    Returns CAS string or empty string.
    """
    try:
        # Try PUG REST API
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            f"{name}/property/CAS/JSON"
        )
        if HAS_REQUESTS:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                return ''
            data = resp.json()
        else:
            import urllib.request
            req = urllib.request.Request(url, headers={
                'User-Agent': 'GCMS-Analyzer/3.1 (research)'
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

        props = data.get('PropertyTable', {}).get('Properties', [])
        if props and props[0].get('CAS'):
            return props[0]['CAS']
        return ''

    except Exception:
        return ''


def main():
    parser = argparse.ArgumentParser(description="Batch PubChem CAS lookup")
    parser.add_argument('--max', type=int, default=0,
                        help='Max compounds to query (0=unlimited)')
    parser.add_argument('--status', action='store_true',
                        help='Show progress')
    parser.add_argument('--delay', type=float, default=REQUEST_DELAY,
                        help=f'Delay between requests (default: {REQUEST_DELAY}s)')
    args = parser.parse_args()

    if args.status:
        state = load_state()
        lib = parse_msp_file(str(MSP_PATH))
        total_missing = sum(1 for e in lib if not e.get('cas', '').strip())
        print(f"Library: {len(lib)} compounds")
        print(f"Missing CAS: {total_missing}")
        print(f"Checked so far: {state['total_checked']}")
        print(f"Found: {state['found']}")
        if state['total_checked'] > 0:
            rate = state['found'] / state['total_checked'] * 100
            print(f"Hit rate: {rate:.1f}%")
            remaining = total_missing - state['total_checked']
            eta_h = remaining * args.delay / 3600
            print(f"ETA: {eta_h:.1f}h")
        return

    # Load library
    print("Loading library...")
    lib = parse_msp_file(str(MSP_PATH))
    state = load_state()

    # Find compounds without CAS
    missing = [e for e in lib
               if not e.get('cas', '').strip()
               and (e.get('name') or '').strip()
               and len(e.get('name', '').strip()) >= 3]

    # Skip already-checked
    checked = set(state.get('checked', []))
    missing = [e for e in missing if e['name'] not in checked]

    if args.max > 0:
        missing = missing[:args.max]

    print(f"Library: {len(lib)} compounds")
    print(f"Missing CAS: {len(missing)}")
    print(f"Already checked: {state['total_checked']}")
    print(f"Found so far: {state['found']}")
    if missing:
        eta_h = len(missing) * args.delay / 3600
        print(f"ETA: {eta_h:.1f}h ({args.delay}s/query)")
    print()

    if not missing:
        print("All compounds checked!")
        return

    start_time = time.time()
    found_session = 0

    try:
        for i, entry in enumerate(missing):
            name = entry['name']
            cas = query_pubchem_cas(name)

            if cas:
                # Update library entry
                entry['cas'] = cas
                found_session += 1
                state['found'] += 1

            state['checked'].append(name)
            state['total_checked'] += 1

            # Progress
            if (i + 1) % BATCH_SIZE == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = len(missing) - (i + 1)
                eta_h = remaining / max(rate, 0.001) / 3600

                # Save enriched library
                save_enriched_library(lib)
                save_state(state)

                print(f"  [{i+1}/{len(missing)}] "
                      f"Found: {state['found']} (+{found_session}) "
                      f"({state['found']/max(state['total_checked'],1)*100:.1f}%) "
                      f"ETA={eta_h:.1f}h "
                      f"({rate:.1f} cpd/min)")
                found_session = 0

            time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n  Interrupted. Saving progress...")
        save_enriched_library(lib)
        save_state(state)
        print(f"  Found: {state['found']} / {state['total_checked']}")
        return

    # Final save
    save_enriched_library(lib)
    save_state(state)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  CAS LOOKUP COMPLETE")
    print(f"{'='*60}")
    print(f"  Checked: {state['total_checked']}")
    print(f"  Found: {state['found']}")
    print(f"  Hit rate: {state['found']/max(state['total_checked'],1)*100:.1f}%")
    print(f"  Time: {elapsed/3600:.1f}h")


def save_enriched_library(lib):
    """Save library with updated CAS numbers."""
    out_path = MSP_PATH
    with open(out_path, 'w', encoding='utf-8') as f:
        for entry in lib:
            f.write(f'NAME: {entry["name"]}\n')
            if entry.get('cas'):
                f.write(f'CASNO: {entry["cas"]}\n')
            f.write(f'FORMULA: {entry.get("formula", "")}\n')
            if entry.get('ri_exp'):
                f.write(f'RETENTIONINDEX: {entry["ri_exp"]}\n')
            f.write(f'SOURCE: {entry.get("source", "msp_file")}\n')
            f.write(f'NUM PEAKS: {entry["num_peaks"]}\n')
            for mz, intensity in entry.get('peaks', []):
                f.write(f'{mz} {intensity}; ')
            f.write('\n\n')


if __name__ == "__main__":
    main()
