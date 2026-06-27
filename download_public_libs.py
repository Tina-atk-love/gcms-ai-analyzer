#!/usr/bin/env python3
"""
Download & Integrate Public GC-MS Spectral Libraries
=====================================================
Automatically downloads free/open-source mass spectral libraries
and integrates them into the agent's searchable library.
No registration, no API key, no payment required.

Sources:
  1. MassBank Europe (MSP format, from GitHub releases)
  2. NIST WebBook EI spectra (CSV, from Zenodo)
  3. MoNA — queried live (no download needed, see mona_client.py)

Usage:
    python download_public_libs.py              # Download all, then integrate
    python download_public_libs.py --massbank   # MassBank EU only
    python download_public_libs.py --webbook    # NIST WebBook only
    python download_public_libs.py --status     # Show current library status
"""

import requests
import zipfile
import io
import os
import sys
import json
import time
from pathlib import Path

# ============================================================
# Configuration
# ============================================================
OUTPUT_DIR = Path(__file__).parent / "public_libraries"
OUTPUT_DIR.mkdir(exist_ok=True)

# MassBank Europe GitHub
MASSBANK_API = "https://api.github.com/repos/MassBank/MassBank-data/releases/latest"

# NIST WebBook on Zenodo
ZENODO_RECORDS = [
    {
        "url": "https://zenodo.org/api/records/12786324",
        "name": "GCMS_NIST_WebBook_reference_library",
        "description": "NIST WebBook EI-MS reference library (CSV format, ~350K spectra)"
    },
    {
        "url": "https://zenodo.org/api/records/14944348",
        "name": "NIST_WebBook_alternative",
        "description": "Alternative NIST WebBook mirror"
    },
]

# MoNA bulk download (JSON export)
MONA_BULK_URL = "https://mona.fiehnlab.ucdavis.edu/downloads"


def download_massbank_eu():
    """Download MassBank Europe MSP library from GitHub releases."""
    print("=" * 60)
    print("📥 MassBank Europe Spectral Library")
    print("=" * 60)

    try:
        resp = requests.get(MASSBANK_API, timeout=30)
        if resp.status_code != 200:
            print(f"  ❌ GitHub API failed: HTTP {resp.status_code}")
            return None

        release = resp.json()
        print(f"  Release: {release.get('tag_name', 'unknown')}")
        print(f"  Published: {release.get('published_at', 'unknown')[:10]}")
        print(f"  Assets: {len(release.get('assets', []))} files")

        # Find MSP assets
        msp_assets = []
        for asset in release.get('assets', []):
            name = asset['name'].lower()
            if 'msp' in name:
                msp_assets.append(asset)

        if not msp_assets:
            print("  ❌ No MSP files in this release")
            for asset in release.get('assets', [])[:10]:
                print(f"    - {asset['name']} ({asset['size']/1024/1024:.1f} MB)")
            return None

        # Prefer EI-MS or GC-MS tagged, then "all", then any MSP
        priority_order = []
        for asset in msp_assets:
            name = asset['name'].lower()
            if 'ei' in name or 'gc' in name:
                priority_order.insert(0, asset)
            elif 'all' in name:
                priority_order.append(asset)
            else:
                priority_order.append(asset)

        downloaded = []
        for asset in priority_order[:2]:  # Download up to 2 MSP files
            name = asset['name']
            url = asset['browser_download_url']
            size_mb = asset['size'] / (1024 * 1024)

            # Skip if already downloaded (same size)
            out_path = OUTPUT_DIR / name
            if out_path.exists() and abs(out_path.stat().st_size - asset['size']) < 1000:
                print(f"  ⏭️  {name} already downloaded ({size_mb:.1f} MB)")
                downloaded.append(out_path)
                continue

            print(f"  Downloading: {name} ({size_mb:.1f} MB)...")
            try:
                dl_resp = requests.get(url, timeout=300)
                if dl_resp.status_code == 200:
                    with open(out_path, 'wb') as f:
                        f.write(dl_resp.content)
                    actual_mb = len(dl_resp.content) / (1024 * 1024)
                    print(f"  ✅ Saved: {out_path.name} ({actual_mb:.1f} MB)")
                    downloaded.append(out_path)
                else:
                    print(f"  ❌ Download failed: HTTP {dl_resp.status_code}")
            except Exception as e:
                print(f"  ❌ Error: {e}")

        return downloaded[0] if downloaded else None

    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def download_nist_webbook():
    """Download NIST WebBook GC-MS reference library from Zenodo."""
    print("\n" + "=" * 60)
    print("📥 NIST WebBook GC-MS Reference Library")
    print("=" * 60)

    for record in ZENODO_RECORDS:
        try:
            print(f"  Trying: {record['name']}")
            resp = requests.get(record['url'], timeout=30)
            if resp.status_code != 200:
                print(f"  ❌ Zenodo API failed: HTTP {resp.status_code}")
                continue

            data = resp.json()

            # Check for useful files
            files = data.get('files', [])
            if not files:
                print("  ❌ No files in this record")
                continue

            found_any = False
            for f in files:
                name = f.get('key', '')
                size_mb = f['size'] / (1024 * 1024)
                url = f['links']['self']

                # Download CSV, MSP, or JSON files
                ext = Path(name).suffix.lower()
                if ext not in ('.csv', '.msp', '.json', '.zip', '.gz', '.tsv'):
                    continue
                if 'license' in name.lower() or 'readme' in name.lower():
                    continue

                out_path = OUTPUT_DIR / name
                if out_path.exists() and abs(out_path.stat().st_size - f['size']) < 1000:
                    print(f"  ⏭️  {name} already downloaded ({size_mb:.1f} MB)")
                    found_any = True
                    continue

                print(f"  Downloading: {name} ({size_mb:.1f} MB)...")
                try:
                    dl_resp = requests.get(url, timeout=600)  # Longer timeout for big files
                    if dl_resp.status_code == 200:
                        with open(out_path, 'wb') as f_out:
                            f_out.write(dl_resp.content)
                        actual_mb = len(dl_resp.content) / (1024 * 1024)
                        print(f"  ✅ Saved: {name} ({actual_mb:.1f} MB)")
                        found_any = True

                        # If zip, extract MSP/CSV files
                        if ext == '.zip':
                            try:
                                with zipfile.ZipFile(out_path) as zf:
                                    for member in zf.namelist():
                                        member_ext = Path(member).suffix.lower()
                                        if member_ext in ('.msp', '.csv', '.json'):
                                            zf.extract(member, OUTPUT_DIR)
                                            print(f"  📦 Extracted: {member}")
                            except Exception as e:
                                print(f"  ⚠️  Zip extraction failed: {e}")

                    else:
                        print(f"  ❌ Download failed: HTTP {dl_resp.status_code}")
                except Exception as e:
                    print(f"  ❌ Error: {e}")

            if found_any:
                return True

        except Exception as e:
            print(f"  ❌ Error with {record['name']}: {e}")
            continue

    return False


