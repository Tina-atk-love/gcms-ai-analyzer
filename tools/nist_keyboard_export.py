#!/usr/bin/env python3
"""
NIST JCAMP Keyboard Export — Pure keyboard automation
=======================================================
Uses only keyboard shortcuts (no element enumeration) to export
JCAMP files from Agilent 谱库编辑器 (Library Editor).

This avoids pywinauto's slowness with 306K-row DataGridViews.

Usage:
  1. Open 谱库编辑器
  2. Open your NIST library
  3. Click on the FIRST compound in the list to select it
  4. Run: python tools/nist_keyboard_export.py --output D:\\JCAMP_Export

How it works:
  1. Alt+F, E → opens JCAMP export dialog
  2. Types filename → Enter to save
  3. Down arrow → next compound
  4. Repeat

Speed: ~2-3 compounds/second → ~30 hours for 306K (can run overnight)
"""

import os
import re
import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
except ImportError:
    print("Please install: pip install pyautogui")
    sys.exit(1)

# Safety: move mouse to corner to abort
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1  # Small pause between actions


class Checkpoint:
    def __init__(self, output_dir):
        self.file = Path(output_dir) / '_export_checkpoint.json'
        self.state = self._load()

    def _load(self):
        if self.file.exists():
            return json.loads(self.file.read_text(encoding='utf-8'))
        return {'exported': 0, 'current_index': 0, 'errors': []}

    def save(self):
        self.state['updated'] = datetime.now().isoformat()
        self.file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))

    def mark_done(self):
        self.state['exported'] += 1
        self.state['current_index'] += 1
        if self.state['exported'] % 1000 == 0:
            self.save()

    def mark_error(self):
        self.state['errors'].append(self.state['current_index'])
        self.state['current_index'] += 1
        self.save()


def sanitize_filename(name):
    """Remove invalid filename characters."""
    name = re.sub(r'[<>:\"/\\|?*]', '_', name)
    name = re.sub(r'\s+', '_', name)
    return name[:80].strip('_')


def export_one_compound(output_dir, index, delay=0.3):
    """Export the currently selected compound as JCAMP using keyboard shortcuts.

    Returns True if export succeeded, False otherwise.
    """
    # Generate filename
    filename = f'{index:06d}.jdx'
    filepath = Path(output_dir) / filename

    if filepath.exists():
        return True  # Already exported

    # Step 1: File → Export JCAMP
    # Alt+F to open File menu, then E for Export
    pyautogui.hotkey('alt', 'f')
    time.sleep(delay)
    pyautogui.press('e')  # In Chinese version, the accelerator might differ
    time.sleep(delay * 2)

    # Step 2: Look for Save dialog
    # The export dialog should now be open
    # Try typing the full path into the filename field
    # First select all text in the filename field
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.2)
    pyautogui.write(str(filepath))
    time.sleep(0.3)

    # Step 3: Save
    pyautogui.press('enter')
    time.sleep(delay)

    # Step 4: Check if file was created
    return filepath.exists()


def export_batch(output_dir, total_compounds, start_index=0, delay=0.5):
    """Export a batch of compounds starting from start_index.

    The user must have:
    1. The Library Editor window focused
    2. The first compound (or compound at start_index) selected

    Args:
        output_dir: where to save JCAMP files
        total_compounds: total number of compounds to export
        start_index: which compound to start from
        delay: seconds between each export step
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = Checkpoint(output_dir)

    print(f"\n{'='*60}")
    print(f"  NIST JCAMP Keyboard Export")
    print(f"  Range: {start_index:,} → {start_index + total_compounds:,}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}")
    print()
    print(f"  MOVE YOUR MOUSE TO THE TOP-LEFT CORNER TO ABORT")
    print(f"  Make sure 谱库编辑器 window is focused!")
    print(f"  Starting in 5 seconds...")
    print()

    for i in range(5, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    print(f"  GO!")
    t0 = time.time()
    exported = 0
    errors = 0
    skipped = 0

    for i in range(start_index, start_index + total_compounds):
        # Check if already exported
        filepath = output_dir / f'{i:06d}.jdx'
        if filepath.exists():
            skipped += 1
            # Move to next compound
            pyautogui.press('down')
            time.sleep(0.1)
            continue

        # Export current compound
        success = export_one_compound(output_dir, i, delay)
        if success:
            checkpoint.mark_done()
            exported += 1
        else:
            checkpoint.mark_error()
            errors += 1

        # Move to next compound
        pyautogui.press('down')
        time.sleep(0.1)

        # Progress every 100
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            rate = (i + 1 - start_index) / elapsed if elapsed > 0 else 0
            remaining = start_index + total_compounds - i - 1
            eta = remaining / rate if rate > 0 else 0
            print(f"  [{i+1:7,}] "
                  f"Exported: {exported:,} "
                  f"Skipped: {skipped:,} "
                  f"Errors: {errors:,} "
                  f"| {rate:.1f}/s | ETA: {eta/3600:.1f}h")

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"  Done in {elapsed/3600:.1f} hours")
    print(f"  Exported: {exported:,}")
    print(f"  Skipped: {skipped:,}")
    print(f"  Errors:   {errors:,}")


def main():
    parser = argparse.ArgumentParser(
        description='Keyboard-based JCAMP export from 谱库编辑器'
    )
    parser.add_argument('--output', '-o', required=True,
                        help='Output directory for JCAMP files')
    parser.add_argument('--total', '-t', type=int, default=306622,
                        help='Total compounds in library')
    parser.add_argument('--start', '-s', type=int, default=0,
                        help='Start index (resume from checkpoint)')
    parser.add_argument('--delay', '-d', type=float, default=0.5,
                        help='Delay between keystrokes (increase if export fails)')
    parser.add_argument('--test', action='store_true',
                        help='Test: export just 3 compounds')

    args = parser.parse_args()

    total = 3 if args.test else args.total

    print(f"\n  NIST JCAMP Keyboard Export")
    print(f"  Output: {args.output}")
    print(f"  Total: {total:,} compounds")
    print(f"  Delay: {args.delay}s per step")
    print()
    print(f"  Before running, make sure:")
    print(f"  1. 谱库编辑器 is open with your NIST library loaded")
    print(f"  2. The FIRST compound in the list is selected")
    print(f"  3. The 谱库编辑器 window is focused (click on it)")
    if not args.test:
        print(f"")
        print(f"  Estimated time: {total * args.delay * 3 / 3600:.1f} hours")
        print(f"  The script can be interrupted (Ctrl+C) and resumed.")
    print()

    if not args.test:
        input("  Press ENTER to start...")

    export_batch(args.output, total, args.start, args.delay)


if __name__ == '__main__':
    main()
