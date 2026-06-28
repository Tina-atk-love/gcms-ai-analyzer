"""
Spectral matching engine: NIST-style forward/reverse/hybrid search
with optional Retention Index (RI) consistency filtering.

Compares experimental mass spectra against MSP spectral library.
"""

import numpy as np


# ----- Core similarity functions -----

def _match_ions(observed, reference, tolerance=0.5):
    """Match reference ions to observed ions within m/z tolerance.

    Returns:
        (weighted_sum, total_ref_sq, total_obs_sq, matched_count, total_ref_count)
    """
    if not observed or not reference:
        return 0.0, 0.0, 0.0, 0, 0

    obs_mz = np.array([o[0] for o in observed], dtype=np.float64)
    obs_int = np.array([o[1] for o in observed], dtype=np.float64)
    ref_mz = np.array([r[0] for r in reference], dtype=np.float64)
    ref_int = np.array([r[1] for r in reference], dtype=np.float64)

    total_ref_sq = float(np.sum(ref_int ** 2))
    total_obs_sq = float(np.sum(obs_int ** 2))

    if total_ref_sq == 0 or total_obs_sq == 0:
        return 0.0, total_ref_sq, total_obs_sq, 0, len(reference)

    weighted_sum = 0.0
    matched = 0

    for i in range(len(ref_mz)):
        diffs = np.abs(obs_mz - ref_mz[i])
        best_idx = int(np.argmin(diffs))
        if diffs[best_idx] <= tolerance:
            weighted_sum += float(ref_int[i]) * float(obs_int[best_idx])
            matched += 1

    return weighted_sum, total_ref_sq, total_obs_sq, matched, len(reference)


def _scale_to_nist(cosine):
    """Scale cosine similarity to NIST-style match factor (0-999)."""
    return min(999, max(0, int(cosine * 999)))


def cosine_similarity(observed_ions, reference_ions, tolerance=0.5):
    """Standard weighted cosine similarity (forward match).

    Measures how well the observed spectrum matches the library spectrum.
    All observed ions should be explained by the reference.

    Returns:
        int: NIST-style match factor 0-999
    """
    ws, tr, to, matched, total = _match_ions(observed_ions, reference_ions, tolerance)
    if tr == 0 or to == 0:
        return 0
    cosine = ws / np.sqrt(tr * to)
    return _scale_to_nist(cosine)


def forward_match(observed_ions, reference_ions, tolerance=0.5):
    """NIST Forward Search: observed vs library.

    Penalises observed ions not found in the library spectrum.
    Best for pure compounds where the unknown spectrum is clean.
    """
    ws, tr, to, matched, total = _match_ions(observed_ions, reference_ions, tolerance)
    if tr == 0 or to == 0:
        return 0

    # Forward: normalize by observed total (did we explain all observed ions?)
    forward_cosine = ws / np.sqrt(tr * to)

    # Additional penalty for unmatched observed ions
    obs_mz = np.array([o[0] for o in observed_ions], dtype=np.float64)
    ref_mz = np.array([r[0] for r in reference_ions], dtype=np.float64)
    obs_matched = 0
    for i in range(len(obs_mz)):
        diffs = np.abs(ref_mz - obs_mz[i])
        if np.min(diffs) <= tolerance:
            obs_matched += 1

    coverage = obs_matched / max(len(observed_ions), 1)
    # Weight: 80% cosine + 20% coverage
    combined = 0.8 * forward_cosine + 0.2 * coverage

    return _scale_to_nist(combined)


def reverse_match(observed_ions, reference_ions, tolerance=0.5):
    """NIST Reverse Search: library vs observed.

    Measures how well the library spectrum is contained within the observed.
    Ignores extra ions in observed (may be contaminants/co-elution).
    Best for mixture analysis or noisy spectra.
    """
    ws, tr, to, matched, total = _match_ions(observed_ions, reference_ions, tolerance)
    if tr == 0:
        return 0

    # Reverse: normalize by reference total (did we find all library ions?)
    reverse_cosine = ws / np.sqrt(tr * tr)  # note: tr not to

    # Coverage: fraction of library ions matched
    coverage = matched / max(total, 1)
    combined = 0.7 * reverse_cosine + 0.3 * coverage

    return _scale_to_nist(combined)


def hybrid_match(observed_ions, reference_ions, tolerance=0.5,
                 forward_weight=0.6):
    """NIST Hybrid Search: weighted combination of forward + reverse.

    Default 60/40 forward/reverse split (NIST default).
    Higher forward_weight → more emphasis on explaining observed ions.
    Higher reverse_weight → more tolerant of contaminants.
    """
    fwd = forward_match(observed_ions, reference_ions, tolerance) / 999.0
    rev = reverse_match(observed_ions, reference_ions, tolerance) / 999.0

    hybrid = forward_weight * fwd + (1 - forward_weight) * rev
    return _scale_to_nist(hybrid)


# ----- RI consistency scoring -----

