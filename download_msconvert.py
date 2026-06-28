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
import shutil
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).parent / "tools"
MSCONVERT_EXE = TOOLS_DIR / "msconvert.exe"

# Latest ProteoWizard release URLs
PROTEOWIZARD_SF_URL = (
    "https://sourceforge.net/projects/proteowizard/files/latest/download"
)

# Common install paths to check first
COMMON_PATHS = [
    r"C:\Program Files\ProteoWizard\ProteoWizard 3.0\msconvert.exe",
    r"C:\Program Files (x86)\ProteoWizard\ProteoWizard 3.0\msconvert.exe",
    r"D:\ProteoWizard\msconvert.exe",
]


def find_existing_install():
    """Search common paths for an existing msconvert installation.

    Returns path string if found, None otherwise.
    """
    for p in COMMON_PATHS:
        if os.path.exists(p):
            return p
    return None


def save_path_reference(msconvert_path):
    """Save a reference to an externally-installed msconvert."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    ref_file = Path(str(MSCONVERT_EXE) + '.path')
    with open(ref_file, 'w') as f:
        f.write(msconvert_path)
    print(f"  Saved path reference to: {ref_file}")
    print(f"  → {msconvert_path}")


def download_with_progress(url, dest_path, desc="Downloading"):
    """Download a file with progress indication.

    Returns True on success, False on failure.
    """
    import urllib.request
    import urllib.error

    print(f"  {desc}...")
    print(f"  Source: {url}")

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        })

        with urllib.request.urlopen(req, timeout=30) as response:
            total = response.headers.get('Content-Length')
            if total:
                total = int(total)
                print(f"  Size: {total / 1024 / 1024:.0f} MB")

            downloaded = 0
            chunk_size = 1024 * 1024  # 1 MB chunks

            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total:
                        pct = downloaded / total * 100
                        mb_done = downloaded / 1024 / 1024
                        mb_total = total / 1024 / 1024
                        print(f"\r    {mb_done:.0f}/{mb_total:.0f} MB "
                              f"({pct:.0f}%)", end='', flush=True)

            if total:
                print()  # newline after progress
            print(f"  ✓ Download complete: {dest_path.name}")
            return True

    except urllib.error.HTTPError as e:
        print(f"\n  ✗ HTTP error: {e.code} {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"\n  ✗ Connection error: {e.reason}")
        return False
    except Exception as e:
        print(f"\n  ✗ Download failed: {e}")
        return False


def extract_msi(msi_path, extract_dir):
    """Extract files from an MSI installer using msiexec /a.

    This performs an administrative install (extracts without running).
    Returns True on success.
    """
    print(f"  Extracting MSI (this may take a minute)...")
    try:
        result = subprocess.run(
            ["msiexec", "/a", str(msi_path), "/qn",
             f"TARGETDIR={extract_dir}"],
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  ⚠ MSI extraction timed out")
        return False
    except FileNotFoundError:
        print("  ⚠ msiexec not found — can't extract MSI")
        return False


def extract_zip(zip_path, extract_dir):
    """Extract a ZIP archive. Returns True on success."""
    print(f"  Extracting ZIP...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        return True
    except zipfile.BadZipFile:
        print("  ✗ Bad ZIP file")
        return False
    except Exception as e:
        print(f"  ✗ Extraction failed: {e}")
        return False


def find_msconvert_in_dir(search_dir):
    """Recursively search for msconvert.exe in a directory tree.

    Returns the Path if found, None otherwise.
    """
    for root, dirs, files in os.walk(search_dir):
        for f in files:
            if f.lower() == 'msconvert.exe':
                return Path(root) / f
    return None


def try_download_msconvert():
    """Attempt to download and set up msconvert automatically.

    Returns True if successful.
    """
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Check for existing installations
    existing = find_existing_install()
    if existing:
        print(f"  ✓ Found existing installation: {existing}")
        save_path_reference(existing)
        return True

    # Step 2: Download from SourceForge
    print("  No existing installation found.")
    print("  Downloading ProteoWizard from SourceForge...")
    print()

    tmp_dir = Path(tempfile.mkdtemp(prefix="pwiz_"))
    download_path = tmp_dir / "ProteoWizard_installer.msi"

    try:
        success = download_with_progress(
            PROTEOWIZARD_SF_URL, download_path,
            desc="Downloading ProteoWizard"
        )
        if not success:
            return False

        # Step 3: Extract based on file type
        # SourceForge redirects to actual filename; check extension
        actual_name = download_path.name.lower()

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir(exist_ok=True)

        if actual_name.endswith('.zip'):
            if not extract_zip(download_path, extract_dir):
                return False
        elif actual_name.endswith('.msi'):
            if not extract_msi(download_path, extract_dir):
                print("  ⚠ MSI extraction failed — trying as ZIP...")
                if not extract_zip(download_path, extract_dir):
                    return False
        else:
            # Unknown format — try both
            if not extract_msi(download_path, extract_dir):
                if not extract_zip(download_path, extract_dir):
                    print("  ✗ Cannot extract downloaded file "
                          f"({actual_name})")
                    return False

        # Step 4: Find msconvert.exe in extracted files
        msconvert_path = find_msconvert_in_dir(extract_dir)
        if not msconvert_path:
            # Also check the download dir (some ZIPs extract at top level)
            msconvert_path = find_msconvert_in_dir(tmp_dir)

        if msconvert_path:
            # Copy to tools directory
            dest = MSCONVERT_EXE
            print(f"  Copying msconvert.exe to {dest}...")
            shutil.copy2(str(msconvert_path), str(dest))
            print(f"  ✓ msconvert.exe ready: {dest}")
            return True
        else:
            print("  ✗ msconvert.exe not found in downloaded package.")
            print("  The package structure may have changed.")
            print(f"  Extracted files are at: {extract_dir}")
            return False

    finally:
        # Clean up temp files (keep extracted msconvert only)
        try:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def print_manual_instructions():
    """Print manual download and installation instructions."""
    print(f"""
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
║     {TOOLS_DIR}\\msconvert.exe                              ║
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
""")


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
        print(f"  ✓ msconvert found: {MSCONVERT_EXE}")
        return

    # Check for path reference file
    path_ref = Path(str(MSCONVERT_EXE) + '.path')
    if path_ref.exists():
        with open(path_ref, 'r') as f:
            ref_path = f.read().strip()
        if os.path.exists(ref_path):
            print(f"  ✓ msconvert found at: {ref_path}")
            return
        else:
            print(f"  ⚠  Referenced msconvert not found: {ref_path}")
            path_ref.unlink()

    # Try automatic download + extraction
    success = try_download_msconvert()

    if not success:
        print()
        print_manual_instructions()

    print()
    print("  After installing msconvert, the gcms_agent can read raw .D data")
    print("  via mass_spectra_reader.py for full spectral matching.")


if __name__ == "__main__":
    main()
