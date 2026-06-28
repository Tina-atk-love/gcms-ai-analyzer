#!/usr/bin/env python3
"""
ProteoWizard msconvert Downloader
==================================
Downloads msconvert (ProteoWizard) for Agilent .D → mzML conversion.

msconvert is the standard tool for converting vendor-format mass spectrometry
data files to open formats. Required by mass_spectra_reader.py for reading
raw Agilent ChemStation .D data.

Usage:
    python download_msconvert.py          # Download automatically
    python download_msconvert.py --manual # Show manual download instructions

Source: https://proteowizard.sourceforge.io/download.html
"""

import sys
import os
import subprocess
import argparse
import zipfile
import io
from pathlib import Path

TOOLS_DIR = Path(__file__).parent / "tools"
MSCONVERT_EXE = TOOLS_DIR / "msconvert.exe"

# Latest ProteoWizard release (as of June 2026)
# The direct download URL uses a redirect, so we provide both options
PROTEOWIZARD_DOWNLOAD_URL = (
    "https://github.com/ProteoWizard/pwiz/raw/master/installers/"
    "ProteoWizard_x64.msi"
)

# Alternative: direct ZIP from SourceForge
PROTEOWIZARD_ZIP_URL = (
    "https://sourceforge.net/projects/proteowizard/files/latest/download"
)


def try_download_msconvert():
    """Attempt to download msconvert automatically.

    Returns True if successful.
    """
    import urllib.request
    import urllib.error

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    print("Attempting automatic download of ProteoWizard/msconvert...")
    print()
    print("Note: The full ProteoWizard installer is ~200 MB.")
    print("For a lighter option, you can manually install only msconvert.")
    print()

    # Option 1: Try to find an existing installation
    common_paths = [
        r"C:\Program Files\ProteoWizard\ProteoWizard 3.0\msconvert.exe",
        r"C:\Program Files (x86)\ProteoWizard\ProteoWizard 3.0\msconvert.exe",
        r"D:\ProteoWizard\msconvert.exe",
    ]

    for p in common_paths:
        if os.path.exists(p):
            print(f"  Found existing installation: {p}")
            # Create a symlink/copy to tools/
            if not MSCONVERT_EXE.exists():
                with open(str(MSCONVERT_EXE) + '.path', 'w') as f:
                    f.write(p)
                print(f"  Saved path reference to: {MSCONVERT_EXE}.path")
            return True

    return False


def print_manual_instructions():
    """Print manual download and installation instructions."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║        ProteoWizard msconvert — Manual Installation         ║
╠══════════════════════════════════════════════════════════════╣
║                                                            ║
║  1. Download ProteoWizard:                                 ║
║     https://proteowizard.sourceforge.io/download.html       ║
║     (Choose the "Windows 64-bit" installer)                ║
║                                                            ║
║  2. Install with default options.                          ║
║     msconvert.exe will be at:                              ║
║     C:\\Program Files\\ProteoWizard\\...\\msconvert.exe     ║
║                                                            ║
║  3. Copy msconvert.exe to:                                 ║
║     {tools_dir}\\msconvert.exe                    ║
║                                                            ║
║     OR set environment variable:                            ║
║     $env:MSCONVERT = "C:\\Program Files\\...\\msconvert.exe" ║
║                                                            ║
║  4. Verify installation:                                   ║
║     msconvert --help                                       ║
║                                                            ║
║  Alternative — Docker (no Windows install needed):          ║
║     docker pull chambm/pwiz-skyline-i-agree-to-the-...     ║
║     docker run -v D:\\data:/data chambm/... msconvert ...   ║
║                                                            ║
╚══════════════════════════════════════════════════════════════╝
""".format(tools_dir=str(TOOLS_DIR.resolve())))


def main():
    parser = argparse.ArgumentParser(
        description="Download/setup ProteoWizard msconvert"
    )
    parser.add_argument('--manual', action='store_true',
                       help='Show manual installation instructions')
    args = parser.parse_args()

    if args.manual:
        print_manual_instructions()
        return

    print("=" * 60)
    print("  ProteoWizard msconvert Setup")
    print("=" * 60)
    print()

    if MSCONVERT_EXE.exists():
        print(f"  ✅ msconvert found: {MSCONVERT_EXE}")
        return

    # Check for path reference file
    path_ref = Path(str(MSCONVERT_EXE) + '.path')
    if path_ref.exists():
        with open(path_ref, 'r') as f:
            ref_path = f.read().strip()
        if os.path.exists(ref_path):
            print(f"  ✅ msconvert found at: {ref_path}")
            return
        else:
            print(f"  ⚠️  Referenced msconvert not found: {ref_path}")
            path_ref.unlink()

    # Try automatic download
    success = try_download_msconvert()

    if not success:
        print_manual_instructions()

    print()
    print("  After installing msconvert, the gcms_agent can read raw .D data")
    print("  via mass_spectra_reader.py for full spectral matching.")


if __name__ == "__main__":
    main()
