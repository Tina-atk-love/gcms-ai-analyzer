#!/usr/bin/env python3
"""
NIST JCAMP Export - Hybrid (pywinauto menus + keyboard navigation)
====================================================================
Fast approach avoiding DataGridView enumeration:
  1. pywinauto opens menus (File -> Export JCAMP)
  2. pyautogui handles save dialog (type path, Enter)
  3. Keyboard presses Down arrow for next compound

Test first with 3 compounds:
  python tools/nist_export_hybrid.py --output OUTPUT_DIR --test

Full export (runs for hours - use Ctrl+C to pause, resume with --start):
  python tools/nist_export_hybrid.py --output D:/JCAMP_Export --total 306622
"""

import os, sys, re, time, json, argparse
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    import pygetwindow as gw
    from pywinauto import Desktop, Application
except ImportError as e:
    print(f"Missing: {e}. Install: pip install pyautogui pygetwindow pywinauto")
    sys.exit(1)

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05


class Checkpoint:
    def __init__(self, d):
        self.f = Path(d) / '_ckpt.json'
        self.s = json.loads(self.f.read_text()) if self.f.exists() else {'n':0,'err':[]}
    def save(self): self.f.write_text(json.dumps(self.s))
    def ok(self,i): return Path(self.f.parent/f'{i:06d}.jdx').exists()
    def done(self): self.s['n']+=1
    def err(self,i): self.s['err'].append(i)
    def cnt(self): return self.s['n']


def focus_editor():
    """Focus the Library Editor window."""
    ws = gw.getWindowsWithTitle('谱库')
    if not ws:
        print("[ERROR] Library Editor not found. Open it first.")
        return None
    w = ws[0]
    w.activate()
    time.sleep(0.3)
    return w


def export_current(output_dir, index):
    """Export current compound via menu → handle save dialog."""
    filepath = Path(output_dir) / f'{index:06d}.jdx'
    if filepath.exists():
        return True

    # Connect via pywinauto and click menu
    dw = Desktop(backend='uia')
    for w in dw.windows():
        if '谱库编辑器' in w.window_text():
            app = Application(backend='uia').connect(handle=w.handle)
            win = app.window(handle=w.handle)
            try:
                win.menu_select('文件(F)->导出 JCAMP 文件...')
            except:
                pass
            break

    # Wait for save dialog
    time.sleep(2)

    # Handle dialog with keyboard
    pyautogui.hotkey('ctrl', 'a')  # Select all in filename
    time.sleep(0.2)
    pyautogui.write(str(filepath))
    time.sleep(0.3)
    pyautogui.press('enter')

    # Wait and check
    time.sleep(1)
    return filepath.exists()


def run(output_dir, total, start=0, delay=0.8, test=False):
    """Main export loop."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ck = Checkpoint(output_dir)

    end = start + (3 if test else total)

    print(f"\n{'='*50}")
    print(f"  NIST JCAMP Hybrid Export")
    print(f"  Range: {start} → {end}")
    print(f"  Output: {output_dir}")
    print(f"  MOUSE TO TOP-LEFT CORNER TO ABORT")
    print(f"{'='*50}\n")

    # Focus the editor
    if not focus_editor():
        return

    if not test:
        for i in range(5,0,-1):
            print(f"  Starting in {i}...")
            time.sleep(1)

    print("  GO! Select the FIRST compound, then press Enter here.")
    input("  Press ENTER when ready...")

    t0 = time.time()
    ok = skip = err = 0

    for i in range(start, end):
        if ck.ok(i):
            skip += 1
            pyautogui.press('down'); time.sleep(0.08)
            continue

        if export_current(output_dir, i):
            ck.done(); ok += 1
        else:
            ck.err(i); err += 1

        # Next compound
        pyautogui.press('down')
        time.sleep(delay)

        if (i+1) % 100 == 0:
            ck.save()
            elapsed = time.time() - t0
            rate = (i+1-start)/elapsed if elapsed>0 else 0
            eta = (end-i-1)/rate if rate>0 else 0
            print(f"  [{i+1:7,}] ok={ok} skip={skip} err={err} | {rate:.1f}/s | ETA: {eta/3600:.1f}h")

    elapsed = time.time()-t0
    print(f"\n  Done in {elapsed/3600:.1f}h. ok={ok} skip={skip} err={err}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output','-o',default=r'C:\Users\86150\Desktop\JCAMP_Export')
    p.add_argument('--total','-t',type=int,default=306622)
    p.add_argument('--start','-s',type=int,default=0)
    p.add_argument('--delay','-d',type=float,default=0.6)
    p.add_argument('--test',action='store_true')
    a = p.parse_args()
    run(a.output, a.total, a.start, a.delay, a.test)
