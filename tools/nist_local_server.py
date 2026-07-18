#!/usr/bin/env python3
"""
 NIST Local Server — Parse & Serve YOUR Licensed NIST Library
==================================================================
Runs entirely on **your computer**. Reads YOUR licensed NIST MSSEARCH
library (.L format), creates a searchable local database, and serves
it via a local HTTP API that the gcms_analyzer connects to.

️  LEGAL: This tool does NOT contain or distribute any NIST data.
          It only reads NIST library files that YOU already own.
          No NIST spectra, names, or formulas are ever uploaded.

  How it works:
    1. You point it at your NIST library folder (e.g. .../NIST17.L/)
    2. It parses the binary format → extracts compound metadata
    3. Creates a local SQLite database (stays on your disk)
    4. Starts a local HTTP server at http://localhost:8765
    5. gcms_analyzer connects to localhost:8765 to search

  Usage:
    python nist_local_server.py --nist "C:\\NIST17\\MSSEARCH\\mainlib"
    python nist_local_server.py --nist "D:\\Database\\NIST17.L"
    python nist_local_server.py --nist ~/Desktop/NIST17.L --port 8765

  Endpoints:
    GET  /search?q=caffeine       — search by name/formula
    GET  /search?q=C8H10N4O2      — search by formula
    GET  /stats                    — database statistics
    GET  /health                   — server health check

  Once running, in gcms_analyzer CLI:
    /nist-local          (sets up connection)
    Then agent can call search_nist_local with any query.
"""

import argparse
import json
import os
import re
import sqlite3
import struct
import sys
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs


# ================================================================
# NIST MSSEARCH .L Format Parser
# ================================================================
class NISTParser:
    """Reads NIST MSSEARCH library format (.L directory).

    Format documentation (reverse-engineered from NIST 2017):
      header.ind:
        Bytes 0-3:   magic "22*" (version identifier)
        Bytes 4-7:   number of entries (big-endian uint32)
        Bytes 8+:    array of big-endian uint32 offsets into header file

      header:
        Variable-length records at the offsets from header.ind
        Each record ~825 bytes, contains null-terminated strings:
          - Compound name
          - Molecular formula
          - NIST MS number
          - Category/source
    """

    def __init__(self, lib_path):
        self.lib_path = Path(lib_path)
        self._validate()

    def _validate(self):
        """Check required files exist (case-insensitive on Windows)."""
        files = os.listdir(self.lib_path)
        files_lower = {f.lower(): f for f in files}

        required = ['header.ind', 'header']
        for req in required:
            if req not in files_lower:
                alt = [f for f in files_lower if req.replace('.', '') in f.lower()]
                if alt:
                    print(f"  Note: Using '{alt[0]}' for '{req}'")
                else:
                    raise FileNotFoundError(
                        f"Not a NIST .L directory: missing '{req}'\n"
                        f"Expected structure:\n"
                        f"  {self.lib_path}/\n"
                        f"    header       — compound metadata\n"
                        f"    header.ind   — entry index\n"
                        f"    CONDENSE     — spectra (condensed)\n"
                        f"    FULL.D       — spectra (full resolution)\n"
                    )

    def parse_entries(self):
        """Parse all compound entries from the NIST library.

        Returns list of dicts: {name, formula, source_file?}
        """
        # Read index
        ind_data = self._read_file('header.ind')
        num_entries = struct.unpack('>I', ind_data[4:8])[0]
        print(f"  Library declares {num_entries:,} entries")

        # Read offsets (big-endian uint32, starting at byte 8)
        offsets = []
        for i in range(8, len(ind_data), 4):
            off = struct.unpack('>I', ind_data[i:i+4])[0]
            offsets.append(off)

        # Filter valid offsets
        header_size = 260_000_000  # max expected header size
        valid_offsets = []
        for off in offsets:
            if off < header_size:
                if not valid_offsets or off > valid_offsets[-1]:
                    valid_offsets.append(off)

        print(f"  Valid offsets: {len(valid_offsets):,}")

        # Read header data
        header_data = self._read_file('header')
        print(f"  Header file: {len(header_data)/1024/1024:.0f} MB")

        # Parse entries
        entries = []
        skip_words = {'HP', 'DD', 'PChe', 'Gg', 'wH', 'w@', 'wPY', 'wtX', 'wPChe',
                      'il', 'le', 'te', 'al', 'gs', 'tate', 'NIST 2017', 'NIST',
                      'N-', '^N', 'sS', 'TN', 'HN', 'F0', 'X', 'lmitate', 'cetylmorphine'}

        total = len(valid_offsets)
        t0 = time.time()
        for i in range(total):
            off = valid_offsets[i]
            if off >= len(header_data):
                break

            end_off = valid_offsets[i + 1] if i + 1 < total else min(off + 2000, len(header_data))
            chunk = header_data[off:end_off]

            # Extract null-terminated strings
            strings = self._extract_strings(chunk)

            # Find name and formula
            name = None
            formula = None
            for s in strings:
                if s in skip_words:
                    continue
                if not name and len(s) >= 2:
                    # Skip formulas and pure numbers
                    if not re.match(r'^[A-Z][a-z]?\d*([A-Z][a-z]?\d*)+$', s):
                        if not re.match(r'^[\d\s\-\.]+$', s):
                            if not s.startswith('NIST MS#'):
                                name = s
                if not formula and re.match(r'^[A-Z][a-z]?\d*([A-Z][a-z]?\d*)+$', s) and 1 <= len(s) <= 25:
                    formula = s

            if name:
                entries.append({
                    'name': name.strip(),
                    'formula': formula.strip() if formula else None,
                })

            if (i + 1) % 50000 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                eta = (total - i - 1) / rate if rate > 0 else 0
                print(f"  Parsed {i+1:,}/{total:,} ({rate:.0f} entries/s, ETA: {eta:.0f}s)")

        elapsed = time.time() - t0
        print(f"  Done: {len(entries):,} valid entries in {elapsed:.1f}s")
        return entries

    def _read_file(self, name):
        """Read file from library with case-insensitive matching."""
        files_lower = {f.lower(): f for f in os.listdir(self.lib_path)}
        actual_name = files_lower.get(name.lower(), name)
        return (self.lib_path / actual_name).read_bytes()

    def _extract_strings(self, data):
        """Extract null-terminated ASCII strings from binary chunk."""
        strings = []
        current = b''
        for b in data:
            if 32 <= b < 127:
                current += bytes([b])
            else:
                if len(current) >= 2:
                    strings.append(current.decode('ascii', errors='replace'))
                current = b''
        if len(current) >= 2:
            strings.append(current.decode('ascii', errors='replace'))
        return strings