def ri_consistency_penalty(ri_library, ri_expected, ri_tolerance=50):
    """Compute penalty factor for RI mismatch.

    Args:
        ri_library: RI value from the library entry (or None)
        ri_expected: expected RI based on calibration or RT estimation
        ri_tolerance: acceptable deviation (default ±50 for same column type)

    Returns:
        float: penalty factor 0.0-1.0 (1.0 = perfect match, <1.0 = penalized)
    """
    if ri_library is None or ri_expected is None:
        return 1.0  # No RI data → no penalty

    diff = abs(ri_library - ri_expected)

    if diff <= ri_tolerance:
        return 1.0  # Within tolerance: full score
    elif diff <= ri_tolerance * 2:
        # Linear ramp from 1.0 down to 0.5
        return 1.0 - 0.5 * (diff - ri_tolerance) / ri_tolerance
    elif diff <= ri_tolerance * 4:
        # Linear ramp from 0.5 down to 0.1
        return 0.5 - 0.4 * (diff - ri_tolerance * 2) / (ri_tolerance * 2)
    else:
        return 0.1  # Far outside: heavy penalty but not zero


def estimate_ri_from_rt(rt_minutes, column_type='db5'):
    """Rough RI estimate from retention time (no calibration).

    This is a VERY rough heuristic — proper calibration with alkane
    standards is strongly recommended. Based on typical DB-5 conditions:
    40°C → 280°C at 10°C/min, 1 mL/min He.

    Args:
        rt_minutes: retention time in minutes
        column_type: 'db5', 'dbwax', or 'db1'

    Returns:
        float: estimated Kovats RI (very approximate!)
    """
    # Rough linear approximation for DB-5 (most common GC column)
    # Alkanes on DB-5 at ~10°C/min: C8~800@8min, C20~2000@20min, C30~3000@30min
    if column_type == 'db5':
        # RI ≈ 100 * RT (rough rule of thumb for standard conditions)
        return rt_minutes * 100.0
    elif column_type == 'dbwax':
        # WAX columns shift polar compounds later
        return rt_minutes * 110.0
    else:
        return rt_minutes * 100.0


# ----- Main search functions -----

def search_library(observed_ions, library=None, min_match=600,
                   search_mode='hybrid', tolerance=0.5,
                   ri_expected=None, ri_tolerance=50,
                   ri_boost=True):
    """Search observed mass spectrum against spectral library.

    Args:
        observed_ions: list of (mz, intensity) tuples
        library: list of library entries (from parse_msp_file / load_library)
        min_match: minimum match factor to include (0-999)
        search_mode: 'cosine', 'forward', 'reverse', or 'hybrid' (default)
        tolerance: m/z matching tolerance in Da (default 0.5)
        ri_expected: optional expected RI (from alkane calibration)
        ri_tolerance: acceptable RI deviation (default ±50)
        ri_boost: if True, boost matches with RI support; if False, only penalize

    Returns:
        list of dicts: [{name, cas, formula, match_factor, ri, ri_penalty, ...}]
        sorted by effective score descending (spectral match × RI penalty)
    """
    from spectral_library import load_library as _load_library

    if library is None:
        library = _load_library()

    # Select matcher
    matchers = {
        'cosine': cosine_similarity,
        'forward': forward_match,
        'reverse': reverse_match,
        'hybrid': hybrid_match,
    }
    matcher = matchers.get(search_mode, hybrid_match)

    # Step 1: Compute spectral match for all entries
    results = []
    for entry in library:
        if 'peaks' not in entry or not entry['peaks']:
            continue

        mf = matcher(observed_ions, entry['peaks'], tolerance)

        if mf >= min_match:
            # RI check
            lib_ri = entry.get('ri_exp')
            penalty = ri_consistency_penalty(lib_ri, ri_expected, ri_tolerance)

            # Effective score (spectral match × RI penalty)
            effective_mf = int(mf * penalty)

            if effective_mf >= min_match or mf >= min_match:
                results.append({
                    'name': entry['name'],
                    'cas': entry.get('cas', ''),
                    'formula': entry.get('formula', ''),
                    'match_factor': mf,
                    'effective_match': effective_mf,
                    'ri': lib_ri,
                    'ri_penalty': penalty,
                    'num_peaks': entry.get('num_peaks', 0),
                })

    # Step 2: Sort by effective match (spectral × RI)
    results.sort(key=lambda x: x['effective_match'], reverse=True)

    # Step 3: If RI boost is enabled, gently promote RI-supported matches
    if ri_boost and ri_expected is not None and len(results) > 1:
        # Find the best RI-supported match
        ri_supported = [r for r in results if r['ri'] is not None]
        if ri_supported:
            best_ri = max(ri_supported, key=lambda r: r['effective_match'])
            best_overall = results[0]

            # If the best RI-supported match has a good spectral score
            # and isn't already #1, consider boosting
            if (best_overall['ri'] is None
                    and best_ri['match_factor'] >= best_overall['match_factor'] - 80
                    and best_ri['ri_penalty'] >= 0.9):
                # Promote RI-supported match to #1 if spectral score is close
                results.remove(best_ri)
                results.insert(0, best_ri)

    return results


def identify_compound(observed_ions, library=None, min_match=600,
                      search_mode='hybrid', ri_expected=None):
    """Identify a single compound from its mass spectrum.

    Returns best match or None. Uses hybrid search + RI filtering by default.
    """
    results = search_library(
        observed_ions, library, min_match,
        search_mode=search_mode, ri_expected=ri_expected
    )
    if results:
        return results[0]
    return None
