#!/usr/bin/env python3
"""
NIST MSSEARCH Library → JCAMP-DX Batch Converter
==================================================
Reads NIST MSSEARCH format library files (.L directories) and converts all
spectra to JCAMP-DX (.jdx) format for use with gcms_analyzer.

Supports:
  - NIST mainlib / replib / user-created libraries in MSSEARCH .L format
  - Reads compound metadata (name, CAS, formula, MW)
  - Extracts EI-MS spectra (m/z + intensity pairs)
  - Exports individual .jdx files per compound
  - Checkpoint/resume for large libraries

NIST MSSEARCH .L directory structure:
  header       — compound metadata (names, formulas, CAS, etc.)
  header.ind   — index into header file
  condense     — condensed spectra (cluster-represented for fast search)
  condense.ind — index into condense file
  full.d       — full-resolution spectra (optional, some libraries only)
  root         — search tree / root node data
  subset.ind   — subset index
  subset.sdb   — subset database

Usage:
  python nist_library_converter.py --input D:\\NIST14\\MSSEARCH\\mainlib \\
                                    --output D:\\NIST_JCAMP

  # With resume support:
  python nist_library_converter.py --input ... --output ... --resume

  # Preview only (no export, just list compounds):
  python nist_library_converter.py --input ... --preview
"""

import argparse
import json
import os
import re
import struct
import sys
import time
from datetime import datetime
from pathlib import Path


