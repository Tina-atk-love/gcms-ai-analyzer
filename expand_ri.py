#!/usr/bin/env python3
"""
Expand RI Database from NIST WebBook
=====================================
Background process: queries NIST WebBook for Kovats Retention Index values
for compounds in the MSP spectral library. Saves progress every 50 queries.

Resume capability: re-running will skip compounds already in the RI database
and continue from where it left off.

Usage:
    python expand_ri.py                  # Start/resume expansion
    python expand_ri.py --max 200        # Limit to N queries
    python expand_ri.py --status         # Show current progress
    python expand_ri.py --check-compound "hexanal"  # Test single compound

Database:
    Input:  public_libraries/ei_ms_combined.msp (12,709 spectra)
    Output: public_libraries/nist_webbook_ri.json (Kovats RI values)
"""

import requests
import re
import time
import json
import argparse
import sys
from pathlib import Path

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (compatible; GCMS-Research/3.1; +mailto:research@example.com)'
})

OUT = Path(__file__).parent / "public_libraries"
MSP_PATH = OUT / "ei_ms_combined.msp"
RI_PATH = OUT / "nist_webbook_ri.json"
STATE_PATH = OUT / "ri_expansion_state.json"

# Rate limiting: be respectful to NIST servers
REQUEST_DELAY = 1.0  # seconds between requests
BATCH_SIZE = 50       # save state every N compounds
BATCH_REST = 5.0      # extra rest between batches


def load_state():
    """Load expansion resume state."""
    if STATE_PATH.exists():
        try:
            with open(STATE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {'checked': [], 'last_index': 0, 'total_added': 0}


def save_state(state):
    """Save expansion resume state."""
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)


