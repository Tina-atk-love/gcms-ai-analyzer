#!/usr/bin/env python3
"""
NIST JCAMP Batch Auto-Exporter
================================
GUI automation of Agilent MassHunter 谱库编辑器 (Library Editor).
Automatically exports all spectra from a NIST library as JCAMP files.

⚠️  IMPORTANT:
  - NIST library MUST already be opened in the Library Editor
  - This script ONLY controls the already-open window
  - All NIST data stays on your computer

Usage:
  1. Open 谱库编辑器 manually
  2. Open your NIST library (File → Open → select NIST .L or .ms file)
  3. Make sure the compound list is visible in the DataGridView
  4. Run: python tools/nist_jcamp_auto_exporter.py --output D:\\JCAMP_Export

The script will:
  - Click the first compound in the list
  - File → 导出 JCAMP 文件... → Save
  - Move to next compound
  - Repeat until all compounds are exported
  - Support checkpoint/resume if interrupted
"""

import os
import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except ImportError:
    print("Please install: pip install pywinauto")
    sys.exit(1)


# ================================================================
# Checkpoint Manager
# ================================================================
class Checkpoint:
    def __init__(self, output_dir):
        self.file = Path(output_dir) / '_export_checkpoint.json'
        self.state = self._load()

    def _load(self):
        if self.file.exists():
            return json.loads(self.file.read_text(encoding='utf-8'))
        return {'exported': [], 'total': 0, 'current_index': 0, 'errors': []}

    def save(self):
        self.state['updated'] = datetime.now().isoformat()
        self.file.write_text(json.dumps(self.state, ensure_ascii=False, indent=2))

    def is_done(self, idx):
        return str(idx) in self.state.get('exported', [])

    def mark_done(self, idx, name):
        if str(idx) not in self.state['exported']:
            self.state['exported'].append(str(idx))
        self.state['current_index'] = idx + 1
        self.save()

    def mark_error(self, idx, msg):
        self.state['errors'].append({'index': idx, 'error': str(msg)})
        self.save()


