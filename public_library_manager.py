#!/usr/bin/env python3
"""
Public GC-MS Spectral Library Manager
======================================
Unified interface to open-source mass spectral libraries.
Combines multiple sources into a single searchable library:
  - Built-in MSP library (~140 flavor/aroma compounds)
  - MassBank Europe (MSP format, downloadable)
  - NIST WebBook EI spectra (CSV, from Zenodo)
  - MoNA (MassBank of North America) — live REST API

Usage:
    from public_library_manager import PublicLibraryManager
    mgr = PublicLibraryManager()
    results = mgr.search_by_spectrum(ions, min_match=700)
    results = mgr.search_by_name("hexanal")
    results = mgr.search_mona_api(ions)  # live MoNA search
    mgr.download_massbank()  # auto-download MassBank EU
    mgr.download_nist_webbook()  # auto-download NIST WebBook
"""

import os
import re
import json
import hashlib
import time
from pathlib import Path
from collections import defaultdict
import numpy as np

# ============================================================
# Configuration
# ============================================================
LIBRARY_DIR = Path(__file__).parent / "public_libraries"
LIBRARY_CACHE = LIBRARY_DIR / ".library_cache.json"
LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

# MoNA REST API base
MONA_API_BASE = "https://mona.fiehnlab.ucdavis.edu/rest"
MONA_API_TIMEOUT = 30

# ============================================================
# MSP Parser (supports NIST-compatible MSP format)
# ============================================================
def parse_msp_file(filepath):
    """Parse an MSP-format spectral library file.

    Handles two MSP format variants:
      Format A (built-in): NAME:/CASNO:/FORMULA:/NUM PEAKS:/mz;int;...
      Format B (MassBank NIST): Name:/Formula:/Num Peaks:/mz int (one per line)

    Returns list of dicts with keys: name, cas, formula, rt_exp, peaks, source
    """
    entries = []
    current = None
    in_peaks = False  # For MassBank NIST format (peak lines have no semicolons)

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            raw = f.read()
    except Exception:
        try:
            with open(filepath, 'r', encoding='latin-1', errors='ignore') as f:
                raw = f.read()
        except Exception:
            return entries

    for line in raw.split('\n'):
        line_stripped = line.strip()
        if not line_stripped:
            if current and 'peaks' in current:
                entries.append(current)
            current = None
            in_peaks = False
            continue

        line_upper = line_stripped.upper()

        # --- Detect start of new entry ---
        if line_upper.startswith('NAME:') or line_stripped.lower().startswith('name:'):
            if current and 'peaks' in current:
                entries.append(current)
            current = {
                'name': line_stripped.split(':', 1)[1].strip().lower(),
                'source': 'msp_file',
                'source_file': str(Path(filepath).name),
                'peaks': [],
            }
            in_peaks = False
            continue

        if current is None:
            continue

        # --- Metadata fields ---
        # CAS number
        if line_upper.startswith('CAS') and ':' in line_stripped:
            current['cas'] = line_stripped.split(':', 1)[1].strip()
            continue

        # Formula
        if line_upper.startswith('FORMULA:') or line_stripped.lower().startswith('formula:'):
            current['formula'] = line_stripped.split(':', 1)[1].strip()
            continue

        # RT
        if line_upper.startswith('RT') and ':' in line_stripped:
            try:
                current['rt_exp'] = float(line_stripped.split(':', 1)[1].strip())
            except ValueError:
                pass
            continue

        # Num Peaks (both formats)
        if 'NUM PEAKS' in line_upper or 'NUM PEAKS' in line_upper.replace(' ', ''):
            try:
                val = line_stripped.split(':', 1)[1].strip()
                current['num_peaks'] = int(val)
                in_peaks = True  # Peak data follows
            except (ValueError, IndexError):
                pass
            continue

        # MassBank NIST: DB# as accession
        if line_upper.startswith('DB#'):
            current['accession'] = line_stripped.split(':', 1)[1].strip()
            continue

        # InChIKey / InChI
        if line_upper.startswith('INCHIKEY:') or line_upper.startswith('INCHI:'):
            current[line_stripped.split(':')[0].lower()] = line_stripped.split(':', 1)[1].strip()
            continue

        # SMILES
        if line_upper.startswith('SMILES:'):
            current['smiles'] = line_stripped.split(':', 1)[1].strip()
            continue

        # Instrument type
        if line_upper.startswith('INSTRUMENT_TYPE:') or line_upper.startswith('INSTRUMENT:'):
            k = 'instrument_type' if 'TYPE' in line_upper else 'instrument'
            current[k] = line_stripped.split(':', 1)[1].strip()
            continue

        # Ion mode
        if line_upper.startswith('ION_MODE:'):
            current['ion_mode'] = line_stripped.split(':', 1)[1].strip()
            continue

        # Collision energy
        if line_upper.startswith('COLLISION_ENERGY:'):
            current['collision_energy'] = line_stripped.split(':', 1)[1].strip()
            continue

        # Spectrum type (MS2, MS1, etc.)
        if line_upper.startswith('SPECTRUM_TYPE:'):
            current['spectrum_type'] = line_stripped.split(':', 1)[1].strip()
            continue

        # Precursor MZ
        if line_upper.startswith('PRECURSORMZ:') or line_upper.startswith('PRECURSOR_MZ:'):
            try:
                current['precursor_mz'] = float(line_stripped.split(':', 1)[1].strip())
            except ValueError:
                pass
            continue

        # MW / ExactMass
        if line_upper.startswith('MW:') or line_upper.startswith('EXACTMASS:'):
            try:
                current['mw'] = float(line_stripped.split(':', 1)[1].strip())
            except ValueError:
                pass
            continue

        # Splash
        if line_upper.startswith('SPLASH:'):
            current['splash'] = line_stripped.split(':', 1)[1].strip()
            continue

        # Synon (synonyms)
        if line_upper.startswith('SYNON:'):
            if 'synonyms' not in current:
                current['synonyms'] = []
            current['synonyms'].append(line_stripped.split(':', 1)[1].strip())
            continue

        # Comments
        if line_upper.startswith('COMMENTS:') or line_upper.startswith('PRECURSOR_TYPE:'):
            continue

        # --- Peak data ---
        # Format A: "mz int; mz int; ..." (semicolon-separated)
        if ';' in line_stripped and current is not None:
            peaks = current.get('peaks', [])
            for pair in line_stripped.split(';'):
                pair = pair.strip()
                if not pair:
                    continue
                parts = pair.split()
                if len(parts) >= 2:
                    try:
                        mz_val = int(float(parts[0]))
                        intensity = int(float(parts[1]))
                        peaks.append((mz_val, intensity))
                    except ValueError:
                        continue
            if peaks:
                current['peaks'] = peaks
            continue

        # Format B: "mz intensity" (one per line, no semicolons)
        # After "Num Peaks:" line, lines with 2 numbers are peak data
        parts = line_stripped.split()
        if len(parts) == 2 and in_peaks:
            try:
                mz_val = float(parts[0])
                intensity = float(parts[1])
                # Reasonable m/z range check
                if 10 < mz_val < 2000 and intensity > 0:
                    peaks = current.get('peaks', [])
                    peaks.append((int(mz_val) if mz_val == int(mz_val) else mz_val, int(intensity)))
                    current['peaks'] = peaks
                else:
                    in_peaks = False  # Out of peak range, stop
            except ValueError:
                in_peaks = False
                continue

    if current and 'peaks' in current and len(current['peaks']) >= 3:
        entries.append(current)

    return entries