def download_mona_bulk_export():
    """Download MoNA bulk export (JSON format) for offline use."""
    print("\n" + "=" * 60)
    print("📥 MoNA (MassBank of North America) Bulk Export")
    print("=" * 60)

    try:
        resp = requests.get(MONA_BULK_URL, timeout=30)
        if resp.status_code != 200:
            # Try alternate methods
            print("  MoNA bulk download page not accessible.")
            print("  MoNA will be queried via live API instead (no download needed).")
            print("  For bulk download, visit: https://mona.fiehnlab.ucdavis.edu/downloads")
            return None

        # Parse download page for JSON links
        import re
        text = resp.text
        json_urls = re.findall(r'href=["\']([^"\']+\.json[^"\']*)["\']', text)

        if json_urls:
            for url in json_urls[:3]:
                if not url.startswith('http'):
                    url = 'https://mona.fiehnlab.ucdavis.edu' + url
                name = Path(url).name
                out_path = OUTPUT_DIR / name
                if out_path.exists():
                    print(f"  ⏭️  {name} already exists")
                    continue

                print(f"  Downloading: {name}...")
                try:
                    dl_resp = requests.get(url, timeout=600)
                    if dl_resp.status_code == 200:
                        with open(out_path, 'wb') as f:
                            f.write(dl_resp.content)
                        print(f"  ✅ Saved: {name} ({len(dl_resp.content)/1024/1024:.1f} MB)")
                except Exception as e:
                    print(f"  ❌ {name}: {e}")

            if any(OUTPUT_DIR.glob("*.json")):
                return True

        print("  ℹ️  MoNA live API will be used for searches (no offline download needed)")
        return None

    except Exception as e:
        print(f"  MoNA bulk download unavailable: {e}")
        print("  Live API will be used instead.")
        return None


