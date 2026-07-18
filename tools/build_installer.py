#!/usr/bin/env python3
"""
GC-MS AI Analyzer — Windows Installer Builder
===============================================
Builds a standalone Windows application:
  1. PyInstaller → single .exe file
  2. NSIS → Windows installer with shortcuts

Usage:
  python tools/build_installer.py          # Full build
  python tools/build_installer.py --light  # Lightweight (just exe, no installer)
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / 'dist' / 'installer'


def step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def check_deps():
    """Check required tools are installed."""
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"  [OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("  Installing PyInstaller...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller', '-q'])

    # Check NSIS
    nsis_paths = [
        r'C:\Program Files (x86)\NSIS\makensis.exe',
        r'C:\Program Files\NSIS\makensis.exe',
    ]
    nsis_found = any(Path(p).exists() for p in nsis_paths)
    if nsis_found:
        print(f"  [OK] NSIS found")
    else:
        print(f"  [INFO] NSIS not found — will build .exe only (no installer)")
        print(f"  [INFO] Install NSIS from: https://nsis.sourceforge.io/Download")

    return nsis_found


def generate_icon():
    """Generate a simple icon file using PIL."""
    icon_path = ROOT / 'icon.ico'
    if icon_path.exists():
        print(f"  [OK] Icon exists: {icon_path}")
        return

    try:
        from PIL import Image, ImageDraw
        print("  Generating icon...")

        # Create a 256x256 icon with a simple DNA/molecule motif
        img = Image.new('RGBA', (256, 256), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        # Background circle
        draw.ellipse([20, 20, 236, 236], fill='#1a5276')

        # Simple test-tube icon
        draw.rectangle([100, 40, 156, 180], fill='white', outline='white', width=4)
        draw.ellipse([90, 170, 166, 200], fill='white')
        draw.rectangle([108, 60, 148, 100], fill='#1a5276')

        # Save as .ico
        img.save(icon_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
        print(f"  [OK] Icon created: {icon_path}")
    except ImportError:
        print(f"  [WARN] PIL not installed — skipping icon")
        print(f"  [FIX] pip install Pillow")


def build_pyinstaller():
    """Build standalone .exe with PyInstaller."""
    spec_file = ROOT / 'gcms_analyzer.spec'

    print("  Building .exe (this may take 5-10 minutes)...")
    result = subprocess.run(
        [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(spec_file)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    exe_path = ROOT / 'dist' / 'GCMS-AI-Analyzer.exe'
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"  [OK] .exe built: {exe_path} ({size_mb:.0f} MB)")
        return exe_path
    else:
        print(f"  [FAIL] PyInstaller build failed")
        print(f"  stdout: {result.stdout[-500:]}")
        print(f"  stderr: {result.stderr[-500:]}")
        return None


def create_portable_package(exe_path):
    """Create a portable ZIP package."""
    package_dir = ROOT / 'dist' / 'GCMS-AI-Analyzer-Portable'
    shutil.rmtree(package_dir, ignore_errors=True)
    package_dir.mkdir(parents=True, exist_ok=True)

    # Copy exe
    shutil.copy(exe_path, package_dir / 'GCMS-AI-Analyzer.exe')

    # Copy icon
    icon = ROOT / 'icon.ico'
    if icon.exists():
        shutil.copy(icon, package_dir / 'icon.ico')

    # Create README
    readme = """GC-MS AI Analyzer — Portable Edition
=====================================

Double-click GCMS-AI-Analyzer.exe to start.

Requirements:
  - Windows 10 or later
  - 2GB free RAM
  - No Python installation needed

First launch may take 30-60 seconds (extracting dependencies).
Subsequent launches are fast.

☕ Try Demo mode — no data, no API key needed.

For the full manual: https://github.com/Tina-atk-love/gcms-ai-analyzer
"""
    (package_dir / 'README.txt').write_text(readme)

    # Create ZIP
    zip_path = ROOT / 'dist' / 'GCMS-AI-Analyzer-Portable.zip'
    if zip_path.exists():
        zip_path.unlink()
    shutil.make_archive(
        str(ROOT / 'dist' / 'GCMS-AI-Analyzer-Portable'),
        'zip',
        str(package_dir),
    )

    zip_size = zip_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] Portable ZIP: {zip_path} ({zip_size:.0f} MB)")
    return zip_path


def main():
    print("GC-MS AI Analyzer — Installer Builder")
    print(f"Project root: {ROOT}")

    has_nsis = check_deps()
    generate_icon()

    step("Building standalone .exe (PyInstaller)")
    exe_path = build_pyinstaller()
    if not exe_path:
        print("\nBuild failed. Try: pip install pyinstaller Pillow")
        sys.exit(1)

    step("Creating portable package")
    zip_path = create_portable_package(exe_path)

    step("Done!")
    print(f"""
  Output files:
    {exe_path}
    {zip_path}

  To share with others:
    Send them the ZIP file → they extract → double-click → app opens in browser.

  To create a proper Windows installer (setup.exe):
    Install NSIS from https://nsis.sourceforge.io/Download
    Then run: python tools/build_installer.py
""")


if __name__ == '__main__':
    main()
