#!/usr/bin/env python3
"""
Validate GCMS analysis results: compare agent output vs batch analyzer output.
Usage: python validate_results.py
"""

import sys
from pathlib import Path
import pandas as pd

OUTPUT_DIR = Path(__file__).parent / "output"
AGENT_DIR = OUTPUT_DIR / "agent_results"
BATCH_DIR = OUTPUT_DIR

def find_latest_csv(directory):
    """Find the most recent CSV pivot file in a directory."""
    csv_files = list(directory.glob("*.csv"))
    if not csv_files:
        return None
    return max(csv_files, key=lambda p: p.stat().st_mtime)

def main():
    print("=" * 55)
    print("  GCMS Results Validation")
    print("=" * 55)
    print()

    # Find files
    batch_csv = BATCH_DIR / "amino_acid_data.csv"
    agent_csv = find_latest_csv(AGENT_DIR)

    if not batch_csv.exists():
        print("  [WARN] Batch output not found. Run gcms_analyzer.py first:")
        print(f"    python gcms_analyzer.py --data-dir \"<path>\" --no-plots")
        print()
        sys.exit(1)

    if not agent_csv:
        print("  [WARN] Agent output not found. Run gcms_agent.py and type /run first.")
        print()
        sys.exit(1)

    print(f"  Batch: {batch_csv}")
    print(f"  Agent: {agent_csv}")
    print()

    # Load data
    batch = pd.read_csv(batch_csv)
    agent = pd.read_csv(agent_csv)

    # Normalize: remove .D suffix from sample names in agent output
    if 'sample' in agent.columns:
        agent['sample'] = agent['sample'].str.replace(r'\.D$', '', regex=True)

    # Find amino acid columns (exclude group/sample)
    id_cols = {'group', 'sample', 'sub_group', 'sample_num', 'label'}
    batch_aa = [c for c in batch.columns if c not in id_cols]
    agent_aa = [c for c in agent.columns if c not in id_cols]

    common_aa = sorted(set(batch_aa) & set(agent_aa))
    if not common_aa:
        print("  [ERROR] No common amino acid columns found between files.")
        print(f"  Batch columns: {batch_aa}")
        print(f"  Agent columns: {agent_aa}")
        sys.exit(1)

    print(f"  Common amino acids: {len(common_aa)}")
    print()

    # Compare means per amino acid
    print("  --- Per-Amino-Acid Mean Comparison ---")
    print(f"  {'Compound':12s} {'Batch Mean':>12s} {'Agent Mean':>12s} {'Diff':>10s} {'Status'}")
    print("  " + "-" * 60)

    all_ok = True
    issues = []

    for comp in common_aa:
        bm = batch[comp].mean()
        am = agent[comp].mean()
        diff = abs(bm - am)
        rel_diff = diff / abs(bm) * 100 if abs(bm) > 1e-10 else 0

        status = "[OK]" if rel_diff < 0.1 else ("[WARN]" if rel_diff < 1.0 else "[FAIL]")
        if status != "[OK]":
            all_ok = False
            issues.append((comp, rel_diff))

        print(f"  {comp:12s} {bm:12.6f} {am:12.6f} {rel_diff:9.2f}% {status}")

    # Summary
    print()
    print("=" * 55)
    if all_ok:
        print("  [OK] All amino acid means match! Agent output is accurate.")
    else:
        print(f"  [WARN] {len(issues)} compounds have discrepancies:")
        for comp, diff in issues[:5]:
            print(f"    - {comp}: {diff:.1f}% difference")
        print()
        print("  Possible causes:")
        print("    1. Agent parsed different .D folders than batch")
        print("    2. Different samples were included/skipped")
        print("    3. Data directory was different between runs")
    print("=" * 55)


if __name__ == "__main__":
    main()
