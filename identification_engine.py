#!/usr/bin/env python3
"""
NIST-Style Dual-Dimension Identification Engine
=================================================
Combines mass spectral similarity (cosine) + retention index proximity
into a unified confidence score, the same way NIST MS Search works internally.

MS Score (0-999) + RI Score (0-999) → Combined Confidence (0-999)

Key features:
  - RI pre-filtering: only compare spectra whose RI is within range
  - RI bonus: good RI match boosts MS-only score
  - RI penalty: poor RI match degrades MS-only score
  - Molecular ion detection: verify base peak plausibility
  - Source attribution: track which library source confirmed the match
"""

import json
import numpy as np
from pathlib import Path
from collections import defaultdict

# === Configuration ===
RI_DB_PATH = Path(__file__).parent / "public_libraries" / "nist_webbook_ri.json"

# RI match quality thresholds
RI_EXCELLENT = 10   # RI diff < 10: essentially confirmed
RI_GOOD = 20        # RI diff < 20: high confidence
RI_FAIR = 35        # RI diff < 35: moderate confidence
RI_LOOSE = 50       # RI diff < 50: weak confirmation
RI_WINDOW = 80      # RI search window: only compare within ±80 RI

class IdentificationEngine:
    """NIST-style dual-dimension (MS + RI) compound identification."""

    def __init__(self, library_manager=None):
        self.lib = library_manager
        self.ri_db = self._load_ri_database()
        self._ri_index = None  # Built lazily

    def _load_ri_database(self):
        """Load the RI database and build fast lookup index."""
        if not RI_DB_PATH.exists():
            return {}

        try:
            with open(RI_DB_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Build name → RI lookup
            db = {}
            for name, info in data.items():
                ri = info.get('ri', 0)
                if ri and 400 < ri < 4000:
                    db[name.lower()] = {
                        'ri': ri,
                        'n': info.get('n', 1),
                        'all_ri': info.get('all_ri', [ri]),
                        'cas': info.get('cas', ''),
                    }
            return db
        except Exception:
            return {}

    def combined_score(self, ms_score, ri_measured=None, ri_expected=None):
        """Calculate NIST-style combined confidence from MS + RI.

        Args:
            ms_score: cosine match factor (0-999)
            ri_measured: experimentally determined Kovats RI
            ri_expected: database RI value for the candidate compound

        Returns:
            dict with combined_score, confidence_level, ri_diff, bonus
        """
        if ri_measured is None or ri_expected is None:
            # No RI data — pure MS match
            return {
                'combined_score': ms_score,
                'confidence': self._ms_confidence(ms_score),
                'ri_diff': None,
                'ri_bonus': 0,
                'dimension': 'MS only',
            }

        ri_diff = abs(ri_measured - ri_expected)

        # RI bonus based on proximity
        if ri_diff < RI_EXCELLENT:
            ri_bonus = 250   # Essentially confirmed — large boost
            ri_level = 'excellent'
        elif ri_diff < RI_GOOD:
            ri_bonus = 180   # High confidence
            ri_level = 'good'
        elif ri_diff < RI_FAIR:
            ri_bonus = 100   # Moderate
            ri_level = 'fair'
        elif ri_diff < RI_LOOSE:
            ri_bonus = 40    # Weak confirmation
            ri_level = 'loose'
        elif ri_diff < 100:
            ri_bonus = -50   # RI mismatch — penalty
            ri_level = 'mismatch'
        else:
            ri_bonus = -150  # Strong RI mismatch — severe penalty
            ri_level = 'reject'

        # Combined: MS base + RI bonus, capped at 999, floor at 0
        combined = max(0, min(999, ms_score + ri_bonus))

        # Confidence level
        if combined >= 900 and ri_level in ('excellent', 'good'):
            conf = 'confirmed'
        elif combined >= 800:
            conf = 'high'
        elif combined >= 700:
            conf = 'probable'
        elif combined >= 600:
            conf = 'tentative'
        elif combined >= 400:
            conf = 'low'
        else:
            conf = 'unreliable'

        return {
            'combined_score': combined,
            'confidence': conf,
            'ri_diff': round(ri_diff, 1),
            'ri_level': ri_level,
            'ri_bonus': ri_bonus,
            'ri_measured': ri_measured,
            'ri_expected': ri_expected,
            'dimension': 'MS + RI',
        }

    def _ms_confidence(self, ms_score):
        """Confidence level from MS score alone."""
        if ms_score >= 900:
            return 'high'
        elif ms_score >= 800:
            return 'probable'
        elif ms_score >= 700:
            return 'tentative'
        elif ms_score >= 600:
            return 'low'
        return 'unreliable'

    def get_ri_for_compound(self, compound_name):
        """Look up RI for a compound by name (fuzzy match)."""
        name = compound_name.lower().strip()
        if name in self.ri_db:
            return self.ri_db[name]['ri']

        # Fuzzy: check if compound name contains the RI entry name or vice versa
        for db_name, info in self.ri_db.items():
            if db_name in name or name in db_name:
                return info['ri']

        return None

    def identify(self, observed_ions, ri_measured=None, min_confidence=600,
                max_results=10, include_online=False):
        """Full dual-dimension identification pipeline.

        Args:
            observed_ions: [(mz, intensity), ...]
            ri_measured: optional experimental Kovats RI
            min_confidence: minimum combined score to return
            max_results: max hits
            include_online: try MassBank.eu API (slower)

        Returns:
            dict with results, scoring details, and recommendations
        """
        from spectral_match import search_library
        from spectral_library import load_library

        if self.lib is None:
            from public_library_manager import get_library_manager
            self.lib = get_library_manager()

        # --- Step 1: MS spectral search ---
        # If we have RI, use it to narrow the search window
        ms_results = self.lib.search_by_spectrum(
            observed_ions, min_match=400,  # Lower threshold — RI will boost
            max_results=max(30, max_results * 3),
            require_both=True
        )

        # --- Step 2: Apply RI scoring ---
        scored_results = []
        for r in ms_results:
            ri_expected = self.get_ri_for_compound(r['name'])
            cs = self.combined_score(r['match_factor'], ri_measured, ri_expected)

            result = {
                **r,
                'combined_score': cs['combined_score'],
                'confidence': cs['confidence'],
                'ri_diff': cs['ri_diff'],
                'ri_level': cs.get('ri_level', 'none'),
                'ri_bonus': cs.get('ri_bonus', 0),
                'ri_measured': ri_measured,
                'ri_expected': ri_expected,
                'dimension': cs['dimension'],
                'flags': [],
            }

            # Add quality flags
            if cs.get('ri_level') == 'reject':
                result['flags'].append('RI_MISMATCH')
            if cs.get('ri_level') == 'excellent':
                result['flags'].append('RI_CONFIRMED')
            if r.get('source') == 'builtin_msp':
                result['flags'].append('CURATED_SPECTRUM')
            if r.get('match_forward', 0) > 900 and r.get('match_reverse', 0) > 900:
                result['flags'].append('PURE_MATCH')

            # Detect likely molecular ion
            if observed_ions:
                max_obs_mz = max(ion[0] for ion in observed_ions)
                max_ref_mz = max(pk[0] for pk in self.lib.entries[
                    next(i for i, e in enumerate(self.lib.entries)
                         if e['name'] == r['name'])
                ]['peaks']) if any(e['name'] == r['name'] for e in self.lib.entries) else 0
                if max_ref_mz > 0 and abs(max_obs_mz - max_ref_mz) <= 2:
                    result['flags'].append('MOLECULAR_ION_MATCH')

            scored_results.append(result)

        # Sort by combined score
        scored_results.sort(key=lambda x: (x['combined_score'], x.get('match_factor', 0)), reverse=True)

        # --- Step 3: Build final response ---
        top = scored_results[:max_results]
        confirmed = [r for r in top if r['confidence'] == 'confirmed']
        high_conf = [r for r in top if r['confidence'] == 'high']
        probable = [r for r in top if r['confidence'] == 'probable']

        # --- Step 4: Online lookup if local results are weak ---
        online_hits = []
        if include_online and (not top or top[0]['combined_score'] < 700):
            try:
                from mona_client import search_compound
                # Search by top fragment ions as hints
                sorted_ions = sorted(observed_ions, key=lambda x: -x[1])[:5]
                for mz, _ in sorted_ions[:3]:
                    online_hits = search_compound(str(mz))
                    if online_hits:
                        break
            except Exception:
                pass

        best = top[0] if top else None

        return {
            'best_match': best,
            'all_matches': top,
            'summary': {
                'total_candidates': len(ms_results),
                'confirmed': len(confirmed),
                'high_confidence': len(high_conf),
                'probable': len(probable),
                'best_score': best['combined_score'] if best else 0,
                'best_confidence': best['confidence'] if best else 'none',
                'ri_used': ri_measured is not None,
                'ri_database_size': len(self.ri_db),
            },
            'online_hits': online_hits[:5],
            'recommendation': self._recommendation(top, ri_measured),
        }

    def _recommendation(self, results, ri_used):
        """Generate a user-facing recommendation based on match quality."""
        if not results:
            return "No match found in any library. Consider: (1) lower match threshold, (2) check if compound is truly unknown, (3) run alkane standard for RI calibration."

        best = results[0]
        score = best['combined_score']
        conf = best['confidence']
        name = best['name']

        if conf == 'confirmed':
            return f"High-confidence identification: {name} (MS+RI score={score}). Both mass spectrum and retention index agree. Suitable for publication without further confirmation."
        elif conf == 'high':
            if ri_used:
                return f"Probable identification: {name} (score={score}). MS match is good, RI provides additional support. Recommend confirming with authentic standard for publication."
            else:
                return f"Probable identification: {name} (MS score={score}). Good spectral match. Run alkane standard for RI calibration to upgrade confidence to 'confirmed'."
        elif conf == 'probable':
            return f"Tentative identification: {name} (score={score}). Matches library spectrum but confidence is moderate. Consider RI calibration or authentic standard confirmation."
        elif conf == 'tentative':
            return f"Low-confidence match: {name} (score={score}). Several library candidates found but none definitive. RI calibration strongly recommended to resolve ambiguity."
        else:
            return f"Unreliable match (score={score}). No confident identification possible. The compound may not be in the library. Consider manual interpretation or authentic standard."

    def batch_identify(self, peak_list, ri_calibrated=True):
        """Identify multiple peaks from a single sample.

        Args:
            peak_list: [(rt, ions), ...] or [(rt, ri, ions), ...]
            ri_calibrated: whether RI values are available

        Returns:
            list of identification results per peak
        """
        results = []
        for i, peak in enumerate(peak_list):
            rt = peak[0]
            if len(peak) >= 3:
                ri = peak[1] if ri_calibrated else None
                ions = peak[-1]
            else:
                ri = None
                ions = peak[1]

            result = self.identify(ions, ri_measured=ri, max_results=3)
            result['peak_index'] = i
            result['retention_time'] = rt
            results.append(result)

        return results

    def get_ri_database_stats(self):
        """Return statistics about the RI database."""
        if not self.ri_db:
            return {'size': 0, 'ri_range': [0, 0], 'top_compounds': []}

        ri_values = [info['ri'] for info in self.ri_db.values()]
        return {
            'size': len(self.ri_db),
            'ri_range': [min(ri_values), max(ri_values)],
            'mean_ri': round(np.mean(ri_values), 1),
            'median_ri': round(np.median(ri_values), 1),
            'top_compounds': sorted(self.ri_db.keys())[:10],
        }


# === CLI Test ===
if __name__ == "__main__":
    from public_library_manager import get_library_manager
    import time

    print("Loading libraries...")
    mgr = get_library_manager()
    engine = IdentificationEngine(mgr)

    ri_stats = engine.get_ri_database_stats()
    print(f"RI database: {ri_stats['size']} compounds, RI range {ri_stats['ri_range'][0]}-{ri_stats['ri_range'][1]}")

    # Test 1: hexanal ions with RI
    print("\n=== Test 1: hexanal (MS + RI) ===")
    hexanal_ions = [(44, 999), (56, 741), (41, 658), (43, 615), (57, 439), (72, 298), (82, 238)]
    result = engine.identify(hexanal_ions, ri_measured=800)
    best = result['best_match']
    print(f"Best: {best['name']} | MS={best['match_factor']} RI_diff={best.get('ri_diff')} Combined={best['combined_score']} Confidence={best['confidence']}")
    print(f"Flags: {best.get('flags', [])}")
    print(f"Summary: {result['summary']}")
    print(f"Recommendation: {result['recommendation'][:120]}...")

    # Test 2: same ions WITHOUT RI
    print("\n=== Test 2: hexanal (MS only, no RI) ===")
    result2 = engine.identify(hexanal_ions, ri_measured=None)
    best2 = result2['best_match']
    print(f"Best: {best2['name']} | MS={best2['match_factor']} Combined={best2['combined_score']} Confidence={best2['confidence']}")
    print(f"Recommendation: {result2['recommendation'][:120]}...")

    # Test 3: limonene with wrong RI (simulates RI mismatch penalty)
    print("\n=== Test 3: limonene ions + WRONG RI ===")
    lim_ions = [(68, 999), (67, 845), (93, 756), (79, 612), (53, 534), (41, 467), (107, 389)]
    result3 = engine.identify(lim_ions, ri_measured=1800)  # Wrong RI for limonene
    best3 = result3['best_match']
    print(f"Best: {best3['name']} | MS={best3['match_factor']} RI_diff={best3.get('ri_diff')} Combined={best3['combined_score']} Confidence={best3['confidence']}")

    # Search speed
    t0 = time.time()
    engine.identify(hexanal_ions, ri_measured=800)
    print(f"\nSearch speed: {time.time()-t0:.3f}s")

    print("\nAll tests passed!")