# ================================================================
# Core Exporter
# ================================================================
class JCAMPExporter:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint = Checkpoint(output_dir)
        self.app = None
        self.window = None

    def connect(self):
        """Connect to running Library Editor window."""
        windows = Desktop(backend='uia').windows()
        for w in windows:
            try:
                if '谱库编辑器' in w.window_text():
                    self.app = Application(backend='uia').connect(handle=w.handle)
                    self.window = self.app.window(handle=w.handle)
                    self.window.set_focus()
                    print(f"✓ Connected to: {w.window_text()}")
                    return True
            except:
                pass
        print("[ERROR] Library Editor not found. Please open it first.")
        return False

    def get_compound_count(self):
        """Get total number of compounds from the status bar."""
        try:
            # Look for the "化合物总数:" text element
            for child in self.window.descendants(control_type='Text'):
                try:
                    name = child.window_text()
                    if '化合物总数' in name:
                        # Extract number: "化合物总数: 306,622"
                        import re
                        match = re.search(r'[\d,]+', name)
                        if match:
                            return int(match.group().replace(',', ''))
                except:
                    pass
        except:
            pass
        return 0

    def get_current_compound_name(self):
        """Read the currently selected compound name from the grid."""
        try:
            grid = self.window.child_window(control_type='Table')
            if grid.exists():
                # Try to read selected cell
                for cell in grid.descendants(control_type='DataItem'):
                    try:
                        return cell.window_text()
                    except:
                        pass
        except:
            pass
        return 'Unknown'

    def select_compound_by_index(self, index):
        """Select compound at given index in the DataGridView."""
        try:
            grid = self.window.child_window(control_type='Table')
            if not grid.exists():
                return False

            # Click on the row header area to select
            # The first column is "首行" (row header)
            grid.click_input()

            # Use keyboard to navigate: Ctrl+Home, then Down arrow by index
            send_keys('^{HOME}')  # Go to first row
            time.sleep(0.3)

            for _ in range(index):
                send_keys('{DOWN}')
                time.sleep(0.05)

            time.sleep(0.3)
            return True
        except Exception as e:
            print(f"  Select failed: {e}")
            return False

    def export_current_compound(self, save_path):
        """Export the currently selected compound as JCAMP."""
        try:
            # Click File → 导出 JCMP 文件...
            self.window.menu_select('文件(F)->导出 JCAMP 文件...')
            time.sleep(1.5)

            # Handle Save dialog
            save_dlg = None
            for _ in range(10):  # Wait up to 5 seconds
                for dlg in Desktop(backend='uia').windows():
                    try:
                        text = dlg.window_text()
                        if text and ('另存为' in text or 'Save' in text or '导出' in text):
                            save_dlg = dlg
                            break
                    except:
                        pass
                if save_dlg:
                    break
                time.sleep(0.5)

            if not save_dlg:
                # Try pressing Enter on the export menu item
                send_keys('{ENTER}')
                time.sleep(1)
                return False

            # Fill in file path
            # Find the filename combo box
            combo = None
            for child in save_dlg.descendants():
                try:
                    ctrl_type = child.element_info.control_type
                    if ctrl_type in ('ComboBox', 'Edit'):
                        combo = child
                        break
                except:
                    pass

            if combo:
                combo.set_edit_text(str(save_path))
                time.sleep(0.5)
            else:
                # Type the path
                send_keys(str(save_path))
                time.sleep(0.5)

            # Click Save button
            for child in save_dlg.descendants(control_type='Button'):
                try:
                    name = child.window_text()
                    if name in ('保存', 'Save', '确定'):
                        child.click()
                        time.sleep(1)
                        return True
                except:
                    pass

            # Fallback: press Enter
            send_keys('{ENTER}')
            time.sleep(1)
            return True

        except Exception as e:
            print(f"  Export error: {e}")
            return False

    def export_all(self, start_index=0, max_export=None, delay=0.5):
        """Export all compounds from the library.

        Args:
            start_index: compound index to start from (for resume)
            max_export: max number to export (None = all)
            delay: seconds between exports
        """
        total = self.get_compound_count()
        if total == 0:
            total = 306622  # Default for NIST17

        end_index = min(total, start_index + max_export) if max_export else total

        print(f"\n{'='*60}")
        print(f"  Starting JCAMP Export")
        print(f"  Range: {start_index:,} → {end_index:,} of {total:,}")
        print(f"  Output: {self.output_dir}")
        print(f"{'='*60}\n")

        exported = 0
        skipped = 0
        errors = 0
        t0 = time.time()

        for i in range(start_index, end_index):
            if self.checkpoint.is_done(i):
                skipped += 1
                continue

            # Select compound
            if not self.select_compound_by_index(i):
                errors += 1
                continue

            # Get compound name for the filename
            name = self.get_current_compound_name()
            safe_name = name.replace('/', '_').replace('\\', '_').replace(':', '_')[:60]
            save_path = self.output_dir / f'{i:06d}_{safe_name}.jdx'

            # Export
            if self.export_current_compound(str(save_path)):
                self.checkpoint.mark_done(i, name)
                exported += 1
            else:
                errors += 1
                self.checkpoint.mark_error(i, 'Export failed')

            # Progress
            if (i + 1) % 100 == 0 or i == end_index - 1:
                elapsed = time.time() - t0
                rate = (i + 1 - start_index) / elapsed if elapsed > 0 else 0
                eta = (end_index - i - 1) / rate if rate > 0 else 0
                print(f"  [{i+1:7,}/{total:,}] "
                      f"Exported: {exported:,} "
                      f"Skipped: {skipped:,} "
                      f"Errors: {errors:,} "
                      f"| {rate:.1f} cmp/s | ETA: {eta/60:.0f} min")

            time.sleep(delay)

        elapsed = time.time() - t0
        print(f"\n{'='*60}")
        print(f"  Done in {elapsed/60:.1f} min")
        print(f"  Exported: {exported:,}")
        print(f"  Skipped: {skipped:,}")
        print(f"  Errors:   {errors:,}")
        print(f"  Output:   {self.output_dir}")


# ================================================================
# CLI
# ================================================================
def main():
    parser = argparse.ArgumentParser(
        description='Auto-export JCAMP from 谱库编辑器 (Library Editor)'
    )
    parser.add_argument('--output', '-o', default='D:\\JCAMP_Export',
                        help='Output directory for JCAMP files')
    parser.add_argument('--start', type=int, default=0,
                        help='Start index (for resume)')
    parser.add_argument('--max', type=int, default=None,
                        help='Max compounds to export')
    parser.add_argument('--delay', type=float, default=0.3,
                        help='Delay between exports (seconds)')
    parser.add_argument('--test', action='store_true',
                        help='Test connection only')

    args = parser.parse_args()

    exporter = JCAMPExporter(args.output)

    if not exporter.connect():
        print("\nPlease:")
        print("  1. Open 谱库编辑器")
        print("  2. Open your NIST library")
        print("  3. Run this script again")
        sys.exit(1)

    if args.test:
        total = exporter.get_compound_count()
        print(f"\n✓ Connected!")
        print(f"  Total compounds: {total:,}")
        print(f"  Try exporting first compound...")
        exporter.select_compound_by_index(0)
        name = exporter.get_current_compound_name()
        print(f"  First compound: {name}")
        sys.exit(0)

    exporter.export_all(
        start_index=args.start,
        max_export=args.max,
        delay=args.delay,
    )


if __name__ == '__main__':
    main()