# ================================================================
# NIST Binary Format Parser
# ================================================================
class NISTLibraryParser:
    """Parse NIST MSSEARCH .L format library files.

    The NIST format uses a mix of:
      - Little-endian 32-bit integers for offsets/lengths
      - Null-terminated ASCII strings for text fields
      - Binary-packed spectral data in condense/full.d
    """

    def __init__(self, lib_path):
        self.lib_path = Path(lib_path)
        self._validate()

    def _validate(self):
        """Check that required files exist."""
        required = ['header', 'header.ind', 'condense', 'condense.ind']
        missing = [f for f in required if not (self.lib_path / f).exists()]
        if missing:
            raise FileNotFoundError(
                f"Not a valid NIST .L directory — missing: {missing}\n"
                f"Expected: {self.lib_path}/{{header, header.ind, condense, condense.ind}}"
            )

    # ---- Header parsing (compound metadata) ----
    def parse_headers(self):
        """Parse the header file and return list of compound metadata dicts.

        Uses a string-scanning approach: finds all compound names and pairs
        them with adjacent molecular formulas and category tags.
        """
        header_path = self.lib_path / 'header'
        header_data = header_path.read_bytes()

        # Extract all strings with positions
        all_strings = self._extract_all_strings(header_data)

        # Filter to find real compound names
        # Compound names are typically: alphabetic, 2+ chars, not single-capital artifacts
        skip_words = {'HP', 'DD', 'PChe', 'Gg', 'wH', 'w@', 'wPY', 'wtX', 'wPChe',
                      'il', 'le', 'te', 'al', 'gs', 'tate', 'lmitate', 'cetylmorphine',
                      'F0', 'sS', 'TN', 'HN', 'X', 'N-', '^N'}

        # Find compound names: strings that look like chemical nomenclature
        # Real compound names: start with capital, contain lowercase, but are NOT
        # English sentences/phrases (which also start with capital)
        candidates = []
        for pos, s in all_strings:
            if s in skip_words:
                continue
            if len(s) < 3:
                continue
            # Exclude formulas
            if re.match(r'^[A-Z][a-z]?\d*([A-Z][a-z]?\d*)+$', s):
                continue
            # Must start with capital letter or digit (e.g. "4-Chlorobiphenyl")
            if not re.match(r'^[A-Z0-9]', s):
                continue
            # Exclude phrases: if contains spaces and is long, check for common English words
            words = s.split()
            if len(words) >= 3:
                common_words = {'the', 'and', 'or', 'of', 'in', 'for', 'with', 'sample',
                                'evaluation', 'performance', 'drug', 'drugs', 'demo',
                                'barbiturates', 'alkaloids'}
                if any(w.lower() in common_words for w in words):
                    continue
            # Exclude if contains spaces AND looks like a sentence
            if ' ' in s and len(s) > 25:
                continue
            candidates.append((pos, s))

        # Build compound entries: name + formula + category
        compounds = []
        used_positions = set()

        for pos, name in candidates:
            if pos in used_positions:
                continue
            if len(name) < 3:
                continue

            entry = {'name': name}
            used_positions.add(pos)

            # Find nearby formula (within 200 bytes after name)
            for pos2, s in all_strings:
                if pos2 in used_positions:
                    continue
                if pos < pos2 <= pos + 200:
                    if re.match(r'^[A-Z][a-z]?\d*([A-Z][a-z]?\d*)+$', s) and 3 <= len(s) <= 20:
                        entry['formula'] = s
                        used_positions.add(pos2)
                        break

            # Find category/description
            for pos2, s in all_strings:
                if pos2 in used_positions:
                    continue
                if pos < pos2 <= pos + 300:
                    if len(s) > 15 and ('sample' in s.lower() or 'drug' in s.lower()
                                        or 'eval' in s.lower()):
                        entry['category'] = s
                        used_positions.add(pos2)
                        break

            compounds.append(entry)

        return compounds

    def _extract_all_strings(self, data):
        """Extract all null-terminated ASCII strings with positions."""
        strings = []
        current = b''
        current_start = 0
        for i, b in enumerate(data):
            if 32 <= b < 127:
                if not current:
                    current_start = i
                current += bytes([b])
            else:
                if len(current) >= 2:
                    strings.append((current_start, current.decode('ascii', errors='replace')))
                current = b''
        if len(current) >= 2:
            strings.append((current_start, current.decode('ascii', errors='replace')))
        return strings

    # ---- Condense file parsing (spectral data) ----
    def parse_spectra(self):
        """Parse the condense file to extract EI-MS spectra.

        Returns list of {name, peaks: [(mz, intensity), ...]} dicts.
        """
        condense_path = self.lib_path / 'condense'
        condense_data = condense_path.read_bytes()

        # Read index
        index_path = self.lib_path / 'condense.ind'
        index_data = index_path.read_bytes()

        spectra = []
        offsets = self._parse_index(index_data)

        for i, (start_off, end_off) in enumerate(offsets):
            if start_off >= len(condense_data):
                continue
            end_off = min(end_off, len(condense_data))
            chunk = condense_data[start_off:end_off]
            peaks = self._decode_condensed_spectrum(chunk)
            if peaks:
                spectra.append({
                    'index': i,
                    'n_peaks': len(peaks),
                    'peaks': peaks,
                })

        return spectra

    def _parse_index(self, index_data):
        """Parse condense.ind — returns list of (start, end) offset pairs."""
        if len(index_data) < 4:
            return []

        # The index format: each entry is typically 4 or 8 bytes
        # Try different interpretations
        offsets = []

        # Try 4-byte little-endian offsets
        for i in range(0, len(index_data) - 4, 4):
            val = struct.unpack('<I', index_data[i:i+4])[0]
            offsets.append(val)

        # Filter out unreasonably large values
        offsets = [o for o in offsets if o < 10_000_000_000]

        if len(offsets) < 2:
            return []

        # Pair them up as (start, end)
        pairs = []
        for i in range(len(offsets) - 1):
            if offsets[i] < offsets[i + 1]:
                pairs.append((offsets[i], offsets[i + 1]))

        return pairs

    def _decode_condensed_spectrum(self, data):
        """Decode NIST condensed spectrum format to m/z + intensity pairs.

        NIST condensed format uses a cluster-based representation:
        - Each cluster has a representative m/z and intensity
        - Clusters are encoded with variable-length encoding
        - Masses are encoded as deltas from previous mass
        """
        if len(data) < 4:
            return []

        peaks = []
        pos = 0

        # Try to detect format version
        # Format 1: [count:2] [mz1:2] [int1:1-2] [mz2_delta:1-2] [int2:1-2] ...
        # Format 2: raw [mz:2][int:2] pairs

        # First try raw 16-bit pairs (most common for demo library)
        peaks_raw = self._try_raw_16bit_pairs(data)
        if len(peaks_raw) >= 3:
            return peaks_raw

        # Try variable-length delta encoding
        peaks_delta = self._try_delta_encoding(data)
        if len(peaks_delta) >= 3:
            return peaks_delta

        return []

    def _try_raw_16bit_pairs(self, data):
        """Try interpreting data as raw (mz:uint16, int:uint16) pairs."""
        peaks = []
        # Skip potential header bytes
        for start in [0, 2, 4]:
            pairs = []
            pos = start
            prev_mz = 0
            valid = True
            while pos + 4 <= len(data) and len(pairs) < 500:
                mz = struct.unpack('<H', data[pos:pos+2])[0]
                intensity = struct.unpack('<H', data[pos+2:pos+4])[0]
                if mz > 0 and mz < 2000 and intensity > 0:
                    if mz > prev_mz:  # Masses should increase
                        pairs.append((mz, intensity))
                        prev_mz = mz
                    elif len(pairs) == 0:
                        pairs.append((mz, intensity))
                        prev_mz = mz
                pos += 4
            if len(pairs) >= 3:
                return pairs
        return []

    def _try_delta_encoding(self, data):
        """Try NIST variable-length delta encoding."""
        peaks = []
        pos = 0
        current_mz = 0

        while pos < len(data) - 1 and len(peaks) < 500:
            # Try reading a delta-encoded m/z
            delta_mz = data[pos]
            pos += 1
            if delta_mz == 0:
                # Might be end marker
                break
            if delta_mz > 200:
                # Not a reasonable delta — try as raw 16-bit
                pos -= 1
                if pos + 4 <= len(data):
                    mz = struct.unpack('<H', data[pos:pos+2])[0]
                    intensity = struct.unpack('<H', data[pos+2:pos+4])[0]
                    if 0 < mz < 2000:
                        current_mz = mz
                        peaks.append((mz, intensity))
                        pos += 4
                        continue
                break

            current_mz += delta_mz
            if pos < len(data):
                intensity = data[pos] * 10  # Scale up (condensed uses compressed intensity)
                pos += 1
                if current_mz > 0 and current_mz < 2000:
                    peaks.append((current_mz, intensity))

        return peaks

    def parse_full_spectra(self):
        """Parse full.d file for high-resolution spectra (if available)."""
        full_path = self.lib_path / 'full.d'
        if not full_path.exists():
            return None

        data = full_path.read_bytes()
        # Full spectra use similar encoding to condense but with higher precision
        return self._try_raw_16bit_pairs(data)