# ================================================================
# SQLite Database Builder
# ================================================================
def build_database(entries, db_path):
    """Create SQLite database from parsed NIST entries.

    Enables fast full-text search by name and formula.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove old DB if exists
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Create tables
    conn.execute("""
        CREATE TABLE compounds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            formula TEXT,
            name_lower TEXT NOT NULL
        )
    """)

    # Create indexes for fast search
    conn.execute("CREATE INDEX idx_name_lower ON compounds(name_lower)")
    conn.execute("CREATE INDEX idx_formula ON compounds(formula)")

    # Batch insert
    print(f"  Building SQLite database with {len(entries):,} entries...")
    rows = [(e['name'], e.get('formula'), e['name'].lower())
            for e in entries]

    conn.executemany(
        "INSERT INTO compounds (name, formula, name_lower) VALUES (?, ?, ?)",
        rows
    )

    conn.commit()

    # Stats
    count = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
    with_formula = conn.execute(
        "SELECT COUNT(*) FROM compounds WHERE formula IS NOT NULL"
    ).fetchone()[0]

    # Save metadata
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('created_at', ?)",
                 (datetime.now().isoformat(),))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('total_entries', ?)",
                 (str(count),))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('with_formula', ?)",
                 (str(with_formula),))
    conn.execute("INSERT OR REPLACE INTO metadata VALUES ('source', ?)",
                 ("User-provided NIST library (parsed locally)",))
    conn.commit()

    conn.close()

    print(f"  Database: {count:,} entries ({with_formula:,} with formula)")
    return db_path


# ================================================================
# Local HTTP API Server
# ================================================================
# ================================================================
# Spectrum Index & Cosine Search
# ================================================================
class SpectrumIndex:
    """Fast spectrum search index with base-peak pre-screening."""

    def __init__(self):
        self.spectra = []        # List of {name, formula, cas, peaks: [(mz,int),...]}
        self.base_peak_idx = {}  # base_peak_mz -> [spectrum_indices]
        self.loaded = False

    def load_jcamp_dir(self, jcamp_dir):
        """Scan JCAMP directory (with subdirs) and index all spectra."""
        import re
        jcamp_path = Path(jcamp_dir)
        if not jcamp_path.exists():
            print(f"  JCAMP dir not found: {jcamp_dir}")
            return 0

        print(f"  Scanning JCAMP files in {jcamp_dir}...")
        count = 0
        t0 = time.time()

        for jdx_file in jcamp_path.rglob("*.jdx"):
            try:
                text = jdx_file.read_text(encoding='utf-8', errors='ignore')
                spec = self._parse_jcamp(text)
                if spec and spec.get('peaks') and len(spec['peaks']) >= 3:
                    idx = len(self.spectra)
                    self.spectra.append(spec)
                    # Index by base peak
                    base = max(spec['peaks'], key=lambda x: x[1])[0]
                    base = (base // 10) * 10  # Round to nearest 10
                    if base not in self.base_peak_idx:
                        self.base_peak_idx[base] = []
                    self.base_peak_idx[base].append(idx)
                    count += 1
            except Exception:
                pass

            if count % 50000 == 0 and count > 0:
                print(f"    Indexed {count:,} spectra...")

        elapsed = time.time() - t0
        print(f"  Spectrum index: {count:,} spectra in {elapsed:.0f}s")
        self.loaded = True
        return count

    def _parse_jcamp(self, text):
        """Parse JCAMP-DX text into spectrum dict."""
        import re
        spec = {'name': '', 'formula': '', 'cas': '', 'peaks': []}
        in_peak_table = False
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('##TITLE='):
                spec['name'] = line[8:]
            elif line.startswith('##MOLFORM='):
                spec['formula'] = line[10:]
            elif line.startswith('##CAS'):
                spec['cas'] = line.split('=')[-1] if '=' in line else ''
            elif '##PEAK TABLE' in line:
                in_peak_table = True
            elif line.startswith('##END'):
                break
            elif in_peak_table:
                for pair in line.split():
                    try:
                        mz, intensity = pair.split(',')
                        spec['peaks'].append((int(mz), int(intensity)))
                    except:
                        pass
        return spec if spec['peaks'] else None

    def search_spectrum(self, query_peaks, max_results=20, min_match=600):
        """Cosine similarity search against indexed spectra.

        Args:
            query_peaks: list of (mz, intensity) tuples
            max_results: max results to return
            min_match: minimum match score (0-999)

        Returns:
            List of {name, formula, cas, match_score, n_peaks} dicts
        """
        if not self.spectra or not query_peaks:
            return []

        # Pre-screen: find candidate spectra sharing the base peak
        query_base = max(query_peaks, key=lambda x: x[1])[0]
        query_base_r = (query_base // 10) * 10

        candidates = set()
        for delta in [-10, 0, 10]:
            key = query_base_r + delta
            if key in self.base_peak_idx:
                candidates.update(self.base_peak_idx[key])

        if not candidates:
            # Fall back to broader search
            candidates = set(range(min(len(self.spectra), 50000)))

        # Normalize query
        q_max = max(p[1] for p in query_peaks)
        q_peaks = [(mz, i/q_max) for mz, i in query_peaks]

        results = []
        for idx in candidates:
            if idx >= len(self.spectra):
                continue
            ref = self.spectra[idx]
            score = self._cosine_match(q_peaks, ref['peaks'])
            if score >= min_match:
                results.append({
                    'name': ref['name'],
                    'formula': ref.get('formula', ''),
                    'cas': ref.get('cas', ''),
                    'match_score': score,
                    'n_peaks': len(ref['peaks']),
                })

        results.sort(key=lambda x: x['match_score'], reverse=True)
        return results[:max_results]

    def _cosine_match(self, query_peaks, ref_peaks):
        """Weighted cosine similarity (NIST-style)."""
        # Normalize reference
        r_max = max(p[1] for p in ref_peaks)
        r_norm = [(mz, i/r_max) for mz, i in ref_peaks]

        # Build sparse vectors
        q_dict = {int(mz): i for mz, i in query_peaks}
        r_dict = {int(mz): i for mz, i in r_norm}

        # Common fragment penalty
        common_frags = {41, 43, 55, 57, 69, 71, 73, 77, 79, 81, 83, 85, 91, 93, 95, 97, 105, 107, 119, 121, 133, 135, 147, 149}
        all_mz = set(q_dict.keys()) | set(r_dict.keys())

        dot = 0.0
        q_norm = 0.0
        r_norm_sq = 0.0
        for mz in all_mz:
            qi = q_dict.get(mz, 0.0)
            ri = r_dict.get(mz, 0.0)
            weight = 0.5 if mz in common_frags else 1.0
            dot += qi * ri * weight
            q_norm += qi * qi * weight
            r_norm_sq += ri * ri * weight

        if q_norm == 0 or r_norm_sq == 0:
            return 0

        return int((dot / (q_norm ** 0.5 * r_norm_sq ** 0.5)) * 999)


# ================================================================
# Local HTTP API Server
# ================================================================
class NISTRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for local NIST search API.

    All endpoints are read-only. No data is modified or uploaded.
    """
    db_path = None      # Set by server before starting
    spec_index = None   # SpectrumIndex instance

    def log_message(self, format, *args):
        """Suppress access logs unless verbose."""
        if getattr(self.server, 'verbose', False):
            super().log_message(format, *args)

    def _get_conn(self):
        """Get a fresh SQLite connection (thread-safe)."""
        return sqlite3.connect(str(self.db_path))

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        params = parse_qs(parsed.query)

        if path == '/health':
            self._send_json({'status': 'ok', 'server': 'nist-local-server'})

        elif path == '/stats':
            conn = self._get_conn()
            try:
                total = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
                with_f = conn.execute(
                    "SELECT COUNT(*) FROM compounds WHERE formula IS NOT NULL"
                ).fetchone()[0]
                meta = {}
                for row in conn.execute("SELECT key, value FROM metadata"):
                    meta[row[0]] = row[1]
                self._send_json({
                    'total_entries': total,
                    'with_formula': with_f,
                    'metadata': meta,
                })
            finally:
                conn.close()

        elif path == '/search':
            query = params.get('q', [''])[0].strip()
            search_type = params.get('type', ['all'])[0]
            max_results = int(params.get('max', ['20'])[0])

            if not query:
                self._send_json({'error': 'Missing query parameter ?q='}, 400)
                return

            conn = self._get_conn()
            try:
                results = []
                query_lower = query.lower()

                if search_type in ('name', 'all'):
                    rows = conn.execute(
                        "SELECT name, formula FROM compounds "
                        "WHERE name_lower LIKE ? "
                        "LIMIT ?",
                        (f'%{query_lower}%', max_results * 2)
                    ).fetchall()
                    for name, formula in rows:
                        if not any(r['name'] == name for r in results):
                            results.append({
                                'name': name,
                                'formula': formula,
                                'match_type': 'name',
                            })
                        if len(results) >= max_results:
                            break

                if search_type in ('formula', 'all'):
                    rows = conn.execute(
                        "SELECT name, formula FROM compounds "
                        "WHERE formula LIKE ? "
                        "LIMIT ?",
                        (f'%{query_lower.upper()}%', max_results)
                    ).fetchall()
                    for name, formula in rows:
                        if not any(r['name'] == name for r in results):
                            results.append({
                                'name': name,
                                'formula': formula,
                                'match_type': 'formula',
                            })

                self._send_json({
                    'status': 'ok',
                    'query': query,
                    'search_type': search_type,
                    'n_results': len(results[:max_results]),
                    'results': results[:max_results],
                })
            finally:
                conn.close()

        elif path == '/search-spectrum':
            if not self.spec_index or not self.spec_index.loaded:
                self._send_json({'error': 'Spectrum index not built. Load JCAMP files first.'}, 503)
                return
            try:
                peaks_str = params.get('peaks', [''])[0]
                min_match = int(params.get('min_match', ['600'])[0])
                max_results = int(params.get('max', ['20'])[0])
                # Parse peaks: "43:999,57:850,71:600" format
                peaks = []
                for p in peaks_str.split(','):
                    if ':' in p:
                        mz, i = p.split(':')
                        peaks.append((int(mz), int(i)))
                if not peaks:
                    self._send_json({'error': 'No peaks provided. Use peaks=43:999,57:850 format'}, 400)
                    return
                results = self.spec_index.search_spectrum(peaks, max_results, min_match)
                self._send_json({'status': 'ok', 'n_results': len(results), 'results': results})
            except Exception as e:
                self._send_json({'error': str(e)}, 500)

        else:
            self._send_json({
                'error': 'Unknown endpoint',
                'available': ['/health', '/stats', '/search', '/search-spectrum?peaks=43:999,57:850&min_match=600'],
            }, 404)

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def start_server(db_path, port=8765, verbose=False, jcamp_dir=None):
    """Start local HTTP server.

    Args:
        db_path: path to SQLite database
        port: local port to listen on
        verbose: enable request logging
        jcamp_dir: path to JCAMP export directory (enables spectrum search)
    """
    NISTRequestHandler.db_path = Path(db_path)

    # Load spectrum index if JCAMP dir provided
    if jcamp_dir and Path(jcamp_dir).exists():
        print(f"\n  Loading spectrum index from {jcamp_dir}...")
        spec_idx = SpectrumIndex()
        n = spec_idx.load_jcamp_dir(jcamp_dir)
        NISTRequestHandler.spec_index = spec_idx
        print(f"  Spectrum search: ENABLED ({n:,} spectra)")

    server = HTTPServer(('127.0.0.1', port), NISTRequestHandler)
    server.verbose = verbose

    print(f"\n{'='*60}")
    print(f"  NIST Local Server Running")
    print(f"  {'='*60}")
    print(f"  URL:             http://localhost:{port}")
    print(f"  Health:          http://localhost:{port}/health")
    print(f"  Stats:           http://localhost:{port}/stats")
    print(f"  Name Search:     http://localhost:{port}/search?q=caffeine")
    if NISTRequestHandler.spec_index and NISTRequestHandler.spec_index.loaded:
        print(f"  Spectrum Search: http://localhost:{port}/search-spectrum?peaks=43:999,57:850")
    print(f"  Database: {db_path}")
    print(f"  {'='*60}")
    print(f"  Keep this window open while using gcms_analyzer.")
    print(f"  All NIST data stays on your computer.")
    print(f"  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.shutdown()


# ================================================================
# CLI
# ================================================================
def main():
    parser = argparse.ArgumentParser(
        description='NIST Local Server - Parse & Serve YOUR Licensed NIST Library',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
LEGAL NOTICE:
    This tool reads NIST library files that YOU already own under license.
    It does NOT contain, distribute, or upload any NIST data.
    All processing happens on your local computer.

Examples:
  # Parse and serve your NIST library
  python nist_local_server.py --nist D:\\NIST17\\MSSEARCH\\mainlib

  # Use a different port
  python nist_local_server.py --nist ~/Desktop/NIST17.L --port 9999

  # Parse only (don't start server) — for testing
  python nist_local_server.py --nist ~/Desktop/NIST17.L --parse-only

  # Use an existing database (skip parsing)
  python nist_local_server.py --db ./nist_local.db

Common NIST library locations:
  Agilent/MassHunter:  C:\\Database\\NIST\\mainlib
  NIST 14/17/20:      C:\\NIST17\\MSSEARCH\\mainlib
  Desktop:            ~/Desktop/NIST17.L
        """
    )
    parser.add_argument('--nist', '-n', help='Path to NIST .L library directory')
    parser.add_argument('--db', '-d', default=None,
                        help='Path to SQLite database (default: nist_local.db next to this script)')
    parser.add_argument('--jcamp-dir', '-j', default=None,
                        help='Path to exported JCAMP directory (enables spectrum search)')
    parser.add_argument('--port', '-p', type=int, default=8765, help='Local port (default: 8765)')
    parser.add_argument('--parse-only', action='store_true',
                        help='Only parse library, skip starting server')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Enable request logging')

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    db_path = args.db or script_dir / 'nist_local.db'

    # Phase 1: Parse NIST library
    if args.nist:
        nist_path = Path(args.nist)
        if not nist_path.exists():
            print(f"\n Error: NIST library not found at: {args.nist}")
            print(f"   Please verify the path to your NIST .L directory.")
            sys.exit(1)

        print(f"\n Parsing NIST library: {nist_path}")
        print(f"{'='*60}")

        parser_obj = NISTParser(nist_path)
        entries = parser_obj.parse_entries()

        if not entries:
            print("\n No valid entries found. Check that the path points to a NIST .L directory.")
            sys.exit(1)

        print(f"\n Building database: {db_path}")
        build_database(entries, db_path)

    # Phase 2: Start server
    if not args.parse_only:
        if not Path(db_path).exists():
            print(f"\n No database found at: {db_path}")
            print(f"   Run with --nist first to parse your library, or provide --db with existing database.")
            print(f"   Example: python nist_local_server.py --nist ~/Desktop/NIST17.L")
            sys.exit(1)

        start_server(db_path, args.port, args.verbose, args.jcamp_dir)
    else:
        print(f"\n Parse complete. Database saved to: {db_path}")
        print(f"   To start server: python nist_local_server.py --db {db_path}")


if __name__ == '__main__':
    main()
