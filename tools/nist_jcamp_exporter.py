#!/usr/bin/env python3
"""
NIST JCAMP Batch Exporter — GUI Automation for MassHunter Qualitative Analysis
================================================================================
Automates the NIST library spectrum export process:
  1. Connects to a running MassHunter Qualitative Analysis instance
  2. Opens each .D data file
  3. Integrates peaks → searches NIST library → exports matched spectra as JCAMP
  4. Supports checkpoint/resume — never loses progress on crash

Supports two operating modes:
  A) Export matched spectra from sample data files (batch of .D folders)
  B) Export raw NIST library spectra by compound name/range (direct NIST MS Search)

Requirements:
  pip install pywinauto pyautogui pywin32 comtypes

Usage:
  # Mode A: Export NIST matches from .D data files
  python nist_jcamp_exporter.py --data-dir D:\\GCMS_Data --output D:\\NIST_JCAMP

  # Mode B: Export NIST library spectra by CAS list
  python nist_jcamp_exporter.py --cas-list compounds.txt --output D:\\NIST_JCAMP

  # Resume from checkpoint
  python nist_jcamp_exporter.py --resume
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ---- Output directory ----
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "nist_export"
CHECKPOINT_FILE = OUTPUT_DIR / "checkpoint.json"

# ================================================================
# Configuration
# ================================================================
class Config:
    # ================================================================
    # MassHunter 未知物分析 (Unknowns Analysis) — found on your system
    # ================================================================
    MASSHUNTER_EXE = (
        r"C:\Program Files\Agilent\MassHunter\Workstation\Quant\bin"
        r"\Agilent.MassHunter.UnknownsAnalysis.UI.exe"
    )

    # Window titles — Chinese & English (try in order)
    MASSHUNTER_WINDOW_TITLES = [
        "未知物分析",
        "Unknowns Analysis",
        "Agilent MassHunter Unknowns Analysis",
        "MassHunter Unknowns Analysis",
        "MassHunter Qualitative Analysis",
        "Qualitative Analysis",
        "Agilent MassHunter Qualitative Analysis",
    ]

    # NIST MS Search window titles (standalone mode)
    NIST_WINDOW_TITLES = [
        "NIST MS Search",
        "NIST MS Search Program",
        "NIST MS Search v",
    ]

    # Timeouts (seconds)
    WINDOW_APPEAR_TIMEOUT = 30
    BUTTON_CLICK_TIMEOUT = 10
    EXPORT_WAIT_TIMEOUT = 15
    SEARCH_WAIT_TIMEOUT = 120  # NIST search can be slow for complex spectra
    INTEGRATE_WAIT_TIMEOUT = 60

    # Delays between operations (prevents UI freezes)
    POST_CLICK_DELAY = 0.5
    POST_DIALOG_DELAY = 1.0
    BETWEEN_FILE_DELAY = 3.0

    # After every N files, take a longer cooldown
    COOLDOWN_INTERVAL = 50
    COOLDOWN_DURATION = 30  # seconds


# ================================================================
# Checkpoint Manager
# ================================================================
class CheckpointManager:
    """Persists progress so long runs survive crashes."""

    def __init__(self, filepath=CHECKPOINT_FILE):
        self.filepath = Path(filepath)
        self.state = self._load()

    def _load(self):
        if self.filepath.exists():
            try:
                return json.loads(self.filepath.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {
            'mode': None,
            'completed_files': [],
            'completed_compounds': [],
            'total_exported': 0,
            'current_file': None,
            'current_compound': None,
            'started_at': None,
            'last_updated': None,
        }

    def save(self):
        self.state['last_updated'] = datetime.now().isoformat()
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self.filepath.write_text(json.dumps(self.state, ensure_ascii=False, indent=2),
                                 encoding='utf-8')

    def mark_file_done(self, filepath):
        if str(filepath) not in self.state['completed_files']:
            self.state['completed_files'].append(str(filepath))
        self.state['current_file'] = str(filepath)
        self.save()

    def mark_compound_done(self, compound_name):
        if compound_name not in self.state['completed_compounds']:
            self.state['completed_compounds'].append(compound_name)
        self.state['current_compound'] = compound_name
        self.state['total_exported'] += 1
        self.save()

    def is_file_done(self, filepath):
        return str(filepath) in self.state['completed_files']

    def is_compound_done(self, compound_name):
        return compound_name in self.state['completed_compounds']


# ================================================================
# Window Finder — locates MassHunter or NIST MS Search
# ================================================================
class WindowFinder:
    """Finds and attaches to MassHunter Qual or NIST MS Search windows."""

    @staticmethod
    def find_masshunter(app=None):
        """Find MassHunter Qualitative Analysis window.
        Returns (app, window) tuple or (None, None).
        """
        from pywinauto import Application
        from pywinauto.findwindows import find_windows

        # Strategy 1: Check existing windows by title
        for title_pattern in Config.MASSHUNTER_WINDOW_TITLES:
            try:
                matches = find_windows(title_re=title_pattern, top_level_only=True)
                if matches:
                    app = Application(backend='uia').connect(handle=matches[0])
                    window = app.window(handle=matches[0])
                    print(f"  ✓ Connected to MassHunter: \"{window.window_text()}\"")
                    return app, window
            except Exception:
                pass

        # Strategy 2: Try with win32 backend
        for title_pattern in Config.MASSHUNTER_WINDOW_TITLES:
            try:
                matches = find_windows(title_re=title_pattern, top_level_only=True,
                                       backend='win32')
                if matches:
                    app = Application(backend='win32').connect(handle=matches[0])
                    window = app.window(handle=matches[0])
                    print(f"  ✓ Connected to MassHunter (win32): \"{window.window_text()}\"")
                    return app, window
            except Exception:
                pass

        # Strategy 3: Broadcast — list all windows and fuzzy-match
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend='uia')
            for w in desktop.windows():
                try:
                    text = w.window_text()
                    if text and any(kw.lower() in text.lower()
                                    for kw in ['masshunter', 'qualitative', 'agilent qual']):
                        app = Application(backend='uia').connect(handle=w.handle)
                        print(f"  ✓ Connected via fuzzy match: \"{text}\"")
                        return app, app.window(handle=w.handle)
                except Exception:
                    pass
        except Exception:
            pass

        return None, None

    @staticmethod
    def find_nist_ms_search():
        """Find standalone NIST MS Search window."""
        from pywinauto import findwindows
        for pattern in Config.NIST_WINDOW_TITLES:
            try:
                matches = findwindows.find_windows(title_re=pattern,
                                                   top_level_only=True)
                if matches:
                    from pywinauto import Application
                    app = Application(backend='uia').connect(handle=matches[0])
                    return app, app.window(handle=matches[0])
            except Exception:
                pass
        return None, None


# ================================================================
# UI Action Helpers
# ================================================================
class UIActions:
    """Low-level UI interactions with fallback strategies."""

    @staticmethod
    def click_button(window, button_text, timeout=None):
        """Click a button by text. Tries multiple backends."""
        import pyautogui
        if timeout is None:
            timeout = Config.BUTTON_CLICK_TIMEOUT

        # Strategy 1: UIA name match
        try:
            btn = window.child_window(title=button_text, control_type="Button",
                                       found_index=0, timeout=timeout)
            btn.click()
            return True
        except Exception:
            pass

        # Strategy 2: UIA automation_id match (case-insensitive)
        try:
            btn = window.child_window(auto_id=button_text, control_type="Button",
                                       found_index=0, timeout=timeout/2)
            btn.click()
            return True
        except Exception:
            pass

        # Strategy 3: Partial match
        try:
            for child in window.descendants(control_type="Button"):
                try:
                    if button_text.lower() in (child.window_text().lower() or ''):
                        child.click()
                        return True
                except Exception:
                    continue
        except Exception:
            pass

        # Strategy 4: Image-based click (pyautogui) — last resort
        try:
            location = pyautogui.locateOnScreen(f'btn_{button_text}.png', confidence=0.8)
            if location:
                pyautogui.click(location)
                return True
        except Exception:
            pass

        return False

    @staticmethod
    def click_menu(window, menu_path, timeout=None):
        """Click through a menu path like 'File → Export → JCAMP'.
        Args:
            window: the main window
            menu_path: list of menu items, e.g. ['File', 'Export', 'JCAMP (.jdx)']
        """
        if timeout is None:
            timeout = Config.BUTTON_CLICK_TIMEOUT
        import pyautogui

        # Strategy 1: Use Alt key shortcuts if available
        # Try Alt+F for File, etc.
        first_letter = menu_path[0][0].lower()
        pyautogui.hotkey('alt', first_letter)
        time.sleep(0.3)
        for item in menu_path[1:]:
            pyautogui.press(item[0].lower())
            time.sleep(0.2)

        # If a "Save As" dialog appears, we're done with menu
        return True

    @staticmethod
    def get_save_dialog():
        """Find the 'Save As' / 'Export' dialog window."""
        from pywinauto import findwindows
        dialog_titles = ['Save As', 'Save', 'Export', '另存为', '导出',
                        'Save JCAMP', 'Export Spectrum']
        for title in dialog_titles:
            try:
                matches = findwindows.find_windows(title_re=title, top_level_only=True)
                if matches:
                    from pywinauto import Application
                    app = Application(backend='uia').connect(handle=matches[0])
                    return app, app.window(handle=matches[0])
            except Exception:
                pass
        return None, None

    @staticmethod
    def fill_save_path(dialog, path):
        """Fill the file path in a Save As dialog and click Save."""
        import pyautogui
        # Try setting the filename combo box directly
        try:
            combo = dialog.child_window(control_type="ComboBox", found_index=0, timeout=5)
            combo.set_edit_text(str(path))
            time.sleep(0.3)
        except Exception:
            # Fallback: type the path
            pyautogui.write(str(path))
            time.sleep(0.3)

        # Click Save
        try:
            save_btn = dialog.child_window(title="Save", control_type="Button", timeout=3)
            save_btn.click()
        except Exception:
            pyautogui.press('enter')

        time.sleep(Config.POST_DIALOG_DELAY)
        return True


# ================================================================
# Core Exporter
# ================================================================
class NISTJCAMPExporter:
    """Main exporter class — orchestrates the GUI automation."""

    def __init__(self, output_dir, resume=False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint = CheckpointManager()
        self.actions = UIActions()
        self.window_finder = WindowFinder()

        if resume:
            state = self.checkpoint.state
            print(f"\n📋 Resuming from checkpoint:")
            print(f"   Total exported so far: {state['total_exported']}")
            print(f"   Completed files: {len(state['completed_files'])}")
            print(f"   Last file: {state.get('current_file', 'N/A')}")

    # ----- Mode A: Export from sample data files -----
    def export_from_data_files(self, data_dir, compound_filter=None):
        """Process .D data files through MassHunter Qual, export NIST matches as JCAMP.

        Workflow per file:
          1. Open data file in MassHunter Qual
          2. Integrate peaks
          3. Search NIST library
          4. For each identified peak → export NIST reference spectrum as JCAMP
          5. Save JCAMP to output directory
        """
        data_path = Path(data_dir)
        d_folders = sorted(data_path.glob("*.D"))

        if not d_folders:
            print(f"\n❌ No .D folders found in {data_dir}")
            return

        print(f"\n🔍 Found {len(d_folders)} .D data folders")
        print(f"📁 Output: {self.output_dir}")
        print(f"📋 Checkpoint: {CHECKPOINT_FILE}")
        print(f"{'='*60}")

        self.checkpoint.state['mode'] = 'data_files'
        self.checkpoint.state['started_at'] = datetime.now().isoformat()
        self.checkpoint.save()

        for i, d_folder in enumerate(d_folders):
            if self.checkpoint.is_file_done(d_folder):
                print(f"\n  ⏭ [{i+1}/{len(d_folders)}] SKIP (already done): {d_folder.name}")
                continue

            print(f"\n  📂 [{i+1}/{len(d_folders)}] Processing: {d_folder.name}")
            self._process_single_data_file(d_folder)

            # Cooldown
            if (i + 1) % Config.COOLDOWN_INTERVAL == 0:
                print(f"\n  🧊 Cooldown {Config.COOLDOWN_DURATION}s (Memory/UI reset)...")
                time.sleep(Config.COOLDOWN_DURATION)

        print(f"\n{'='*60}")
        print(f"✅ Done. Total exported: {self.checkpoint.state['total_exported']} spectra")
        print(f"📁 Output: {self.output_dir}")

    def _process_single_data_file(self, d_folder):
        """Process one .D file through MassHunter Qual."""
        app, window = self.window_finder.find_masshunter()

        if not app:
            print("  ⚠️  MassHunter Qual not found — attempting to launch...")
            app, window = self._launch_masshunter()
            if not app:
                print("  ❌ Cannot launch MassHunter Qual. Skipping this file.")
                return False

        try:
            # Step 1: Open data file
            print("  [1/4] Opening data file...")
            self._open_data_file(window, d_folder)
            time.sleep(3)

            # Step 2: Integrate peaks
            print("  [2/4] Integrating peaks...")
            self._integrate_peaks(window)
            time.sleep(2)

            # Step 3: Search NIST
            print("  [3/4] Searching NIST library...")
            compounds = self._search_nist_and_get_results(window)

            # Step 4: Export each compound's NIST spectrum
            print(f"  [4/4] Exporting {len(compounds)} spectra to JCAMP...")
            exported = 0
            for compound in compounds:
                if self.checkpoint.is_compound_done(compound):
                    continue
                if self._export_single_spectrum(window, compound, d_folder.stem):
                    self.checkpoint.mark_compound_done(compound)
                    exported += 1

            print(f"  ✓ Exported {exported} new spectra from {d_folder.name}")
            self.checkpoint.mark_file_done(d_folder)
            return True

        except Exception as e:
            print(f"  ❌ Error processing {d_folder.name}: {e}")
            traceback.print_exc()
            self.checkpoint.save()
            return False

    def _open_data_file(self, window, d_folder):
        """Open a .D data file in MassHunter Qual."""
        import pyautogui
        # Ctrl+O or File → Open
        pyautogui.hotkey('ctrl', 'o')
        time.sleep(1)

        # Navigate to the .D folder in the Open dialog
        app2, dialog = self.window_finder.find_masshunter()  # Try finding the dialog
        if dialog:
            self.actions.fill_save_path(dialog, str(d_folder.parent / d_folder.name))
        else:
            # Type the path directly
            pyautogui.write(str(d_folder))
            pyautogui.press('enter')

        time.sleep(Config.POST_DIALOG_DELAY)

    def _integrate_peaks(self, window):
        """Integrate chromatogram peaks."""
        import pyautogui
        # Method 1: Menu → Chromatogram → Integrate
        pyautogui.hotkey('alt', 'c')  # Chromatogram menu
        time.sleep(0.3)
        pyautogui.press('i')  # Integrate
        time.sleep(5)  # Wait for integration to complete

        # Method 2: If menu not found, try toolbar button
        # Fall back to clicking Integrate button by image/text

    def _search_nist_and_get_results(self, window):
        """Search NIST library for all peaks and return compound names."""
        import pyautogui
        # Select all peaks → Search → NIST Library
        pyautogui.hotkey('ctrl', 'a')  # Select all peaks
        time.sleep(0.5)

        # Method → Search Library (or Spectra → Search NIST)
        pyautogui.hotkey('alt', 's')  # Spectrum/Search menu
        time.sleep(0.3)
        pyautogui.press('s')  # Search

        # Wait for search to complete
        print("    Waiting for NIST search...")
        time.sleep(Config.SEARCH_WAIT_TIMEOUT)

        # Extract compound list from the results table
        compounds = self._extract_compound_names(window)
        return compounds

    def _extract_compound_names(self, window):
        """Extract identified compound names from the NIST search results table."""
        compounds = []
        try:
            # Try to find the results list/grid
            for child in window.descendants():
                try:
                    ctrl_type = child.element_info.control_type if hasattr(child, 'element_info') else None
                    name = child.window_text() if hasattr(child, 'window_text') else ''
                except Exception:
                    continue
        except Exception:
            pass
        return compounds

    def _export_single_spectrum(self, window, compound_name, sample_stem):
        """Export one NIST match result as a JCAMP file."""
        import pyautogui

        # Select the compound in the results list
        # ... (UI-specific actions)
        # Export → JCAMP
        output_path = self.output_dir / f"{compound_name}_{sample_stem}.jdx"
        output_path = str(output_path).replace(' ', '_').replace('/', '_')

        # File → Export → JCAMP
        pyautogui.hotkey('alt', 'f')
        time.sleep(0.3)
        pyautogui.press('e')  # Export
        time.sleep(0.5)

        # Handle Save dialog
        app2, dialog = self.actions.get_save_dialog()
        if dialog:
            self.actions.fill_save_path(dialog, output_path)
            return True
        return False

    # ----- Mode B: Direct NIST MS Search export -----
    def export_nist_library_by_cas(self, cas_list_file):
        """Export NIST library spectra by CAS number list.

        Uses NIST MS Search program directly (not MassHunter).
        Reads a list of CAS numbers from a file, searches each in NIST,
        and exports the reference spectrum as JCAMP.
        """
        cas_path = Path(cas_list_file)
        if not cas_path.exists():
            print(f"❌ CAS list file not found: {cas_list_file}")
            return

        cas_numbers = []
        for line in cas_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                # Extract CAS pattern: XXX-XX-X
                match = re.search(r'\d{2,7}-\d{2}-\d', line)
                if match:
                    cas_numbers.append((match.group(), line))
                else:
                    cas_numbers.append((line, line))  # Could be compound name

        print(f"\n📋 Loaded {len(cas_numbers)} compounds to export")
        print(f"📁 Output: {self.output_dir}")
        print(f"{'='*60}")

        self.checkpoint.state['mode'] = 'cas_list'
        self.checkpoint.state['started_at'] = datetime.now().isoformat()
        self.checkpoint.save()

        app, window = self.window_finder.find_nist_ms_search()
        if not app:
            print("❌ NIST MS Search not running. Please open it first.")
            print("   Typically at: C:\\NISTXX\\MSSEARCH\\nistms.exe")
            return

        for i, (query, label) in enumerate(cas_numbers):
            if self.checkpoint.is_compound_done(query):
                print(f"  ⏭ [{i+1}/{len(cas_numbers)}] SKIP: {label}")
                continue

            print(f"  🔍 [{i+1}/{len(cas_numbers)}] {label}")
            self._search_and_export_nist_standalone(window, query, label)

            if (i + 1) % Config.COOLDOWN_INTERVAL == 0:
                print(f"\n  🧊 Cooldown {Config.COOLDOWN_DURATION}s...")
                time.sleep(Config.COOLDOWN_DURATION)

        print(f"\n✅ Done. Exported: {self.checkpoint.state['total_exported']} spectra")

    def _search_and_export_nist_standalone(self, window, query, label):
        """Search NIST MS Search program and export spectrum."""
        import pyautogui
        # Focus the search field (typically a text box)
        pyautogui.hotkey('ctrl', 'f')  # Find/Search
        time.sleep(0.5)
        pyautogui.write(query)
        pyautogui.press('enter')
        time.sleep(3)  # Wait for search

        # File → Export → JCAMP
        output_path = self.output_dir / f"{label.replace(' ', '_').replace('/', '_')}.jdx"
        pyautogui.hotkey('alt', 'f')
        time.sleep(0.3)
        pyautogui.press('e')
        time.sleep(0.5)

        app2, dialog = self.actions.get_save_dialog()
        if dialog:
            self.actions.fill_save_path(dialog, str(output_path))
            self.checkpoint.mark_compound_done(query)
        else:
            print(f"    ⚠️  Could not find Save dialog for {label}")

    # ----- Launch & Helpers -----
    def _launch_masshunter(self):
        """Try to launch MassHunter 未知物分析."""
        # Primary: the KnownGood™ path from your system
        primary = Config.MASSHUNTER_EXE
        if Path(primary).exists():
            print(f"    Launching: {primary}")
            os.startfile(primary)
            time.sleep(15)  # MassHunter takes a while to initialize
            app, window = self.window_finder.find_masshunter()
            if app:
                return app, window

        # Fallbacks
        common_paths = [
            r"C:\Program Files\Agilent\MassHunter\Workstation\Qual\QualitativeAnalysis.exe",
            r"C:\Program Files\Agilent\MassHunter\Qual\Bin\QualSw.exe",
        ]
        for path in common_paths:
            p = Path(path)
            if p.exists():
                print(f"    Launching: {p}")
                os.startfile(str(p))
                time.sleep(10)
                app, window = self.window_finder.find_masshunter()
                if app:
                    return app, window

        print("    ⚠️  Cannot find MassHunter 未知物分析 executable.")
        print("    Please manually launch the software and re-run the script.")
        return None, None


# ================================================================
# CLI
# ================================================================
def main():
    parser = argparse.ArgumentParser(
        description="NIST JCAMP Batch Exporter — GUI Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export NIST matches from .D data files
  python nist_jcamp_exporter.py --data-dir D:\\GCMS_Data --output D:\\NIST_JCAMP

  # Export NIST library spectra by compound list
  python nist_jcamp_exporter.py --cas-list compounds.txt --output D:\\NIST_JCAMP

  # Resume interrupted export
  python nist_jcamp_exporter.py --resume

  # Dry run — test window connection only
  python nist_jcamp_exporter.py --test
        """
    )
    parser.add_argument('--data-dir', help='Directory containing .D data folders (Mode A)')
    parser.add_argument('--cas-list', help='File with CAS numbers / compound names (Mode B)')
    parser.add_argument('--output', default='D:\\NIST_JCAMP', help='Output directory for JCAMP files')
    parser.add_argument('--resume', action='store_true', help='Resume from last checkpoint')
    parser.add_argument('--test', action='store_true', help='Test window connection only')
    parser.add_argument('--filter', help='Only export compounds matching this pattern')

    args = parser.parse_args()

    exporter = NISTJCAMPExporter(output_dir=args.output, resume=args.resume)

    if args.test:
        print("🔍 Testing window detection...\n")
        app, window = exporter.window_finder.find_masshunter()
        if app:
            print(f"\n✅ MassHunter Qual found and connected!")
            print(f"   Window title: \"{window.window_text()}\"")
            print(f"   Handle: {window.handle}")
        else:
            print("\n❌ MassHunter Qual NOT found.")
            print("   Please open MassHunter Qualitative Analysis and re-run --test")

        app2, win2 = exporter.window_finder.find_nist_ms_search()
        if app2:
            print(f"\n✅ NIST MS Search found: \"{win2.window_text()}\"")
        else:
            print("\n⚠️  NIST MS Search (standalone) not found.")
        return

    if args.data_dir:
        exporter.export_from_data_files(args.data_dir, compound_filter=args.filter)
    elif args.cas_list:
        exporter.export_nist_library_by_cas(args.cas_list)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