def parse_msp_text(msp_text, source_label="inline"):
    """Parse MSP-format text (same as parse_msp_file but from string)."""
    entries = []
    current = None

    for line in msp_text.strip().split('\n'):
        line = line.strip()
        if not line:
            if current and 'peaks' in current:
                entries.append(current)
            current = None
            continue

        if line.upper().startswith('NAME:'):
            if current and 'peaks' in current:
                entries.append(current)
            current = {
                'name': line.split(':', 1)[1].strip().lower(),
                'source': source_label,
                'source_file': 'built-in',
            }
        elif line.upper().startswith('CAS') and current:
            current['cas'] = line.split(':', 1)[1].strip()
        elif line.upper().startswith('FORMULA:') and current:
            current['formula'] = line.split(':', 1)[1].strip()
        elif line.upper().startswith('RT_EXP:') and current:
            try:
                current['rt_exp'] = float(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif line.upper().startswith('NUM PEAKS:') and current:
            try:
                current['num_peaks'] = int(line.split(':', 1)[1].strip())
            except ValueError:
                pass
        elif ';' in line and current:
            peaks = []
            for pair in line.split(';'):
                pair = pair.strip()
                if not pair:
                    continue
                parts = pair.split()
                if len(parts) >= 2:
                    try:
                        mz_val = int(parts[0])
                        intensity = int(parts[1])
                        peaks.append((mz_val, intensity))
                    except ValueError:
                        continue
            if peaks:
                current['peaks'] = peaks

    if current and 'peaks' in current:
        entries.append(current)

    return entries


# ============================================================
# JSON Parser (MoNA / MassBank JSON export)
# ============================================================
def parse_mona_json(filepath):
    """Parse MoNA-exported JSON spectral library.

    MoNA JSON format:
      [{"id": "...", "name": "...", "spectrum": "mz:int mz:int ...", ...}]
    """
    entries = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return entries

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return entries

    for item in data:
        name = item.get('compound', item.get('name', '')).strip().lower()
        if not name:
            continue

        entry = {
            'name': name,
            'cas': item.get('cas', item.get('casNumber', '')),
            'formula': item.get('formula', item.get('molecularFormula', '')),
            'source': 'mona_json',
            'source_file': str(Path(filepath).name),
            'mona_id': item.get('id', ''),
            'inchi': item.get('inchi', ''),
            'inchikey': item.get('inchikey', ''),
            'precursor_mz': item.get('precursorMZ', item.get('precursor', 0)),
            'instrument': item.get('instrument', ''),
            'collision_energy': item.get('collisionEnergy', ''),
            'ion_mode': item.get('ionizationMode', item.get('ionMode', '')),
        }

        # Parse spectrum
        spectrum_str = item.get('spectrum', '')
        if spectrum_str:
            peaks = []
            for pair in spectrum_str.strip().split():
                parts = pair.split(':')
                if len(parts) == 2:
                    try:
                        mz_val = float(parts[0])
                        intensity = float(parts[1])
                        peaks.append((int(mz_val) if mz_val == int(mz_val) else mz_val,
                                      int(intensity)))
                    except ValueError:
                        continue
            if peaks:
                entry['peaks'] = peaks

        if 'peaks' in entry:
            entries.append(entry)

    return entries


# ============================================================
# NIST WebBook CSV parser (from Zenodo record)
# ============================================================
def parse_nist_webbook_csv(filepath):
    """Parse NIST WebBook CSV export (from Zenodo).

    Expected format: name,cas,formula,mw,rt,n_peaks,mz1 int1 mz2 int2 ...
    or similar variations.
    """
    entries = []
    try:
        import pandas as pd
        df = pd.read_csv(filepath, encoding='utf-8', on_bad_lines='skip')
    except Exception:
        try:
            import pandas as pd
            df = pd.read_csv(filepath, encoding='latin-1', on_bad_lines='skip')
        except Exception:
            return entries

    # Auto-detect columns
    cols = [c.lower().strip() for c in df.columns]

    name_col = area_col = cas_col = formula_col = spectrum_col = None
    for i, c in enumerate(cols):
        if c in ('name', 'compound', 'compound name', 'compound_name'):
            name_col = df.columns[i]
        elif c in ('cas', 'cas#', 'cas number', 'cas_number'):
            cas_col = df.columns[i]
        elif c in ('formula', 'molecular formula', 'mol formula'):
            formula_col = df.columns[i]
        elif 'spectrum' in c or 'peaks' in c or 'ions' in c:
            spectrum_col = df.columns[i]

    if name_col is None:
        return entries

    for _, row in df.iterrows():
        name = str(row[name_col]).strip().lower()
        if not name or name == 'nan':
            continue

        entry = {
            'name': name,
            'cas': str(row[cas_col]).strip() if cas_col and pd.notna(row[cas_col]) else '',
            'formula': str(row[formula_col]).strip() if formula_col and pd.notna(row[formula_col]) else '',
            'source': 'nist_webbook_csv',
            'source_file': str(Path(filepath).name),
        }

        # Try to parse spectrum from spectrum column
        if spectrum_col and pd.notna(row[spectrum_col]):
            spec_str = str(row[spectrum_col])
            peaks = []
            # Try "mz:int mz:int ..." format
            for pair in spec_str.split():
                parts = pair.replace(':', ' ').split()
                if len(parts) >= 2:
                    try:
                        mz_val = int(float(parts[0]))
                        intensity = int(float(parts[1]))
                        peaks.append((mz_val, intensity))
                    except ValueError:
                        continue
            if peaks:
                entry['peaks'] = peaks

        # Try to find m/z and intensity columns (mz1, int1, mz2, int2, ...)
        if 'peaks' not in entry:
            peaks = []
            for i in range(1, 51):  # Up to 50 ion pairs
                mz_col = f'mz{i}'
                int_col = f'int{i}'
                # Try various naming patterns
                for mc, ic in [(f'mz{i}', f'int{i}'),
                               (f'm/z{i}', f'intensity{i}'),
                               (f'peak{i}_mz', f'peak{i}_int')]:
                    if mc in cols and ic in cols:
                        mz_val = row[df.columns[cols.index(mc)]]
                        int_val = row[df.columns[cols.index(ic)]]
                        if pd.notna(mz_val) and pd.notna(int_val):
                            try:
                                peaks.append((int(float(mz_val)), int(float(int_val))))
                            except ValueError:
                                continue
            if peaks:
                entry['peaks'] = peaks

        if 'peaks' in entry and len(entry['peaks']) >= 3:
            entries.append(entry)

    return entries


# ============================================================
# Cosine Similarity Engine
# ============================================================
def cosine_similarity_weighted(observed_ions, reference_ions, tolerance=0.5):
    """Compute weighted cosine similarity between two mass spectra.

    Uses intensity-weighted matching — high-intensity ions contribute more.

    Returns match factor 0-999 (NIST-style).
    """
    if not observed_ions or not reference_ions:
        return 0

    obs_mz = np.array([o[0] for o in observed_ions], dtype=float)
    obs_int = np.array([o[1] for o in observed_ions], dtype=float)

    total_ref_sq = sum(r[1]**2 for r in reference_ions)
    total_obs_sq = sum(obs_int**2)

    if total_ref_sq == 0 or total_obs_sq == 0:
        return 0

    # Weighted intensity matching
    weighted_sum = 0.0
    for ref_mz, ref_int in reference_ions:
        diffs = np.abs(obs_mz - ref_mz)
        best_idx = int(np.argmin(diffs))
        if diffs[best_idx] <= tolerance:
            weighted_sum += ref_int * obs_int[best_idx]

    cosine = weighted_sum / np.sqrt(total_ref_sq * total_obs_sq)
    match_factor = int(cosine * 999)
    return min(999, max(0, match_factor))


def cosine_similarity_forward(observed_ions, reference_ions, tolerance=0.5):
    """Forward search: how well reference ions are represented in observed.

    This is the NIST "Match Factor" — all reference ions must be found in observed.
    """
    return cosine_similarity_weighted(observed_ions, reference_ions, tolerance)


def cosine_similarity_reverse(observed_ions, reference_ions, tolerance=0.5):
    """Reverse search: how well observed ions are represented in reference.

    This is the NIST "Reverse Match Factor" — ignores extra ions in observed
    (e.g., co-eluting peaks, background).
    """
    return cosine_similarity_weighted(reference_ions, observed_ions, tolerance)


# ============================================================
# PublicLibraryManager
# ============================================================
class PublicLibraryManager:
    """Unified manager for all public-domain mass spectral libraries.

    Combines:
      - Built-in MSP library (~140 flavor/aroma compounds)
      - MassBank Europe (MSP, downloadable)
      - NIST WebBook EI spectra (CSV, from Zenodo)
      - MoNA (live REST API)

    Usage:
        mgr = PublicLibraryManager()
        mgr.load_all()
        results = mgr.search_by_spectrum(ions)
        results = mgr.search_by_name("hexanal")
    """

    def __init__(self, cache_dir=None):
        self.cache_dir = Path(cache_dir) if cache_dir else LIBRARY_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / ".library_cache.json"

        self.entries = []          # All library entries
        self.cas_index = {}        # CAS number → entry index
        self.name_index = defaultdict(list)  # Name → entry indices
        self.base_peak_index = defaultdict(list)  # base peak m/z → entry indices
        self.stats = {
            'total_entries': 0,
            'sources': defaultdict(int),
            'loaded_at': '',
        }

    def load_builtin(self):
        """Load the built-in MSP spectral library."""
        from spectral_library import MSP_LIBRARY, load_library as load_builtin

        builtin_entries = load_builtin()
        for entry in builtin_entries:
            entry['source'] = 'builtin_msp'
            entry['source_file'] = 'spectral_library.py'
        self._add_entries(builtin_entries, 'builtin_msp')
        return len(builtin_entries)

    def load_msp_file(self, filepath):
        """Load an MSP-format library file."""
        entries = parse_msp_file(filepath)
        for entry in entries:
            entry['source'] = 'msp_file'
            entry['source_file'] = str(Path(filepath).name)
        self._add_entries(entries, 'msp_file')
        return len(entries)

    def load_mona_json(self, filepath):
        """Load a MoNA JSON export file."""
        entries = parse_mona_json(filepath)
        self._add_entries(entries, 'mona_json')
        return len(entries)

    def load_nist_csv(self, filepath):
        """Load a NIST WebBook CSV file."""
        entries = parse_nist_webbook_csv(filepath)
        self._add_entries(entries, 'nist_webbook_csv')
        return len(entries)

    def load_downloaded_libraries(self):
        """Scan public_libraries/ directory and load all found libraries."""
        total = 0
        if not self.cache_dir.exists():
            return total

        for f in sorted(self.cache_dir.glob("*")):
            if f.name.startswith('.'):
                continue
            suffix = f.suffix.lower()
            try:
                if suffix == '.msp':
                    n = self.load_msp_file(f)
                    print(f"  Loaded MSP: {f.name} ({n} entries)")
                    total += n
                elif suffix == '.json':
                    n = self.load_mona_json(f)
                    print(f"  Loaded JSON: {f.name} ({n} entries)")
                    total += n
                elif suffix == '.csv':
                    n = self.load_nist_csv(f)
                    print(f"  Loaded CSV: {f.name} ({n} entries)")
                    total += n
            except Exception as e:
                print(f"  [WARN] Failed to load {f.name}: {e}")

        return total

    def load_all(self, include_downloaded=True):
        """Load all available libraries."""
        self.entries = []
        self.cas_index = {}
        self.name_index = defaultdict(list)
        self.base_peak_index = defaultdict(list)

        n_builtin = self.load_builtin()
        print(f"  Loaded built-in: {n_builtin} entries")

        if include_downloaded:
            n_downloaded = self.load_downloaded_libraries()
            if n_downloaded:
                print(f"  Loaded downloaded: {n_downloaded} entries")

        self.stats['total_entries'] = len(self.entries)
        self.stats['loaded_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"  Total library: {self.stats['total_entries']} entries")
        print(f"  Sources: {dict(self.stats['sources'])}")

        return self.stats['total_entries']

    def _add_entries(self, new_entries, source_label):
        """Add entries with deduplication by CAS number."""
        added = 0
        for entry in new_entries:
            if 'peaks' not in entry or not entry['peaks']:
                continue
            if len(entry['peaks']) < 3:
                continue

            cas = entry.get('cas', '')
            name = entry.get('name', '')

            # Deduplicate by CAS number
            if cas and cas in self.cas_index:
                existing_idx = self.cas_index[cas]
                existing = self.entries[existing_idx]
                # Keep the entry with more peaks or from preferred source
                source_priority = {'builtin_msp': 3, 'mona_json': 2, 'msp_file': 2,
                                  'nist_webbook_csv': 1}
                existing_priority = source_priority.get(existing.get('source', ''), 0)
                new_priority = source_priority.get(source_label, 0)

                if new_priority > existing_priority:
                    self.entries[existing_idx] = entry
                elif new_priority == existing_priority and len(entry['peaks']) > len(existing['peaks']):
                    self.entries[existing_idx] = entry
                continue

            # Deduplicate by exact name match
            if name:
                found_dup = False
                for idx in self.name_index.get(name, []):
                    existing = self.entries[idx]
                    if existing.get('cas') == cas:
                        found_dup = True
                        break
                if found_dup:
                    continue

            idx = len(self.entries)
            self.entries.append(entry)
            if cas:
                self.cas_index[cas] = idx
            if name:
                self.name_index[name].append(idx)

            # Index by base peak m/z for fast spectral search pre-filtering
            peaks = entry['peaks']
            base_peak_mz = int(max(peaks, key=lambda p: p[1])[0])
            self.base_peak_index[base_peak_mz].append(idx)

            self.stats['sources'][source_label] += 1
            added += 1

        return added

    def search_by_spectrum(self, observed_ions, min_match=600, max_results=20,
                          include_sources=None, require_both=True):
        """Search all libraries by spectral similarity (cosine).

        Uses NIST-style combined scoring: both forward AND reverse matches must
        be decent for a reliable identification. This eliminates false positives
        from LC-MS/MS spectra when searching EI-MS data and vice versa.

        Args:
            observed_ions: list of (mz, intensity) tuples
            min_match: minimum match factor 0-999 (applied to combined score)
            max_results: max hits to return
            include_sources: optional list of source labels to restrict search
            require_both: if True, uses min(forward, reverse) as score (NIST-like).
                         if False, uses max(forward, reverse) (lenient).

        Returns:
            list of dicts with match results, sorted by match_factor desc
        """
        # --- Fast pre-filter: only check entries whose base peak matches ---
        # Find observed base peak and top-5 ions
        sorted_obs = sorted(observed_ions, key=lambda x: x[1], reverse=True)
        top_5_mz = set(int(x[0]) for x in sorted_obs[:5])

        # Collect candidate entry indices via base peak index
        candidate_indices = set()
        for mz in top_5_mz:
            if mz in self.base_peak_index:
                candidate_indices.update(self.base_peak_index[mz])
            # Also check +/- 1 Da (isotope/nominal mass variation)
            for delta in (-1, 1):
                if (mz + delta) in self.base_peak_index:
                    candidate_indices.update(self.base_peak_index[mz + delta])

        # If no candidates via base peak, fall back to all entries (rare)
        if not candidate_indices:
            candidate_indices = range(len(self.entries))

        results = []
        for idx in candidate_indices:
            entry = self.entries[idx]
            if include_sources and entry.get('source') not in include_sources:
                continue

            mf_forward = cosine_similarity_forward(observed_ions, entry['peaks'])
            mf_reverse = cosine_similarity_reverse(observed_ions, entry['peaks'])

            # NIST-style combined score: require both directions
            if require_both:
                combined_mf = int((mf_forward + mf_reverse) / 2)
                # Additional penalty if one direction is very low
                if mf_forward < 400 or mf_reverse < 400:
                    combined_mf = min(combined_mf, 500)
            else:
                combined_mf = max(mf_forward, mf_reverse)

            if combined_mf >= min_match:
                results.append({
                    'name': entry['name'],
                    'cas': entry.get('cas', ''),
                    'formula': entry.get('formula', ''),
                    'match_factor': combined_mf,
                    'match_forward': mf_forward,
                    'match_reverse': mf_reverse,
                    'source': entry.get('source', 'unknown'),
                    'source_file': entry.get('source_file', ''),
                    'n_ref_peaks': len(entry['peaks']),
                })

        results.sort(key=lambda x: x['match_factor'], reverse=True)
        return results[:max_results]

    def search_by_name(self, name, max_results=20):
        """Search library by compound name (fuzzy match).

        Args:
            name: compound name or substring
            max_results: max hits

        Returns:
            list of matching entries
        """
        name_lower = name.lower().strip()
        results = []

        for entry in self.entries:
            if name_lower in entry['name']:
                results.append({
                    'name': entry['name'],
                    'cas': entry.get('cas', ''),
                    'formula': entry.get('formula', ''),
                    'source': entry.get('source', 'unknown'),
                    'n_peaks': len(entry.get('peaks', [])),
                })

        # Also check name_index for exact matches
        exact_indices = set()
        if name_lower in self.name_index:
            exact_indices = set(self.name_index[name_lower])

        # Rank: exact matches first, then fuzzy
        results.sort(key=lambda x: (0 if x['name'] == name_lower else 1,
                                     -x['n_peaks']))
        return results[:max_results]

    def search_by_cas(self, cas_number):
        """Search library by CAS number."""
        cas = cas_number.strip()
        if cas in self.cas_index:
            entry = self.entries[self.cas_index[cas]]
            return {
                'name': entry['name'],
                'cas': entry.get('cas', ''),
                'formula': entry.get('formula', ''),
                'source': entry.get('source', 'unknown'),
                'n_peaks': len(entry.get('peaks', [])),
                'peaks': entry.get('peaks', []),
            }
        return None

    def search_mona_api(self, observed_ions=None, compound_name=None,
                       precursor_mz=None, min_match=600, max_results=10):
        """Search MoNA (MassBank of North America) via REST API.

        Args:
            observed_ions: list of (mz, intensity) tuples for spectral search
            compound_name: search by compound name
            precursor_mz: search by precursor m/z
            min_match: minimum match factor for spectral search
            max_results: max hits

        Returns:
            list of dicts with match results
        """
        import requests

        results = []

        try:
            if observed_ions and len(observed_ions) >= 3:
                # Build spectrum query string: "mz:int mz:int ..."
                spectrum_str = ' '.join(f"{mz}:{intensity}"
                                       for mz, intensity in observed_ions[:50])

                resp = requests.get(
                    f"{MONA_API_BASE}/spectra/search",
                    params={
                        'spectrum': spectrum_str,
                        'minSimilarity': min_match,
                        'size': max_results,
                    },
                    timeout=MONA_API_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for hit in data if isinstance(data, list) else data.get('content', []):
                        results.append({
                            'name': (hit.get('compound', {}).get('name', '')
                                    if isinstance(hit.get('compound'), dict)
                                    else hit.get('compoundName', hit.get('name', ''))).lower(),
                            'cas': hit.get('cas', ''),
                            'formula': hit.get('molecularFormula', hit.get('formula', '')),
                            'match_factor': hit.get('similarity', hit.get('score', 0)),
                            'source': 'mona_api',
                            'mona_id': hit.get('id', ''),
                            'mona_url': f"https://mona.fiehnlab.ucdavis.edu/spectra/browse/{hit.get('id', '')}",
                            'instrument': hit.get('instrument', ''),
                            'collision_energy': hit.get('collisionEnergy', ''),
                        })

            elif compound_name:
                resp = requests.get(
                    f"{MONA_API_BASE}/spectra/search",
                    params={'query': compound_name, 'size': max_results},
                    timeout=MONA_API_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    hits = data if isinstance(data, list) else data.get('content', [])
                    for hit in hits:
                        results.append({
                            'name': (hit.get('compound', {}).get('name', '')
                                    if isinstance(hit.get('compound'), dict)
                                    else hit.get('compoundName', '')).lower(),
                            'cas': hit.get('cas', ''),
                            'formula': hit.get('molecularFormula', ''),
                            'source': 'mona_api',
                            'mona_id': hit.get('id', ''),
                            'n_spectra': hit.get('numberOfSpectra', 1),
                        })

        except requests.exceptions.RequestException as e:
            # MoNA API unavailable — return empty results gracefully
            pass
        except Exception:
            pass

        return results

    def identify_compound(self, observed_ions, min_match=600,
                         include_mona=True, include_local=True):
        """Full identification pipeline: search local libraries + MoNA API.

        Args:
            observed_ions: list of (mz, intensity) tuples
            min_match: minimum match factor
            include_mona: query MoNA live API
            include_local: search local downloaded libraries

        Returns:
            dict with best matches from each source, and a combined top hit
        """
        result = {
            'top_hit': None,
            'all_matches': [],
            'sources_searched': [],
        }

        if include_local:
            local_matches = self.search_by_spectrum(observed_ions, min_match=min_match)
            result['local_matches'] = local_matches
            result['all_matches'].extend(local_matches)
            result['sources_searched'].append('local_libraries')

        if include_mona:
            mona_matches = self.search_mona_api(observed_ions, min_match=min_match)
            result['mona_matches'] = mona_matches
            result['all_matches'].extend(mona_matches)
            result['sources_searched'].append('mona_api')

        # Combine and rank
        result['all_matches'].sort(
            key=lambda x: x.get('match_factor', 0) if 'match_factor' in x else x.get('n_spectra', 1) * 100,
            reverse=True
        )

        if result['all_matches']:
            result['top_hit'] = result['all_matches'][0]

        return result

    def get_library_summary(self):
        """Get a summary of all loaded libraries."""
        compounds_by_source = defaultdict(list)
        for entry in self.entries:
            compounds_by_source[entry.get('source', 'unknown')].append(entry['name'])

        summary = {
            'total_entries': len(self.entries),
            'total_unique_cas': len(self.cas_index),
            'sources': dict(self.stats['sources']),
            'compound_count_by_source': {
                src: len(compounds) for src, compounds in compounds_by_source.items()
            },
            'loaded_at': self.stats['loaded_at'],
            'top_categories': self._categorize_compounds(),
        }
        return summary

    def _categorize_compounds(self):
        """Auto-categorize library compounds across 24+ major chemical categories."""
        cats = defaultdict(int)
        # (category, [keywords]) — checked in priority order
        patterns = [
            ('ester', ['ester', 'lactone', 'acetate', 'butyrate', 'hexanoate',
                      'octanoate', 'decanoate', 'laurate', 'palmitate', 'stearate',
                      'oleate', 'linoleate', 'benzoate', 'salicylate', 'phthalate',
                      'adipate', 'citrate', 'succinate', 'carbonate', 'glyceride']),
            ('solvent/VOC', ['solvent', 'methanol', 'ethanol', 'acetone', 'acetonitrile',
                      'chloroform', 'dichloromethane', 'trichloroethylene', 'benzene',
                      'toluene', 'xylene', 'ethylbenzene', 'hexane', 'heptane', 'cyclohexane',
                      'styrene', 'formaldehyde', 'acetaldehyde', 'butadiene', 'butane',
                      'propane', 'pentane', 'octane', 'decane', 'dodecane', 'tetradecane',
                      'hexadecane', 'octadecane', 'butanol', 'pentanol', 'propanol',
                      'isopropanol', 'ethyl acetate', 'butyl acetate', 'methyl ethyl ketone']),
            ('ketone', ['ketone', 'dione', 'quinone', 'heptanone', 'octanone', 'nonanone',
                      'undecanone', 'acetophenone', 'benzophenone', 'ionone', 'carvone',
                      'menthone', 'camphor', 'acetoin', 'cyclohexanone', 'pentanone',
                      'hexanone', 'butanone', 'decanone', 'nootkatone', 'sotolon']),
            ('pyrazine/pyrrole', ['pyrazine', 'pyrrole', 'imidazole', 'pyridine',
                      'indole', 'skatole']),
            ('alcohol', ['alcohol', 'linalool', 'geraniol', 'nerol', 'citronellol',
                      'menthol', 'borneol', 'farnesol', 'terpineol', 'hexanol',
                      'octanol', 'decanol', 'dodecanol', 'phenylethyl', 'butanol',
                      'pentanol', 'propanol', 'glycerol', 'sorbitol', 'mannitol',
                      'xylitol', 'erythritol']),
            ('aldehyde', ['aldehyde', 'hexanal', 'heptanal', 'octanal', 'nonanal',
                      'decanal', 'furfural', 'benzaldehyde', 'cinnamaldehyde',
                      'acrolein', 'glyoxal', 'crotonaldehyde', 'citral', 'citronellal']),
            ('phenol/polyphenol', ['phenol', 'guaiacol', 'eugenol', 'vanillin', 'cresol',
                      'thymol', 'carvacrol', 'resveratrol', 'quercetin', 'flavonoid',
                      'isoflavone', 'anthocyanin', 'catechin', 'tannin']),
            ('PAH', ['naphthalene', 'anthracene', 'phenanthrene', 'pyrene',
                      'fluoranthene', 'chrysene', 'benzo[a]pyrene', 'benzo[', 'perylene',
                      'acenaphthylene', 'acenaphthene', 'fluorene', 'coronene',
                      'triphenylene', 'indeno', 'retene', 'dibenz[a']),
            ('amino acid/derivative', ['alanine', 'arginine', 'asparagine', 'aspartate',
                      'aspartic', 'cysteine', 'cystine', 'glutamate', 'glutamic', 'glutamine',
                      'glycine', 'histidine', 'isoleucine', 'leucine', 'lysine', 'methionine',
                      'phenylalanine', 'proline', 'serine', 'threonine', 'tryptophan',
                      'tyrosine', 'valine', 'ornithine', 'citrulline', 'taurine', 'carnitine',
                      'carnosine', 'creatine', 'creatinine', 'sarcosine', 'betaine',
                      'homocysteine', 'kynurenine', 'glutathione']),
            ('sugar/carbohydrate', ['glucose', 'fructose', 'galactose', 'mannose', 'xylose',
                      'arabinose', 'ribose', 'sucrose', 'lactose', 'maltose', 'cellobiose',
                      'trehalose', 'raffinose', 'glucoside', 'glycoside', 'saccharide',
                      'glucosamine', 'galactosamine', 'glucuronic', 'inositol', 'sugar']),
            ('drug/pharmaceutical', ['morphine', 'codeine', 'diazepam', 'ibuprofen',
                      'acetaminophen', 'paracetamol', 'aspirin', 'warfarin', 'metformin',
                      'omeprazole', 'atorvastatin', 'simvastatin', 'fluoxetine', 'sertraline',
                      'citalopram', 'venlafaxine', 'amlodipine', 'lisinopril', 'enalapril',
                      'losartan', 'valsartan', 'metoprolol', 'propranolol', 'salbutamol',
                      'prednisone', 'prednisolone', 'dexamethasone', 'furosemide',
                      'hydrochlorothiazide', 'clopidogrel', 'alprazolam', 'zolpidem',
                      'lorazepam', 'anesthetic', 'antibiotic', 'antifungal', 'antiviral',
                      'antidepress', 'antipsychotic', 'anticonvulsant', 'antihistamine',
                      'pharmaceutical', 'analgesic', 'nsaid', 'opioid', 'statin',
                      'beta blocker', 'calcium channel', 'ace inhibitor', 'sedative']),
            ('steroid/hormone', ['steroid', 'sterol', 'stanol', 'cholesterol', 'stigmasterol',
                      'sitosterol', 'campesterol', 'ergosterol', 'testosterone', 'estradiol',
                      'estrone', 'estriol', 'progesterone', 'pregnenolone', 'cortisol',
                      'cortisone', 'corticosterone', 'aldosterone', 'androst', 'hormone',
                      'cholic acid', 'deoxycholic', 'lithocholic', 'ursodeoxycholic',
                      'glycocholic', 'taurocholic', 'chenodeoxycholic', 'dhea']),
            ('vitamin/cofactor', ['vitamin', 'retinol', 'retinal', 'retinoic', 'thiamine',
                      'riboflavin', 'niacin', 'nicotinamide', 'pantothenic', 'pyridoxine',
                      'pyridoxal', 'biotin', 'folate', 'folic acid', 'cobalamin',
                      'ascorbic', 'tocopherol', 'tocotrienol', 'phylloquinone', 'menaquinone',
                      'cholecalciferol', 'ergocalciferol', 'ubiquinone', 'coenzyme',
                      'cofactor', 'nad', 'nadp', 'fad', 'carnitine', 'lipoic']),
            ('lipid/fatty acid', ['lipid', 'fatty acid', 'glyceride', 'phospholipid',
                      'sphingolipid', 'ceramide', 'ganglioside', 'prostaglandin',
                      'leukotriene', 'thromboxane', 'lipoxin', 'lauric', 'myristic',
                      'palmitic', 'stearic', 'oleic', 'linoleic', 'linolenic',
                      'arachidonic', 'eicosapentaenoic', 'docosahexaenoic',
                      'phosphatidylcholine', 'phosphatidylethanolamine', 'sphingomyelin',
                      'sphingosine', 'monoglyceride', 'diglyceride', 'triglyceride']),
            ('alkaloid', ['alkaloid', 'caffeine', 'theobromine', 'theophylline', 'nicotine',
                      'cotinine', 'cocaine', 'atropine', 'scopolamine', 'quinine',
                      'quinidine', 'strychnine', 'brucine', 'ergotamine', 'ephedrine',
                      'pseudoephedrine', 'berberine', 'piperine', 'capsaicin', 'colchicine',
                      'vinblastine', 'vincristine', 'paclitaxel', 'taxol', 'morphine',
                      'codeine', 'thebaine', 'papaverine', 'lysergic']),
            ('terpene/terpenoid', ['terpene', 'terpenoid', 'pinene', 'limonene', 'myrcene',
                      'cymene', 'caryophyllene', 'humulene', 'valencene', 'farnesene',
                      'copaene', 'bisabolene', 'sabinene', 'carene', 'phellandrene',
                      'cadinene', 'selinene', 'bisabolol', 'santalol', 'cedrol',
                      'monoterpene', 'sesquiterpene', 'diterpene', 'triterpene']),
            ('organometallic/silicon', ['siloxane', 'silane', 'silyl', 'organotin',
                      'organomercury', 'organolead', 'ferrocene', 'metallocene',
                      'trimethylsilyl', 'tbdms', 'boronic', 'diphenylsilane',
                      'triisopropylsilane', 'organosilicon', 'organoboron',
                      'organophosphorus', 'tributyltin', 'triphenyltin']),
            ('PCB/organohalogen', ['polychlorinated', 'pcb', 'organochlorine', 'organobromine',
                      'organofluorine', 'perfluor', 'polyfluor', 'pfas', 'pfoa', 'pfos',
                      'chlorobenzene', 'hexachlorobenzene', 'hexachlorocyclohexane',
                      'hexabromocyclododecane', 'polybrominated', 'pbde', 'tetrabromobisphenol',
                      'lindane', 'ddt', 'dde', 'ddd', 'aldrin', 'dieldrin', 'endrin',
                      'heptachlor', 'chlordane', 'mirex', 'toxaphene']),
            ('pesticide/agrochemical', ['pesticide', 'insecticide', 'herbicide', 'fungicide',
                      'atrazine', 'simazine', 'glyphosate', 'paraquat', 'malathion',
                      'parathion', 'chlorpyrifos', 'diazinon', 'carbaryl', 'carbofuran',
                      'permethrin', 'cypermethrin', 'deltamethrin', 'imidacloprid',
                      'fipronil', 'thiamethoxam', 'clothianidin', 'triadimefon',
                      'tebuconazole', 'propiconazole', 'azoxystrobin', 'pyraclostrobin',
                      'boscalid', 'metalaxyl', 'chlorothalonil', 'mancozeb', 'thiram',
                      'captan', '2,4-d', 'rodenticide', 'nematicide', 'acaricide']),
            ('plasticizer/additive', ['plasticizer', 'phthalate', 'adipate', 'sebacate',
                      'phosphate ester', 'bisphenol', 'paraben', 'benzophenone',
                      'benzotriazole', 'dehp', 'dinp', 'didp', 'deha', 'dehs',
                      'diisononyl', 'diisodecyl', 'diethylhexyl', 'dioctyl',
                      'sulfonate', 'uv absorber', 'antioxidant phenolic']),
            ('mycotoxin', ['mycotoxin', 'aflatoxin', 'ochratoxin', 'trichothecene',
                      'fumonisin', 'zearalenone', 'patulin', 'citrinin',
                      'deoxynivalenol', 'nivalenol', 't-2 toxin', 'sterigmatocystin',
                      'cyclopiazonic acid', 'penitrem', 'roquefortine', 'gliotoxin']),
            ('natural product', ['curcumin', 'resveratrol', 'gingerol', 'shogaol',
                      'sulforaphane', 'glucosinolate', 'allicin', 'saponin', 'glycyrrhizin',
                      'stevioside', 'artemisinin', 'ginkgolide', 'silymarin', 'silibinin',
                      'hypericin', 'hyperforin', 'withaferin', 'withanolide', 'parthenolide',
                      'andrographolide', 'triptolide', 'celastrol', 'forskolin',
                      'essential oil', 'natural product', 'secondary metabolite',
                      'phytoalexin', 'phytoestrogen']),
            ('environmental contaminant', ['dioxin', 'nonylphenol', 'octylphenol',
                      'triclosan', 'triclocarban', 'bisphenol a', 'microplastic',
                      'dibenzofuran', 'polychlorinated biphenyl', 'polycyclic aromatic',
                      'chlorinated paraffin', 'brominated flame retardant']),
            ('gas/small molecule', ['methane', 'ethane', 'propane', 'ethylene', 'propylene',
                      'acetylene', 'ammonia', 'hydrogen sulfide', 'sulfur dioxide',
                      'nitric oxide', 'nitrous oxide', 'carbon dioxide', 'carbon monoxide',
                      'nitrogen', 'oxygen', 'ozone', 'argon', 'helium', 'hydrogen',
                      'butane', 'pentane']),
            ('sulfur compound', ['sulfide', 'disulfide', 'trisulfide', 'thiol', 'thiophene',
                      'thiazole', 'methional', 'dimethyl sulfide', 'dimethyl disulfide',
                      'dimethyl trisulfide', 'benzothiazole', 'furfurylthiol',
                      'diallyl disulfide', 'diallyl trisulfide', 'sulfone', 'sulfoxide',
                      'isothiocyanate', 'sulforaphane', 'mercaptan', 'thioether']),
        ]

        for entry in self.entries:
            name = entry['name'].lower()
            matched = False
            for cat, keywords in patterns:
                if any(kw in name for kw in keywords):
                    cats[cat] += 1
                    matched = True
                    break
            if not matched:
                cats['other/niche'] += 1

        return dict(cats)

    # ================================================================
    # Auto-download public libraries (no registration required)
    # ================================================================

    def download_massbank_eu(self):
        """Download MassBank Europe EI-MS MSP library from GitHub releases.

        Tries multiple approaches for users behind network restrictions (e.g. China):
          1. Direct GitHub API + download
          2. Alternative: suggest manual download URL

        Returns path to downloaded file or None.
        """
        import requests

        print("=" * 60)
        print("Downloading MassBank Europe spectral library...")
        print("=" * 60)

        # Check if any MSP file already exists
        existing = list(self.cache_dir.glob("*.msp"))
        if existing:
            print(f"  MSP files already present ({len(existing)} files), skipping download")
            return existing[0]

        # Try direct download with shorter timeouts and retries
        api_urls = [
            "https://api.github.com/repos/MassBank/MassBank-data/releases/latest",
            "https://api.github.com/repos/MassBank/MassBank-data/releases",
        ]

        for api_url in api_urls:
            try:
                resp = requests.get(api_url, timeout=15)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                releases = [data] if isinstance(data, dict) else data
                if isinstance(releases, list):
                    releases = releases[:1]  # Try only latest

                for release in releases:
                    tag = release.get('tag_name', 'unknown')
                    print(f"  Release: {tag}")

                    # Find MSP asset
                    msp_asset = None
                    for asset in release.get('assets', []):
                        name = asset['name'].lower()
                        if 'msp' in name:
                            msp_asset = asset
                            if 'ei' in name or 'gc' in name:
                                break  # Prefer EI-MS/GC-MS

                    if not msp_asset:
                        continue

                    download_url = msp_asset['browser_download_url']
                    size_mb = msp_asset['size'] / (1024 * 1024)
                    print(f"  Downloading: {msp_asset['name']} ({size_mb:.1f} MB)")

                    # Use stream with timeout
                    try:
                        dl_resp = requests.get(download_url, timeout=60, stream=True)
                        if dl_resp.status_code == 200:
                            out_path = self.cache_dir / msp_asset['name']
                            with open(out_path, 'wb') as f:
                                for chunk in dl_resp.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            actual_mb = out_path.stat().st_size / (1024 * 1024)
                            print(f"  Saved: {out_path.name} ({actual_mb:.1f} MB)")
                            return out_path
                    except requests.exceptions.Timeout:
                        print(f"  Timeout (file may be too large)")
                        continue
                    except requests.exceptions.ConnectionError as e:
                        print(f"  Connection error: {e}")
                        continue

            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.ConnectionError:
                continue
            except Exception as e:
                print(f"  Error: {e}")
                continue

        # All attempts failed — show manual download instructions
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Auto-download failed (network restriction?)    ║")
        print("  ║  Manual download options:                       ║")
        print("  ║                                                  ║")
        print("  ║  1. Browser download MassBank MSP:              ║")
        print("  ║     https://massbank.eu/MassBank/                ║")
        print("  ║     → Download → MSP format                     ║")
        print("  ║                                                  ║")
        print("  ║  2. Place downloaded .msp file in:              ║")
        print(f"  ║     {self.cache_dir}║")
        print("  ║                                                  ║")
        print("  ║  3. Re-run: agent auto-loads .msp files         ║")
        print("  ║                                                  ║")
        print("  ║  MoNA live API (no download needed):            ║")
        print("  ║  The agent will use MoNA API for online search  ║")
        print("  ╚══════════════════════════════════════════════════╝")
        return None

    def download_nist_webbook(self):
        """Download NIST WebBook GC-MS reference library from Zenodo.

        Zenodo may be blocked/throttled in some regions. Uses short timeouts
        and provides manual download instructions on failure.

        Returns path to downloaded file or None.
        """
        import requests

        print("\n" + "=" * 60)
        print("Downloading NIST WebBook GC-MS reference library...")
        print("=" * 60)

        # Check if already downloaded
        existing = list(self.cache_dir.glob("*nist*")) + list(self.cache_dir.glob("*webbook*"))
        existing += list(self.cache_dir.glob("*NIST*")) + list(self.cache_dir.glob("*WebBook*"))
        if existing:
            print(f"  NIST WebBook files already present, skipping download")
            return existing[0]

        # Zenodo records with NIST WebBook data
        zenodo_records = [
            "https://zenodo.org/api/records/12786324",
            "https://zenodo.org/api/records/14944348",
        ]

        for zenodo_url in zenodo_records:
            try:
                print(f"  Trying: {zenodo_url.split('/')[-1]}...")
                resp = requests.get(zenodo_url, timeout=10)
                if resp.status_code != 200:
                    print(f"  HTTP {resp.status_code}")
                    continue

                record = resp.json()
                files = record.get('files', [])
                print(f"  Found {len(files)} files")

                for f in files:
                    name = f.get('key', '')
                    if not any(kw in name.lower() for kw in ('csv', 'msp', 'json', 'tsv')):
                        continue

                    url = f['links']['self']
                    size_mb = f['size'] / (1024 * 1024)
                    print(f"  Downloading: {name} ({size_mb:.1f} MB)")

                    try:
                        dl_resp = requests.get(url, timeout=60, stream=True)
                        if dl_resp.status_code == 200:
                            out_path = self.cache_dir / name
                            with open(out_path, 'wb') as f_out:
                                for chunk in dl_resp.iter_content(chunk_size=8192):
                                    f_out.write(chunk)
                            actual_mb = out_path.stat().st_size / (1024 * 1024)
                            print(f"  Saved: {name} ({actual_mb:.1f} MB)")
                            return out_path
                    except requests.exceptions.Timeout:
                        print(f"  Timeout downloading {name}")
                        continue
                    except requests.exceptions.ConnectionError as e:
                        print(f"  Connection error: {e}")
                        continue

            except requests.exceptions.Timeout:
                print(f"  Timeout")
                continue
            except requests.exceptions.ConnectionError as e:
                print(f"  Connection error: {e}")
                continue
            except Exception as e:
                print(f"  Error: {e}")
                continue

        # All attempts failed — manual instructions
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Zenodo download failed (network restricted?)   ║")
        print("  ║  Manual options:                                ║")
        print("  ║                                                  ║")
        print("  ║  1. NIST WebBook direct (free, public domain):  ║")
        print("  ║     https://webbook.nist.gov/chemistry/          ║")
        print("  ║     → Search compound → Mass spectrum → Download ║")
        print("  ║                                                  ║")
        print("  ║  2. Zenodo record (may need VPN):               ║")
        print("  ║     https://zenodo.org/records/12786324          ║")
        print("  ║     → Download CSV files                        ║")
        print("  ║                                                  ║")
        print("  ║  3. Place downloaded files in:                  ║")
        print(f"  ║     {self.cache_dir}║")
        print("  ║                                                  ║")
        print("  ║  MoNA live API will be used as fallback         ║")
        print("  ║  (no download needed, internet required)        ║")
        print("  ╚══════════════════════════════════════════════════╝")
        return None

    def download_all(self):
        """Download all available public libraries."""
        results = {}
        results['massbank'] = self.download_massbank_eu()
        results['nist_webbook'] = self.download_nist_webbook()
        return results

    def rebuild_cache(self):
        """Reload all libraries and rebuild the in-memory cache."""
        return self.load_all(include_downloaded=True)


# ============================================================
# Singleton convenience
# ============================================================
_global_manager = None


def get_library_manager(reload=False):
    """Get or create the global PublicLibraryManager singleton."""
    global _global_manager
    if _global_manager is None or reload:
        _global_manager = PublicLibraryManager()
        _global_manager.load_all()
    return _global_manager


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    import sys

    mgr = PublicLibraryManager()

    if len(sys.argv) > 1 and sys.argv[1] == 'download':
        print("Downloading public libraries...")
        results = mgr.download_all()
        print(f"\nResults: {results}")
        # Reload
        mgr.load_all()
    else:
        mgr.load_all()
        summary = mgr.get_library_summary()
        print("\n" + "=" * 60)
        print("Library Summary")
        print("=" * 60)
        print(f"  Total entries: {summary['total_entries']}")
        print(f"  Unique CAS numbers: {summary['total_unique_cas']}")
        print(f"  Sources: {summary['sources']}")
        print(f"  Categories: {summary['top_categories']}")

        # Test search
        if mgr.entries:
            print("\n" + "=" * 60)
            print("Example: searching for 'hexanal' by name")
            print("=" * 60)
            results = mgr.search_by_name("hexanal")
            for r in results[:3]:
                print(f"  {r['name']} | CAS: {r['cas']} | Source: {r['source']} | Peaks: {r['n_peaks']}")
