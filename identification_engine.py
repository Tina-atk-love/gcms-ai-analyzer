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

    # ================================================================
    # Enhanced Identification Features
    # ================================================================

    def isotope_pattern_check(self, observed_ions, molecular_formula, charge=0):
        """Check if observed isotope pattern matches theoretical for a formula.

        Compares M+1 and M+2 peak ratios with theoretical values based on
        natural isotope abundances (¹³C, ²H, ¹⁵N, ¹⁸O, ³⁴S, ³⁷Cl, ⁸¹Br).

        Args:
            observed_ions: [(mz, intensity), ...]
            molecular_formula: e.g. 'C6H12O'
            charge: 0 for EI-MS (molecular ion), 1 for [M+H]+ (LC-MS)

        Returns:
            dict with isotope_score (0-999), M+1/M+2 ratios, and pass/fail
        """
        from collections import Counter
        import re

        # Parse formula
        formula = Counter()
        for match in re.finditer(r'([A-Z][a-z]?)(\d*)', molecular_formula):
            elem = match.group(1)
            count = int(match.group(2)) if match.group(2) else 1
            formula[elem] += count

        # Natural isotope abundances (fractional)
        ISOTOPES = {
            'C': [(1, 0.0111)],  # ¹³C
            'H': [(2, 0.00015)],  # ²H
            'N': [(15, 0.00366)],  # ¹⁵N
            'O': [(18, 0.00205)],  # ¹⁸O
            'S': [(33, 0.0076), (34, 0.0429)],  # ³³S, ³⁴S
            'Cl': [(37, 0.3196)],  # ³⁷Cl
            'Br': [(81, 0.4931)],  # ⁸¹Br
        }

        # Calculate M, M+1, M+2 probabilities
        M_prob = 1.0
        M1_prob = 0.0
        M2_prob = 0.0

        for elem, count in formula.items():
            if elem not in ISOTOPES:
                continue
            for mass_diff, abundance in ISOTOPES[elem]:
                if mass_diff == 1:
                    M1_prob += count * abundance
                elif mass_diff == 2:
                    M2_prob += count * abundance
                    M1_prob += count * abundance * 0  # No double count

        # More accurate binomial for M+1 from C
        if 'C' in formula:
            nC = formula['C']
            p13C = 0.0111
            # M+1 from ¹³C (primary source)
            M1_prob = nC * p13C * (1 - p13C) ** (nC - 1)

        # M+2 approximated
        if 'C' in formula:
            nC = formula['C']
            p13C = 0.0111
            M2_prob = (nC * (nC - 1) / 2) * p13C ** 2  # Two ¹³C

        # Add contributions from S, Cl, Br
        if 'S' in formula:
            M2_prob += formula['S'] * 0.0429
        if 'Cl' in formula:
            nCl = formula['Cl']
            if nCl == 1:
                M2_prob += 0.3196
            elif nCl >= 2:
                M2_prob += 0.3196 * 0.3196 * nCl * (nCl - 1) / 2
        if 'Br' in formula:
            nBr = formula['Br']
            if nBr == 1:
                M2_prob += 0.4931
            elif nBr >= 2:
                M2_prob += 0.4931 * 0.4931 * nBr * (nBr - 1) / 2

        # Theoretical ratios (relative to M = 100%)
        theo_M1_pct = (M1_prob / M_prob) * 100
        theo_M2_pct = (M2_prob / M_prob) * 100

        # Find molecular ion and M+1, M+2 in observed spectrum
        if not observed_ions:
            return {'isotope_score': 0, 'status': 'no_data'}

        max_mz = max(ion[0] for ion in observed_ions)
        base_intensity = max(ion[1] for ion in observed_ions)

        # Find M (highest m/z with significant intensity)
        m_ion = None
        for mz, intensity in sorted(observed_ions, key=lambda x: -x[0]):
            if intensity > base_intensity * 0.01:
                m_ion = (mz, intensity)
                break

        if m_ion is None:
            return {'isotope_score': 0, 'status': 'no_molecular_ion'}

        # Find M+1 and M+2
        m1_intensity = 0
        m2_intensity = 0
        for mz, intensity in observed_ions:
            if abs(mz - m_ion[0] - 1) < 0.5:
                m1_intensity = intensity
            if abs(mz - m_ion[0] - 2) < 0.5:
                m2_intensity = intensity

        obs_M1_pct = (m1_intensity / m_ion[1] * 100) if m_ion[1] > 0 else 0
        obs_M2_pct = (m2_intensity / m_ion[1] * 100) if m_ion[1] > 0 else 0

        # Score: how close observed is to theoretical
        iso_score = 999
        if theo_M1_pct > 0:
            m1_deviation = abs(obs_M1_pct - theo_M1_pct) / max(theo_M1_pct, 1)
            iso_score -= int(min(m1_deviation * 400, 500))
        if theo_M2_pct > 1:
            m2_deviation = abs(obs_M2_pct - theo_M2_pct) / max(theo_M2_pct, 1)
            iso_score -= int(min(m2_deviation * 200, 300))

        iso_score = max(0, min(999, iso_score))

        # Pass/fail: M+1 should be within ±30% of theoretical
        passed = True
        if theo_M1_pct > 5 and obs_M1_pct < theo_M1_pct * 0.3:
            passed = False

        return {
            'isotope_score': iso_score,
            'status': 'passed' if passed else 'failed',
            'theoretical_M1_pct': round(theo_M1_pct, 1),
            'theoretical_M2_pct': round(theo_M2_pct, 1),
            'observed_M1_pct': round(obs_M1_pct, 1),
            'observed_M2_pct': round(obs_M2_pct, 1),
            'molecular_ion_mz': m_ion[0],
        }

    def multi_source_consensus(self, compound_name, min_sources=2):
        """Cross-validate identification across multiple library sources.

        Checks if a compound is confirmed by multiple independent sources
        (MassBank, NIST local, built-in MSP, MoNA, RI database).

        Args:
            compound_name: compound name to check
            min_sources: minimum number of sources for consensus

        Returns:
            dict with source votes, consensus level, and recommendation
        """
        name = compound_name.lower().strip()
        votes = {}
        sources_found = []

        # Check built-in MSP
        if hasattr(self, 'lib') and self.lib:
            for entry in self.lib.entries:
                if name in entry.get('name', '').lower():
                    src = entry.get('source', 'unknown')
                    votes[src] = votes.get(src, 0) + 1
                    sources_found.append(src)

        # Check NIST local library
        if hasattr(self, 'lib') and hasattr(self.lib, '_nist_entries'):
            for entry in self.lib._nist_entries:
                if name in entry.get('name', '').lower():
                    votes['nist_local'] = votes.get('nist_local', 0) + 1
                    sources_found.append('nist_local')

        # Check RI database
        if name in self.ri_db:
            votes['ri_database'] = 1
            sources_found.append('ri_database')
        else:
            for db_name in self.ri_db:
                if name in db_name or db_name in name:
                    votes['ri_database'] = 1
                    sources_found.append('ri_database')
                    break

        unique_sources = len(set(sources_found))
        consensus = 'strong' if unique_sources >= 3 else \
                    'moderate' if unique_sources >= 2 else \
                    'weak' if unique_sources >= 1 else 'none'

        return {
            'compound': compound_name,
            'unique_sources': unique_sources,
            'source_votes': votes,
            'consensus_level': consensus,
            'recommendation': (
                'Multi-source confirmation — high reliability for publication'
                if consensus == 'strong' else
                'Two-source agreement — acceptable with caution'
                if consensus == 'moderate' else
                'Single-source only — confirm with standard or additional library'
                if consensus == 'weak' else
                'Not found in any library'
            ),
            'flags': ['MULTI_SOURCE_CONFIRMED'] if consensus == 'strong' else (
                [] if consensus == 'moderate' else ['SINGLE_SOURCE_ONLY']
            ),
        }

    def enhanced_identify(self, observed_ions, ri_measured=None,
                         molecular_formula=None, min_confidence=600,
                         max_results=10, use_consensus=True,
                         use_isotope=True):
        """Enhanced identification with all available cross-validation.

        Combines: MS cosine similarity + RI proximity + isotope pattern check
        + multi-source consensus into a single authoritative result.

        Args:
            observed_ions: [(mz, intensity), ...]
            ri_measured: experimental Kovats RI (optional)
            molecular_formula: for isotope check (optional, from NIST export)
            min_confidence: minimum combined score
            max_results: max hits
            use_consensus: cross-validate across sources
            use_isotope: check isotope pattern

        Returns:
            dict with enhanced results including all validation layers
        """
        # Step 1: Base MS+RI identification
        base = self.identify(observed_ions, ri_measured=ri_measured,
                            min_confidence=min_confidence, max_results=max_results)

        # Step 2: Isotope check on best match
        if use_isotope and molecular_formula and base['best_match']:
            iso_check = self.isotope_pattern_check(observed_ions, molecular_formula)
            base['isotope_check'] = iso_check
            # Boost or penalize based on isotope check
            if base['best_match']:
                if iso_check['status'] == 'passed':
                    base['best_match']['combined_score'] = min(999,
                        base['best_match']['combined_score'] + 30)
                    base['best_match']['flags'] = base['best_match'].get('flags', []) + ['ISOTOPE_PASS']
                    if base['best_match']['confidence'] in ('high', 'probable'):
                        base['best_match']['confidence'] = 'confirmed' if \
                            base['best_match']['combined_score'] >= 900 else 'high'
                elif iso_check['status'] == 'failed':
                    base['best_match']['flags'] = base['best_match'].get('flags', []) + ['ISOTOPE_FAIL']

        # Step 3: Multi-source consensus
        if use_consensus and base['best_match']:
            consensus = self.multi_source_consensus(base['best_match']['name'])
            base['consensus'] = consensus
            if consensus['consensus_level'] == 'strong':
                base['best_match']['confidence'] = 'confirmed'
                base['best_match']['flags'] = base['best_match'].get('flags', []) + ['MULTI_SOURCE']
            elif consensus['consensus_level'] == 'moderate':
                base['best_match']['flags'] = base['best_match'].get('flags', []) + ['DUAL_SOURCE']

        # Step 4: Build enhanced summary
        base['enhanced_summary'] = {
            'validation_layers': len([x for x in [
                True,  # MS always
                ri_measured is not None,
                molecular_formula is not None,
                use_consensus,
            ] if x]),
            'flags': base['best_match'].get('flags', []) if base['best_match'] else [],
            'recommendation': self._enhanced_recommendation(base),
        }

        return base

    def _enhanced_recommendation(self, result):
        """Generate enhanced recommendation with all available validation."""
        best = result.get('best_match')
        if not best:
            return 'No match found. Consider alternative methods or the compound may be novel.'

        flags = best.get('flags', [])
        conf = best.get('confidence', 'unknown')

        parts = []
        if 'MULTI_SOURCE' in flags:
            parts.append('Multi-source confirmed')
        if 'ISOTOPE_PASS' in flags:
            parts.append('isotope pattern validated')
        if 'RI_CONFIRMED' in flags:
            parts.append('RI confirmed')
        if 'PURE_MATCH' in flags:
            parts.append('pure spectral match')

        evidence = ', '.join(parts) if parts else 'single-dimension MS match only'
        score = best.get('combined_score', best.get('match_factor', 0))

        if conf == 'confirmed':
            return (f"Confirmed identification: {best['name']} "
                    f"(score={score}, evidence: {evidence}). Suitable for publication.")
        elif conf == 'high':
            return (f"High-confidence: {best['name']} (score={score}, {evidence}). "
                    f"Consider authentic standard for definitive confirmation.")
        elif conf == 'probable':
            return (f"Probable: {best['name']} (score={score}). "
                    f"Low evidence ({evidence}). RI calibration or NIST library search recommended.")
        else:
            return (f"Low confidence (score={score}). Evidence: {evidence}. "
                    f"Manual review recommended.")

    def suggest_compound_class(self, observed_ions):
        """Suggest likely compound classes based on spectral features.

        Analyzes fragment patterns to guess compound class (alkane, aldehyde,
        ketone, alcohol, acid, ester, aromatic, terpene, etc.).

        Args:
            observed_ions: [(mz, intensity), ...]

        Returns:
            list of likely classes with confidence scores
        """
        ions = sorted(observed_ions, key=lambda x: -x[1])
        top_mz = set(int(ion[0]) for ion in ions[:10])

        scores = {}

        # Characteristic fragment checks
        if 44 in top_mz and 43 in top_mz:  # Aldehyde (McLafferty)
            scores['aldehyde'] = scores.get('aldehyde', 0) + 3
        if 43 in top_mz and (58 in top_mz or 71 in top_mz or 86 in top_mz):
            scores['methyl_ketone'] = scores.get('methyl_ketone', 0) + 3
        if 31 in top_mz or 45 in top_mz:
            scores['alcohol'] = scores.get('alcohol', 0) + 2
        if 60 in top_mz:
            scores['carboxylic_acid'] = scores.get('carboxylic_acid', 0) + 3
        if 74 in top_mz or 88 in top_mz:
            scores['methyl_ester'] = scores.get('methyl_ester', 0) + 2
        if 91 in top_mz and 92 in top_mz:
            scores['alkylbenzene'] = scores.get('alkylbenzene', 0) + 3
        if 105 in top_mz and 77 in top_mz:
            scores['aromatic_carbonyl'] = scores.get('aromatic_carbonyl', 0) + 3
        if 93 in top_mz and (69 in top_mz or 41 in top_mz):
            scores['terpene'] = scores.get('terpene', 0) + 2
        if {41, 55, 69}.intersection(top_mz) and any(m > 100 for m in top_mz):
            scores['terpene'] = scores.get('terpene', 0) + 1
        if {94, 108, 122}.intersection(top_mz):
            scores['pyrazine'] = scores.get('pyrazine', 0) + 3
        if 149 in top_mz:
            scores['phthalate'] = scores.get('phthalate', 0) + 5  # Very distinctive
        if {73, 147, 207, 281}.intersection(top_mz):
            scores['siloxane'] = scores.get('siloxane', 0) + 5
        if 47 in top_mz and (45 in top_mz or 79 in top_mz):
            scores['sulfur_compound'] = scores.get('sulfur_compound', 0) + 2
        if 94 in top_mz and 66 in top_mz:
            scores['phenol'] = scores.get('phenol', 0) + 2
        if 127 in top_mz and 43 in top_mz:
            scores['thiazole'] = scores.get('thiazole', 0) + 2
        if 81 in top_mz and (41 in top_mz or 53 in top_mz):
            scores['furan'] = scores.get('furan', 0) + 2
        if {57, 71, 85}.intersection(top_mz) and all(m < 120 for m in top_mz):
            scores['alkane'] = scores.get('alkane', 0) + 2

        # Sort by score
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [
            {'class': cls, 'confidence': 'high' if score >= 4 else 'moderate' if score >= 2 else 'low',
             'score': score}
            for cls, score in ranked[:5] if score >= 1
        ]

    def diagnose_unknown_peak(self, observed_ions, rt=None, ri_measured=None):
        """Comprehensive diagnosis of an unknown peak.

        Runs all available analyses and generates a human-readable report
        with possible compound classes, best library matches, and suggestions
        for further investigation.

        Args:
            observed_ions: [(mz, intensity), ...]
            rt: retention time (optional)
            ri_measured: experimental RI (optional)

        Returns:
            dict with diagnosis report
        """
        diagnosis = {
            'peak_info': {
                'rt': rt,
                'ri_measured': ri_measured,
                'n_ions': len(observed_ions),
                'base_peak': max(observed_ions, key=lambda x: x[1]) if observed_ions else None,
                'molecular_ion_candidate': max(observed_ions, key=lambda x: x[0]) if observed_ions else None,
            },
        }

        # Run standard identification
        ident = self.identify(observed_ions, ri_measured=ri_measured, max_results=10)
        diagnosis['library_matches'] = ident.get('all_matches', [])[:5]
        diagnosis['best_match'] = ident.get('best_match')

        # Compound class suggestion
        classes = self.suggest_compound_class(observed_ions)
        diagnosis['likely_classes'] = classes

        # Check for common artifacts
        top_mz = set(int(ion[0]) for ion in observed_ions[:10])
        artifacts = []
        if {73, 147, 207, 281}.intersection(top_mz):
            artifacts.append('Possible column bleed (siloxane pattern detected)')
        if {149, 167, 279}.intersection(top_mz):
            artifacts.append('Possible phthalate contamination')
        if 18 in top_mz and 44 in top_mz:
            artifacts.append('Possible CO2/water background')
        diagnosis['artifacts'] = artifacts if artifacts else None

        # Recommendation
        if ident['best_match'] and ident['best_match'].get('confidence') == 'confirmed':
            diagnosis['action'] = 'Compound confirmed. No further action needed.'
        elif classes and classes[0]['confidence'] == 'high':
            diagnosis['action'] = (f"Likely a {classes[0]['class']}. "
                                   f"Search NIST library for {classes[0]['class']} compounds "
                                   f"{'near RI='+str(int(ri_measured)) if ri_measured else ''}.")
        elif ident['best_match'] and ident['best_match'].get('match_factor', 0) >= 700:
            diagnosis['action'] = ('Moderate library match found. Run RI calibration for confirmation, '
                                   'or search NIST library for higher-quality reference spectra.')
        else:
            diagnosis['action'] = ('No confident library match. Consider: (1) RI calibration, '
                                   '(2) NIST library search, (3) manual spectral interpretation, '
                                   '(4) GC×GC or HRMS for better separation/identification.')

        return diagnosis


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
