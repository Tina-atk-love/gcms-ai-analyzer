#!/usr/bin/env python3
"""
ProteoWizard msconvert Downloader
==================================
Downloads msconvert (ProteoWizard) for Agilent .D -> mzML conversion.

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

# ----- Download URLs (tried in order) -----

# GitHub releases: more reliable, direct S3-backed downloads
GITHUB_API_URL = (
    "https://api.github.com/repos/ProteoWizard/pwiz/releases/latest"
)

# SourceForge direct (bypasses mirrors)
SF_DIRECT_TEMPLATE = (
    "https://sourceforge.net/projects/proteowizard/files/"
    "ProteoWizard%20version%20{version}/"
    "pwiz-setup-{version}-x64.msi/download"
)

# SourceForge latest (redirect-based)
SF_LATEST_URL = (
    "https://sourceforge.net/projects/proteowizard/files/latest/download"
)

# Common install paths to check first
COMMON_PATHS = [
    r"C:\Program Files\ProteoWizard\ProteoWizard 3.0\msconvert.exe",
    r"C:\Program Files (x86)\ProteoWizard\ProteoWizard 3.0\msconvert.exe",
    r"D:\ProteoWizard\msconvert.exe",
]

# Unicode-safe status markers (GBK console compatible)
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"


def safe_print(*args, **kwargs):
    """Print safely to Windows GBK console."""
    text = " ".join(str(a) for a in args)
    # Replace any chars that can't be encoded in common Windows code pages
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        text = text.encode(sys.stdout.encoding or 'ascii',
                           errors='replace').decode(
            sys.stdout.encoding or 'ascii', errors='replace')
        print(text, **kwargs)


def find_existing_install():
    """Search common paths for an existing msconvert installation."""
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
    safe_print(f"  {OK} Saved path reference: {ref_file}")
    safe_print(f"     -> {msconvert_path}")


def download_via_requests(url, dest_path, desc="Downloading"):
    """Download using requests library (best redirect/cookie handling).

    Returns True on success.
    """
    import requests

    safe_print(f"  {desc}...")
    safe_print(f"  Source: {url}")

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/130.0.0.0 Safari/537.36'
        ),
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    try:
        resp = requests.get(url, headers=headers, stream=True,
                           allow_redirects=True, timeout=60,
                           verify=True)
        if resp.status_code != 200:
            safe_print(f"  {FAIL} HTTP {resp.status_code}")
            return False

        total = None
        content_length = resp.headers.get('Content-Length')
        if content_length:
            total = int(content_length)
            safe_print(f"  Size: {total / 1024 / 1024:.0f} MB")

        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB

        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        mb_done = downloaded / 1024 / 1024
                        mb_total = total / 1024 / 1024
                        sys.stdout.write(
                            f"\r    {mb_done:.0f}/{mb_total:.0f} MB "
                            f"({pct:.0f}%)")
                        sys.stdout.flush()

        if total:
            sys.stdout.write("\n")
        safe_print(f"  {OK} Download complete: {dest_path.name}")
        return True

    except requests.exceptions.ConnectionError as e:
        safe_print(f"  {FAIL} Connection error: {e}")
        return False
    except requests.exceptions.Timeout:
        safe_print(f"  {FAIL} Timeout")
        return False
    except Exception as e:
        safe_print(f"  {FAIL} Download failed: {e}")
        return False


def download_via_urllib(url, dest_path, desc="Downloading"):
    """Fallback: download using urllib (no extra deps, less robust)."""
    import urllib.request
    import urllib.error
    import ssl

    safe_print(f"  {desc} (urllib fallback)...")
    safe_print(f"  Source: {url}")

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/130.0.0.0 Safari/537.36'
        ),
        'Accept': '*/*',
    }

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers=headers)

        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            total = resp.headers.get('Content-Length')
            if total:
                total = int(total)
                safe_print(f"  Size: {total / 1024 / 1024:.0f} MB")

            downloaded = 0
            chunk_size = 1024 * 1024

            with open(dest_path, 'wb') as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded / total * 100
                        mb_done = downloaded / 1024 / 1024
                        mb_total = total / 1024 / 1024
                        sys.stdout.write(
                            f"\r    {mb_done:.0f}/{mb_total:.0f} MB "
                            f"({pct:.0f}%)")
                        sys.stdout.flush()

        if total:
            sys.stdout.write("\n")
        safe_print(f"  {OK} Download complete: {dest_path.name}")
        return True

    except urllib.error.HTTPError as e:
        safe_print(f"  {FAIL} HTTP {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        safe_print(f"  {FAIL} Connection error: {e.reason}")
        return False
    except Exception as e:
        safe_print(f"  {FAIL} Download failed: {e}")
        return False


def download_with_progress(url, dest_path, desc="Downloading"):
    """Try requests first, fall back to urllib."""
    try:
        import requests
        return download_via_requests(url, dest_path, desc)
    except ImportError:
        return download_via_urllib(url, dest_path, desc)


def get_github_asset_url():
    """Query GitHub API for the latest ProteoWizard release MSI asset.

    Returns (download_url, filename) or (None, None).
    """
    import urllib.request
    import urllib.error
    import json

    safe_print(f"  {INFO} Querying GitHub releases API...")

    headers = {
        'User-Agent': 'gcms-analyzer/3.1',
        'Accept': 'application/vnd.github+json',
    }

    try:
        req = urllib.request.Request(GITHUB_API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        tag = data.get('tag_name', '')
        safe_print(f"  Latest release: {tag}")

        for asset in data.get('assets', []):
            name = asset.get('name', '')
            url = asset.get('browser_download_url', '')
            if name.endswith('.msi') and 'x64' in name:
                safe_print(f"  Found asset: {name}")
                return url, name

        # Fallback: any MSI
        for asset in data.get('assets', []):
            if asset.get('name', '').endswith('.msi'):
                safe_print(f"  Found asset: {asset['name']}")
                return asset['browser_download_url'], asset['name']

        return None, None

    except Exception as e:
        safe_print(f"  {WARN} GitHub API failed: {e}")
        return None, None


def try_download_msconvert():
    """Attempt to download and set up msconvert automatically.

    Returns True if successful.
    """
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Check for existing installations
    existing = find_existing_install()
    if existing:
        safe_print(f"  {OK} Found existing installation: {existing}")
        save_path_reference(existing)
        return True

    safe_print("  No existing installation found.")
    safe_print()

    # Step 2: Try multiple download sources
    tmp_dir = Path(tempfile.mkdtemp(prefix="pwiz_"))
    download_path = tmp_dir / "ProteoWizard_installer.msi"
    success = False

    # Source order: GitHub (most reliable) -> SourceForge latest -> manual
    sources = []

    # 2a: GitHub releases
    gh_url, gh_name = get_github_asset_url()
    if gh_url:
        sources.append(("GitHub Releases", gh_url))
        if gh_name:
            download_path = tmp_dir / gh_name

    # 2b: SourceForge latest
    sources.append(("SourceForge (latest)", SF_LATEST_URL))

    for source_name, url in sources:
        safe_print(f"  Trying: {source_name}")
        success = download_with_progress(url, download_path,
                                         desc=f"Downloading from {source_name}")
        if success:
            break
        safe_print()

    if not success:
        safe_print(f"  {FAIL} All download sources failed.")
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
        return False

    # Step 3: Extract based on file type
    safe_print()
    extract_dir = tmp_dir / "extracted"
    extract_dir.mkdir(exist_ok=True)

    actual_name = download_path.name.lower()

    if actual_name.endswith('.zip'):
        if not extract_zip(download_path, extract_dir):
            return False
    elif actual_name.endswith('.msi'):
        if not extract_msi(download_path, extract_dir):
            safe_print(f"  {WARN} MSI extraction failed, trying as ZIP...")
            if not extract_zip(download_path, extract_dir):
                return False
    else:
        if not extract_msi(download_path, extract_dir):
            if not extract_zip(download_path, extract_dir):
                safe_print(f"  {FAIL} Cannot extract: {actual_name}")
                return False

    # Step 4: Find msconvert.exe
    msconvert_path = find_msconvert_in_dir(extract_dir)
    if not msconvert_path:
        msconvert_path = find_msconvert_in_dir(tmp_dir)

    if msconvert_path:
        dest = MSCONVERT_EXE
        safe_print(f"  Copying msconvert.exe to {dest}...")
        shutil.copy2(str(msconvert_path), str(dest))
        safe_print(f"  {OK} msconvert.exe ready: {dest}")
        success = True
    else:
        safe_print(f"  {FAIL} msconvert.exe not found in downloaded package.")
        safe_print(f"  Extracted files at: {extract_dir}")
        success = False

    # Cleanup
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    return success


def extract_msi(msi_path, extract_dir):
    """Extract files from an MSI installer using msiexec /a.

    Performs an administrative install (extracts without running).
    """
    safe_print("  Extracting MSI (may take a minute)...")
    try:
        result = subprocess.run(
            ["msiexec", "/a", str(msi_path), "/qn",
             f"TARGETDIR={extract_dir}"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            safe_print(f"  {OK} MSI extraction complete")
            return True
        safe_print(f"  {WARN} msiexec returned {result.returncode}")
        return False
    except subprocess.TimeoutExpired:
        safe_print(f"  {WARN} MSI extraction timed out")
        return False
    except FileNotFoundError:
        safe_print(f"  {WARN} msiexec not found")
        return False


def extract_zip(zip_path, extract_dir):
    """Extract a ZIP archive."""
    safe_print("  Extracting ZIP...")
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(extract_dir)
        safe_print(f"  {OK} ZIP extraction complete")
        return True
    except zipfile.BadZipFile:
        safe_print(f"  {FAIL} Bad ZIP file")
        return False
    except Exception as e:
        safe_print(f"  {FAIL} Extraction failed: {e}")
        return False


def find_msconvert_in_dir(search_dir):
    """Recursively search for msconvert.exe in a directory tree."""
    for root, dirs, files in os.walk(search_dir):
        for f in files:
            if f.lower() == 'msconvert.exe':
                return Path(root) / f
    return None


def print_manual_instructions():
    """Print manual download and installation instructions."""
    tools_dir = str(TOOLS_DIR.resolve())
    safe_print(f"""