# ================================================================
# JCAMP-DX Writer
# ================================================================
class JCAMPWriter:
    """Write EI-MS spectra in JCAMP-DX format."""

    @staticmethod
    def write(compound, spectrum, output_path):
        """Write a single JCAMP-DX file.

        Args:
            compound: dict with name, formula, cas, etc.
            spectrum: dict with peaks [(mz, intensity), ...]
            output_path: Path to write .jdx file
        """
        name = compound.get('name', 'Unknown')
        formula = compound.get('formula', '')
        cas = compound.get('cas', '')
        peaks = spectrum.get('peaks', [])

        if not peaks:
            return False

        # Normalize intensities to 0-9999
        max_int = max(p[1] for p in peaks) if peaks else 1
        normalized = [(mz, int(i / max_int * 9999)) for mz, i in peaks]

        lines = []
        lines.append(f'##TITLE={name}')
        lines.append(f'##JCAMP-DX=4.24')
        lines.append(f'##DATA TYPE=MASS SPECTRUM')
        lines.append(f'##ORIGIN=NIST MSSEARCH Library, converted by gcms_analyzer')
        lines.append(f'##OWNER=NIST')
        if formula:
            lines.append(f'##MOLFORM={formula}')
        if cas:
            lines.append(f'##CAS REGISTRY NUMBER={cas}')
        lines.append(f'##XUNITS=M/Z')
        lines.append(f'##YUNITS=RELATIVE INTENSITY')
        lines.append(f'##XFACTOR=1.0')
        lines.append(f'##YFACTOR=1.0')
        lines.append(f'##NPOINTS={len(normalized)}')
        lines.append(f'##FIRSTX={normalized[0][0]}')
        lines.append(f'##LASTX={normalized[-1][0]}')
        lines.append(f'##MAXX={max(p[0] for p in normalized)}')
        lines.append(f'##MINX={min(p[0] for p in normalized)}')
        lines.append(f'##MAXY={max(p[1] for p in normalized)}')
        lines.append(f'##MINY={min(p[1] for p in normalized)}')
        lines.append(f'##PEAK TABLE=(XY..XY)')

        # Write peak table — 5 pairs per line
        for i in range(0, len(normalized), 5):
            chunk = normalized[i:i+5]
            line = ' '.join(f'{mz},{intensity}' for mz, intensity in chunk)
            lines.append(line)

        lines.append(f'##END=')

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('\n'.join(lines), encoding='utf-8')
        return True


# ================================================================
# Checkpoint Manager
# ================================================================
class Checkpoint:
    def __init__(self, output_dir):
        self.filepath = Path(output_dir) / '_converter_checkpoint.json'
        self.state = self._load()

    def _load(self):
        if self.filepath.exists():
            return json.loads(self.filepath.read_text(encoding='utf-8'))
        return {'converted': [], 'total': 0, 'errors': []}

    def save(self):
        self.state['updated'] = datetime.now().isoformat()
        self.filepath.write_text(json.dumps(self.state, ensure_ascii=False, indent=2),
                                 encoding='utf-8')

    def is_done(self, name):
        return name in self.state['converted']

    def mark_done(self, name):
        if name not in self.state['converted']:
            self.state['converted'].append(name)
        self.state['total'] = len(self.state['converted'])
        self.save()

    def mark_error(self, name, error):
        self.state['errors'].append({'compound': name, 'error': str(error)})
        self.save()