def show_library_status():
    """Display current library status."""
    print("=" * 60)
    print("📚 Current Public Library Status")
    print("=" * 60)

    files = sorted(OUTPUT_DIR.glob("*"))
    if not files:
        print("  No libraries downloaded yet.")
        print("  Run: python download_public_libs.py")
        return

    total_size = 0
    for f in files:
        if f.is_file() and not f.name.startswith('.'):
            size_mb = f.stat().st_size / (1024 * 1024)
            total_size += f.stat().st_size
            print(f"  📄 {f.name:50s} {size_mb:8.1f} MB")

    print(f"\n  Total: {len([f for f in files if not f.name.startswith('.')])} files, {total_size/1024/1024:.1f} MB")

    # Check for index
    try:
        from public_library_manager import PublicLibraryManager
        mgr = PublicLibraryManager()
        mgr.load_all()
        summary = mgr.get_library_summary()
        print(f"  Loaded entries: {summary['total_entries']}")
        print(f"  Unique CAS: {summary['total_unique_cas']}")
        print(f"  Sources: {summary['sources']}")
        print(f"  Categories: {json.dumps(summary.get('top_categories', {}), indent=2)}")
    except ImportError:
        print("  ⚠️  Install dependencies to load library: pip install pandas numpy")


def integrate_to_library():
    """Integrate downloaded libraries into the searchable manager."""
    print("\n" + "=" * 60)
    print("🔧 Integrating Libraries...")
    print("=" * 60)

    try:
        from public_library_manager import PublicLibraryManager
        mgr = PublicLibraryManager()
        n_total = mgr.load_all(include_downloaded=True)
        summary = mgr.get_library_summary()

        print(f"  ✅ Integration complete!")
        print(f"  Total searchable spectra: {n_total}")
        print(f"  Unique compounds (by CAS): {summary['total_unique_cas']}")
        print(f"  Sources:")
        for src, count in summary['sources'].items():
            print(f"    - {src}: {count} entries")
        print(f"  Categories: {summary['top_categories']}")

        return True
    except ImportError as e:
        print(f"  ⚠️  Integration skipped: {e}")
        print("  Libraries downloaded but not loaded. Install: pandas numpy")
        return False
    except Exception as e:
        print(f"  ❌ Integration failed: {e}")
        return False


# ============================================================
# Main
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Download & Integrate Public GC-MS Spectral Libraries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_public_libs.py                 # Download ALL + integrate
  python download_public_libs.py --massbank      # MassBank EU only
  python download_public_libs.py --webbook       # NIST WebBook only
  python download_public_libs.py --status        # Show current status
  python download_public_libs.py --no-download   # Just integrate existing files
        """
    )
    parser.add_argument('--massbank', action='store_true',
                       help='Download MassBank Europe only')
    parser.add_argument('--webbook', action='store_true',
                       help='Download NIST WebBook only')
    parser.add_argument('--mona', action='store_true',
                       help='Download MoNA bulk export')
    parser.add_argument('--status', action='store_true',
                       help='Show current library status')
    parser.add_argument('--no-download', action='store_true',
                       help='Skip download, just integrate existing files')
    parser.add_argument('--no-integrate', action='store_true',
                       help='Skip integration after download')
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  🔬 Public GC-MS Spectral Library Manager")
    print("  Open-Source NIST Alternative")
    print("=" * 60)
    print(f"  Library directory: {OUTPUT_DIR}")
    print()

    if args.status:
        show_library_status()
        return

    download_all = not (args.massbank or args.webbook or args.mona)

    results = {}

    if not args.no_download:
        if download_all or args.massbank:
            result = download_massbank_eu()
            results['massbank_eu'] = '✅' if result else '❌'

        if download_all or args.webbook:
            result = download_nist_webbook()
            results['nist_webbook'] = '✅' if result else '❌'

        if download_all or args.mona:
            result = download_mona_bulk_export()
            results['mona_bulk'] = '✅' if result else '⏭️ (live API)'

        # Summary
        print("\n" + "=" * 60)
        print("📊 Download Summary")
        print("=" * 60)
        for source, status in results.items():
            print(f"  {status} {source}")

    if not args.no_integrate:
        integrate_to_library()

    # Show final status
    print()
    show_library_status()

    print("\n💡 Usage with the AI Agent:")
    print("  The AI agent automatically uses these libraries when you:")
    print("  - Run /run (extract_all_data) → auto spectral matching")
    print("  - Say 'search public libraries' → search_public_libraries tool")
    print("  - Say 'identify peaks with open source library'")
    print()
    print("📖 For publication, cite:")
    print("  - MassBank: Horai et al. (2010) J. Mass Spectrom. 45(7), 703-714")
    print("  - MoNA: https://mona.fiehnlab.ucdavis.edu")
    print("  - NIST WebBook: Linstrom & Mallard (eds.), NIST SRD 69")
    print()


if __name__ == "__main__":
    main()