+======================================================================+
|        ProteoWizard msconvert -- Manual Installation                 |
+======================================================================+
|                                                                      |
|  1. Download ProteoWizard:                                           |
|     https://proteowizard.sourceforge.io/download.html                 |
|     (Choose the "Windows 64-bit" installer)                          |
|                                                                      |
|  2. Install with default options.                                    |
|     msconvert.exe will be at:                                        |
|     C:\\Program Files\\ProteoWizard\\...\\msconvert.exe               |
|                                                                      |
|  3. Copy msconvert.exe to:                                           |
|     {tools_dir}\\msconvert.exe                                        |
|                                                                      |
|     OR set environment variable:                                      |
|     $env:MSCONVERT = "C:\\Program Files\\...\\msconvert.exe"          |
|                                                                      |
|  4. Verify installation:                                             |
|     msconvert --help                                                 |
|                                                                      |
|  Alternative -- Docker (no Windows install needed):                   |
|     docker pull chambm/pwiz-skyline-i-agree-to-the-...               |
|     docker run -v D:\\data:/data chambm/... msconvert ...             |
|                                                                      |
+======================================================================+
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

    safe_print("=" * 60)
    safe_print("  ProteoWizard msconvert Setup")
    safe_print("=" * 60)
    safe_print()

    if MSCONVERT_EXE.exists():
        safe_print(f"  {OK} msconvert found: {MSCONVERT_EXE}")
        return

    # Check for path reference file
    path_ref = Path(str(MSCONVERT_EXE) + '.path')
    if path_ref.exists():
        with open(path_ref, 'r') as f:
            ref_path = f.read().strip()
        if os.path.exists(ref_path):
            safe_print(f"  {OK} msconvert found at: {ref_path}")
            return
        else:
            safe_print(f"  {WARN} Referenced msconvert not found: {ref_path}")
            path_ref.unlink()

    # Try automatic download + extraction
    success = try_download_msconvert()

    if not success:
        safe_print()
        print_manual_instructions()

    safe_print()
    safe_print("  After installing msconvert, gcms_agent can read raw .D data")
    safe_print("  via mass_spectra_reader.py for full spectral matching.")


if __name__ == "__main__":
    main()