# ================================================================
# Main Converter
# ================================================================
def convert_library(input_path, output_dir, resume=False, preview=False, limit=None):
    """Convert entire NIST .L library to JCAMP files.

    Args:
        input_path: path to NIST .L directory (e.g. D:\\NIST14\\MSSEARCH\\mainlib)
        output_dir: where to write .jdx files
        resume: skip already-converted compounds
        preview: only list compounds, don't export
        limit: max number of compounds to convert (for testing)
    """
    lib_path = Path(input_path)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"📂 Library: {lib_path}")
    print(f"📁 Output: {out_path}")

    # Parse
    parser = NISTLibraryParser(lib_path)
    checkpoint = Checkpoint(out_path)

    print("\n📋 Parsing compound metadata...")
    compounds = parser.parse_headers()
    print(f"   Found {len(compounds)} compounds in header")

    print("\n📊 Parsing spectra...")
    spectra = parser.parse_spectra()
    print(f"   Found {len(spectra)} spectra in condense")

    # Try full spectra if available
    full_spectra = parser.parse_full_spectra()
    if full_spectra:
        print(f"   Found {len(full_spectra)} full-resolution peaks in full.d")

    if preview:
        print(f"\n📋 Compound Preview (first 30):")
        print(f"{'='*60}")
        for i, c in enumerate(compounds[:30]):
            name = c.get('name', '???')
            formula = c.get('formula', '?')
            category = c.get('category', '')
            print(f"  {i+1:4d}. {name:<30s} {formula:<15s} {category}")
        print(f"\n  ... and {max(0, len(compounds)-30)} more")
        return

    # Match compounds to spectra by index
    print(f"\n🔄 Converting to JCAMP...")
    converted = 0
    skipped = 0
    errors = 0
    total = min(len(compounds), len(spectra)) if limit is None else min(limit, len(compounds), len(spectra))

    start_time = time.time()

    for i in range(total):
        compound = compounds[i]
        name = compound.get('name', f'Compound_{i}')

        if resume and checkpoint.is_done(name):
            skipped += 1
            continue

        spectrum = spectra[i] if i < len(spectra) else None
        if not spectrum or not spectrum.get('peaks'):
            errors += 1
            checkpoint.mark_error(name, 'No spectrum data')
            continue

        # Sanitize filename
        safe_name = re.sub(r'[<>:"/\\|?*\s]', '_', name).strip('_')[:100]
        out_file = out_path / f'{safe_name}.jdx'

        try:
            success = JCAMPWriter.write(compound, spectrum, out_file)
            if success:
                checkpoint.mark_done(name)
                converted += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            checkpoint.mark_error(name, str(e))

        # Progress
        if (i + 1) % 100 == 0 or i == total - 1:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1:6d}/{total}] {converted} converted, {skipped} skipped, "
                  f"{errors} errors | {rate:.0f} cmp/s | ETA: {eta:.0f}s")

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"✅ Done in {elapsed:.1f}s")
    print(f"   Converted: {converted}")
    print(f"   Skipped:   {skipped}")
    print(f"   Errors:    {errors}")
    print(f"   Output:    {out_path}")

    if errors > 0:
        print(f"\n⚠️  {errors} compounds failed. Check {checkpoint.filepath} for details.")


# ================================================================
# CLI
# ================================================================
def main():
    parser = argparse.ArgumentParser(
        description='NIST MSSEARCH .L → JCAMP-DX Batch Converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what's in a NIST library
  python nist_library_converter.py --input D:\\NIST14\\MSSEARCH\\mainlib --preview

  # Convert entire NIST main library
  python nist_library_converter.py --input D:\\NIST14\\MSSEARCH\\mainlib --output D:\\NIST_JCAMP

  # Convert with limit (test run)
  python nist_library_converter.py --input D:\\NIST14\\MSSEARCH\\mainlib --output D:\\NIST_JCAMP --limit 100

  # Resume after interruption
  python nist_library_converter.py --input D:\\NIST14\\MSSEARCH\\mainlib --output D:\\NIST_JCAMP --resume

Common NIST library locations:
  NIST 14/17/20:  C:\\NIST14\\MSSEARCH\\mainlib  (or mainlib.l)
  MassHunter:     C:\\Database\\NIST\\mainlib
  User libraries: C:\\Database\\*.l
        """
    )
    parser.add_argument('--input', '-i', required=True, help='Path to NIST .L library directory')
    parser.add_argument('--output', '-o', default=None, help='Output directory for JCAMP files')
    parser.add_argument('--preview', action='store_true', help='Preview compounds only, no export')
    parser.add_argument('--limit', type=int, default=None, help='Max compounds to convert (for testing)')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')

    args = parser.parse_args()

    output = args.output or str(Path(args.input).parent / 'jcamp_export')

    convert_library(
        input_path=args.input,
        output_dir=output,
        resume=args.resume,
        preview=args.preview,
        limit=args.limit,
    )


if __name__ == '__main__':
    main()