def load_ri_database():
    """Load existing RI database."""
    if RI_PATH.exists():
        try:
            with open(RI_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_ri_database(ri_db):
    """Save RI database atomically."""
    tmp_path = RI_PATH.with_suffix('.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(ri_db, f, indent=2, ensure_ascii=False)
    tmp_path.replace(RI_PATH)


def query_nist_ri(compound_name, timeout=8):
    """Query NIST WebBook for Kovats RI values of a compound.

    Returns dict: {'ri_values': [float, ...], 'cas': str}
    ri_values is empty list if nothing found.
    """
    result = {'ri_values': [], 'cas': ''}
    try:
        r = session.get(
            f"https://webbook.nist.gov/cgi/cbook.cgi?Name={compound_name}&Units=SI&Mask=2000",
            timeout=timeout
        )
        if r.status_code != 200:
            return result

        text = r.text

        # Extract CAS Registry Number
        cas_match = re.search(r'CAS Registry Number:\s*(\d{2,7}-\d{2}-\d)', text)
        if cas_match:
            result['cas'] = cas_match.group(1)

        # Check if page contains GC data
        if 'Gas Chromatography' not in text and 'Kovats' not in text:
            return result

        # Extract RI values from the GC table
        # Pattern: <td class="right-nowrap"> 1234.5 </td>
        matches = re.findall(
            r'<td class="right-nowrap">\s*(\d{2,4}\.\d{1,2})\s*</td>',
            text
        )

        # Filter to reasonable Kovats range (400-4000)
        ri_values = []
        for m in matches:
            val = float(m)
            if 400 < val < 4000:
                ri_values.append(round(val, 1))

        result['ri_values'] = sorted(set(ri_values))
        return result

    except requests.exceptions.Timeout:
        return result
    except requests.exceptions.ConnectionError:
        return result
    except Exception:
        return result


def show_status():
    """Display current RI database expansion status."""
    ri_db = load_ri_database()
    state = load_state()

    print(f"\n{'='*60}")
    print(f"  RI Database Expansion Status")
    print(f"{'='*60}")
    print(f"  RI entries: {len(ri_db)}")
    print(f"  Checked so far: {state.get('last_index', 0)}")
    print(f"  Total added this session: {state.get('total_added', 0)}")

    # RI distribution
    if ri_db:
        ri_values = []
        for v in ri_db.values():
            if isinstance(v, dict) and 'ri' in v:
                ri_values.append(v['ri'])
            elif isinstance(v, (int, float)):
                ri_values.append(v)

        if ri_values:
            print(f"  RI range: {min(ri_values):.1f} - {max(ri_values):.1f}")
            print(f"  Mean RI: {sum(ri_values)/len(ri_values):.1f}")

    # MSP library size
    if MSP_PATH.exists():
        from public_library_manager import parse_msp_file
        entries = parse_msp_file(str(MSP_PATH))
        print(f"  MSP library: {len(entries)} compounds")
        missing = max(0, len(entries) - len(ri_db))
        print(f"  Without RI data: ~{missing}")
        if missing > 0:
            rate = 100 / REQUEST_DELAY  # ~100 per hour at 1s delay (optimistic)
            eta_h = missing / max(rate, 1)
            print(f"  Est. time to complete: {eta_h:.0f} hours (at {REQUEST_DELAY}s/query)")

    print()


def test_compound(name):
    """Test RI query for a single compound."""
    print(f"\nQuerying NIST for: {name}")
    result = query_nist_ri(name)
    ri_values = result['ri_values']
    if ri_values:
        median_ri = ri_values[len(ri_values) // 2]
        print(f"  RI values: {ri_values}")
        print(f"  Median RI: {median_ri}")
        if result['cas']:
            print(f"  CAS: {result['cas']}")
    else:
        print(f"  No RI data found on NIST WebBook")
        if result['cas']:
            print(f"  CAS (from page): {result['cas']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Expand RI database from NIST WebBook"
    )
    parser.add_argument('--max', type=int, default=0,
                       help='Maximum compounds to query (0=unlimited)')
    parser.add_argument('--status', action='store_true',
                       help='Show expansion status')
    parser.add_argument('--check-compound', type=str, default='',
                       help='Test RI query for a single compound')
    parser.add_argument('--delay', type=float, default=REQUEST_DELAY,
                       help=f'Delay between requests in seconds (default: {REQUEST_DELAY})')
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.check_compound:
        test_compound(args.check_compound)
        return

    # --- Main expansion loop ---
    print("Loading MSP library...")
    from public_library_manager import parse_msp_file

    entries = parse_msp_file(str(MSP_PATH))
    if not entries:
        print(f"[ERROR] No entries found in {MSP_PATH}")
        sys.exit(1)

    ri_db = load_ri_database()
    state = load_state()

    # Build set of already-known compound names
    existing = set()
    for k in ri_db.keys():
        existing.add(k.lower().strip())

    # Filter to candidates not already in database
    candidates = []
    for e in entries:
        name = (e.get('name') or '').strip().lower()
        if name and name not in existing and 3 <= len(name) <= 100:
            candidates.append(e)

    # Skip already-checked compounds
    checked = set(state.get('checked', []))
    candidates = [c for c in candidates if c.get('name', '').strip().lower() not in checked]

    start_idx = state.get('last_index', 0)
    if start_idx > 0 and start_idx < len(candidates):
        candidates = candidates[start_idx:]

    if args.max > 0:
        candidates = candidates[:args.max]

    print(f"\n{'='*60}")
    print(f"  RI Database Expansion")
    print(f"{'='*60}")
    print(f"  Current RI entries: {len(ri_db)}")
    print(f"  MSP library: {len(entries)} compounds")
    print(f"  To check: {len(candidates)} ({len(checked)} already checked)")
    print(f"  Delay: {args.delay}s between requests")
    if candidates:
        eta_h = len(candidates) * args.delay / 3600
        print(f"  Est. time: {eta_h:.1f} hours")
    print()

    if not candidates:
        print("Nothing to do — all compounds checked!")
        return

    ri_new_session = 0
    ri_checked_session = 0
    start_time = time.time()

    try:
        for i, entry in enumerate(candidates):
            name = (entry.get('name') or '').strip()
            ri_checked_session += 1

            result = query_nist_ri(name)
            ri_values = result['ri_values']

            if ri_values:
                median_ri = ri_values[len(ri_values) // 2]
                ri_db[name.lower()] = {
                    'ri': median_ri,
                    'all_ri': ri_values,
                    'n': len(ri_values),
                    'cas': result['cas'] or entry.get('cas', ''),
                }
                ri_new_session += 1
                state['total_added'] = state.get('total_added', 0) + 1

            state['checked'].append(name.lower())
            state['last_index'] = start_idx + i + 1

            # Progress reporting
            if (i + 1) % BATCH_SIZE == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = len(candidates) - (i + 1)
                eta_h = remaining / max(rate, 0.001) / 3600

                save_ri_database(ri_db)
                save_state(state)

                print(f"  [{i+1}/{len(candidates)}] "
                      f"RI={len(ri_db)} (+{ri_new_session} this batch) "
                      f"ETA={eta_h:.1f}h "
                      f"({rate:.1f} cpd/min)")

                ri_new_session = 0
                time.sleep(BATCH_REST)
            else:
                time.sleep(args.delay)

    except KeyboardInterrupt:
        print("\n\n  Interrupted. Saving progress...")
        save_ri_database(ri_db)
        save_state(state)
        print(f"  Progress saved. RI entries: {len(ri_db)}")
        print(f"  Resume with: python expand_ri.py")
        return

    # Final save
    save_ri_database(ri_db)
    save_state(state)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  EXPANSION COMPLETE")
    print(f"{'='*60}")
    print(f"  RI entries: {len(ri_db)}")
    print(f"  Added this session: {state.get('total_added', 0)}")
    print(f"  Time: {elapsed/3600:.1f}h")
    print(f"  Saved: {RI_PATH}")
    print()


if __name__ == "__main__":
    main()
