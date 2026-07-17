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


# ----- Category-based boosting -----

def category_boost_factor(entry, target_category='food_flavor'):
    """Compute a boost/penalty factor based on compound classification.

    Food/flavor compounds get a boost, pharmaceuticals/industrial get penalized.
    Unclassified compounds are neutral.

    Returns:
        float: multiplier 0.7-1.2 (0.7=penalized, 1.0=neutral, 1.2=boosted)
    """
    if not entry:
        return 1.0

    cat = entry.get('compound_class', 'other')
    conf = entry.get('class_confidence', 0.0)

    if cat == 'food_flavor':
        # Boost food/flavor: 1.05 - 1.20 depending on confidence
        return 1.05 + 0.15 * conf
    elif cat == 'natural_product':
        return 1.05 + 0.10 * conf
    elif cat == 'pharmaceutical':
        # Penalize pharma: 0.70 - 0.85 (reverse of confidence)
        return 0.85 - 0.15 * min(conf, 1.0)
    elif cat == 'industrial':
        # Stronger penalty for industrial
        return 0.75 - 0.10 * min(conf, 1.0)
    else:
        return 1.0  # 'other': neutral


# ----- Enhanced NIST-Style Search Algorithms -----

# Common EI-MS fragment ions (non-diagnostic, appear in many compounds)
# These are penalized in NIST-style matching because they provide little
# discriminatory power for compound identification.
COMMON_FRAGMENTS = {41, 42, 43, 44, 45, 55, 56, 57, 58, 59, 67, 69, 70, 71, 73, 74, 75, 77, 79, 81, 83, 85, 91, 93, 95, 97, 105, 107, 119, 121, 133, 135, 147, 149}

COMMON_FRAGMENT_PENALTY = 0.5  # Weight reduction for common fragments


def weighted_cosine_nist(observed_ions, reference_ions, tolerance=0.5,
                         penalize_common=True, base_peak_weight=2.0):
    """NIST-style weighted cosine similarity.

    Improvements over simple cosine:
      - Penalizes common fragment ions (m/z 41, 43, 55, etc.)
      - Boosts base peak importance (most diagnostic ion)
      - Uses forward match (all ref ions must be in observed)

    This produces match factors much closer to NIST MS Search results.

    Args:
        observed_ions: [(mz, intensity), ...]
        reference_ions: [(mz, intensity), ...]
        tolerance: m/z tolerance
        penalize_common: reduce weight of ubiquitous EI fragments
        base_peak_weight: multiplier for base peak contribution

    Returns:
        int: NIST-style match factor 0-999
    """
    if not observed_ions or not reference_ions:
        return 0

    obs_mz = np.array([o[0] for o in observed_ions], dtype=float)
    obs_int = np.array([o[1] for o in observed_ions], dtype=float)

    # Normalize observed to base peak = 999
    if obs_int.max() > 0:
        obs_int = obs_int / obs_int.max() * 999

    ref_mz = np.array([r[0] for r in reference_ions], dtype=float)
    ref_int = np.array([r[1] for r in reference_ions], dtype=float)
    if ref_int.max() > 0:
        ref_int = ref_int / ref_int.max() * 999

    # Find base peaks
    obs_bp_mz = int(obs_mz[np.argmax(obs_int)])
    ref_bp_mz = int(ref_mz[np.argmax(ref_int)])

    # Build weight arrays
    obs_weights = np.ones_like(obs_int)
    ref_weights = np.ones_like(ref_int)

    if penalize_common:
        for i, mz in enumerate(obs_mz):
            if int(mz) in COMMON_FRAGMENTS:
                obs_weights[i] = COMMON_FRAGMENT_PENALTY
        for i, mz in enumerate(ref_mz):
            if int(mz) in COMMON_FRAGMENTS:
                ref_weights[i] = COMMON_FRAGMENT_PENALTY

    # Boost base peak
    for i, mz in enumerate(obs_mz):
        if int(mz) == obs_bp_mz:
            obs_weights[i] *= base_peak_weight
    for i, mz in enumerate(ref_mz):
        if int(mz) == ref_bp_mz:
            ref_weights[i] *= base_peak_weight

    # Weighted forward match
    total_ref_sq = float(np.sum((ref_int * ref_weights) ** 2))
    total_obs_sq = float(np.sum((obs_int * obs_weights) ** 2))

    if total_ref_sq == 0 or total_obs_sq == 0:
        return 0

    weighted_sum = 0.0
    matched_count = 0
    for i in range(len(ref_mz)):
        diffs = np.abs(obs_mz - ref_mz[i])
        best_idx = int(np.argmin(diffs))
        if diffs[best_idx] <= tolerance:
            w = ref_weights[i] * obs_weights[best_idx]
            weighted_sum += float(ref_int[i]) * float(obs_int[best_idx]) * w
            matched_count += 1

    # Penalize unmatched reference ions
    match_ratio = matched_count / len(ref_mz)
    if match_ratio < 0.5:
        weighted_sum *= match_ratio / 0.5  # Severe penalty for <50% ions matched

    cosine = weighted_sum / np.sqrt(total_ref_sq * total_obs_sq)
    return _scale_to_nist(cosine)


def average_apex_spectra(ms_reader, rt_center, n_scans=5):
    """Average mass spectra across the peak apex for better S/N.

    NIST MS Search typically averages 3-5 scans around the peak apex
    to reduce noise before library matching.

    Args:
        ms_reader: Aston AgilentMS reader
        rt_center: peak apex RT in minutes
        n_scans: number of scans to average (odd number recommended)

    Returns:
        [(mz, intensity), ...] — averaged spectrum
    """
    import scipy.sparse
    times = np.array(ms_reader.data.traces[0].index)
    if times.max() > 100:
        times = times / 60000

    center_idx = int(np.argmin(np.abs(times - rt_center)))
    half = n_scans // 2
    start = max(0, center_idx - half)
    end = min(len(times), center_idx + half + 1)

    V = ms_reader.data.values
    traces = ms_reader.data.traces

    # Sum spectra across window
    summed = np.zeros(len(traces))
    for idx in range(start, end):
        row = V[idx]
        if scipy.sparse.issparse(row):
            row = row.toarray().ravel()
        summed += row

    # Average
    n_actual = end - start
    if n_actual > 1:
        summed /= n_actual

    ions = []
    for i in np.where(summed > 0)[0]:
        ions.append((int(float(traces[i].name)), int(float(summed[i]))))

    # Normalize to base peak = 999
    if ions:
        max_int = max(i[1] for i in ions)
        if max_int > 0:
            ions = [(mz, int(i * 999 / max_int)) for mz, i in ions]

    return ions


def search_library_nist_style(observed_ions, library_entries, ri_measured=None,
                               ri_tolerance=50, min_match=600, max_results=10,
                               penalize_common=True, use_ri_prefilter=True):
    """NIST-style library search with all enhancements.

    Combines:
      1. RI pre-filtering (only search within ±ri_tolerance RI window)
      2. Common fragment penalty
      3. Base peak boosting
      4. Forward + reverse + weighted consensus scoring

    This produces match quality very close to NIST MS Search.

    Args:
        observed_ions: [(mz, intensity), ...]
        library_entries: list of library dicts with 'peaks', 'ri_exp', 'name', etc.
        ri_measured: experimental Kovats RI (optional)
        ri_tolerance: RI window for pre-filtering
        min_match: minimum match factor
        max_results: max results
        penalize_common: use common fragment penalty
        use_ri_prefilter: restrict search by RI window

    Returns:
        list of match results sorted by combined score
    """
    results = []

    # Build RI pre-filter index
    candidate_indices = list(range(len(library_entries)))

    if use_ri_prefilter and ri_measured is not None:
        ri_candidates = []
        for i in candidate_indices:
            entry_ri = library_entries[i].get('ri_exp')
            if entry_ri and abs(entry_ri - ri_measured) <= ri_tolerance:
                ri_candidates.append(i)
        if ri_candidates:
            candidate_indices = ri_candidates
        # If no RI-filtered candidates, fall back to all (don't miss the compound)

    for idx in candidate_indices:
        entry = library_entries[idx]
        ref_ions = entry.get('peaks', [])
        if not ref_ions or len(ref_ions) < 3:
            continue

        # Weighted forward match (NIST primary)
        mf_fwd = weighted_cosine_nist(observed_ions, ref_ions,
                                       penalize_common=penalize_common)

        if mf_fwd < min_match - 100:  # Coarse filter
            continue

        # Weighted reverse match
        mf_rev = weighted_cosine_nist(ref_ions, observed_ions,
                                       penalize_common=penalize_common)

        # Combined NIST-style score
        # NIST uses: combined = forward (weighted more) + reverse bonus
        if mf_fwd >= 700 and mf_rev >= 700:
            # Both good — pure spectrum match
            combined = int(mf_fwd * 0.6 + mf_rev * 0.4)
        elif mf_fwd >= 600:
            # Forward OK but reverse poor — co-elution likely
            combined = int(mf_fwd * 0.7 + min(mf_rev, 600) * 0.3)
        else:
            combined = int(min(mf_fwd, mf_rev))

        # RI bonus
        ri_score = 0
        ri_diff = None
        if ri_measured is not None and entry.get('ri_exp'):
            ri_diff = abs(ri_measured - entry['ri_exp'])
            if ri_diff < 5:
                ri_score = 200
            elif ri_diff < 15:
                ri_score = 150
            elif ri_diff < 30:
                ri_score = 100
            elif ri_diff < 50:
                ri_score = 50
            elif ri_diff < 80:
                ri_score = 10
            else:
                ri_score = -100  # Penalty for large mismatch

        combined = max(0, min(999, combined + ri_score))

        if combined >= min_match:
            results.append({
                'name': entry.get('name', ''),
                'cas': entry.get('cas', ''),
                'formula': entry.get('formula', ''),
                'match_factor': combined,
                'match_forward': mf_fwd,
                'match_reverse': mf_rev,
                'ri_score': ri_score if ri_score != 0 else 0,
                'ri_diff': round(ri_diff, 1) if ri_diff else None,
                'ri_expected': entry.get('ri_exp'),
                'source': entry.get('source', 'unknown'),
                'n_ref_peaks': len(ref_ions),
            })

    results.sort(key=lambda x: x['match_factor'], reverse=True)
    return results[:max_results]


# ----- Main search functions -----

def search_library(observed_ions, library=None, min_match=600,
                   search_mode='hybrid', tolerance=0.5,
                   ri_expected=None, ri_tolerance=50,
                   ri_boost=True, category_boost=False):
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
        category_boost: if True, boost food/flavor, penalize pharma/industrial

    Returns:
        list of dicts: [{name, cas, formula, match_factor, ri, ri_penalty, ...}]
        sorted by effective score descending (spectral match × RI × category)
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
            ri_pen = ri_consistency_penalty(lib_ri, ri_expected, ri_tolerance)

            # Category boost/penalty
            cat_factor = category_boost_factor(entry) if category_boost else 1.0

            # Effective score (spectral match × RI × category)
            effective_mf = int(mf * ri_pen * cat_factor)

            if effective_mf >= min_match or mf >= min_match:
                results.append({
                    'name': entry['name'],
                    'cas': entry.get('cas', ''),
                    'formula': entry.get('formula', ''),
                    'match_factor': mf,
                    'effective_match': effective_mf,
                    'ri': lib_ri,
                    'ri_penalty': ri_pen,
                    'category_factor': cat_factor,
                    'compound_class': entry.get('compound_class', 'other'),
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


# ================================================================
# NIST-Style Mirror Plot
# ================================================================
def mirror_plot(observed_ions, reference_ions, ref_name='Reference',
                output_path=None, title=None, figsize=(10, 6)):
    """Generate NIST-style mirror plot comparing observed vs reference spectrum.

    Reference spectrum plotted upward (positive), observed downward (negative).
    This is the standard visualization used by NIST MS Search for visual inspection
    of spectral match quality.

    Args:
        observed_ions: [(mz, intensity), ...] — experimental spectrum
        reference_ions: [(mz, intensity), ...] — library reference spectrum
        ref_name: label for the reference compound
        output_path: save path (default: output/agent_results/plots/mirror_{name}.png)
        title: plot title
        figsize: figure size in inches

    Returns:
        dict with status and file path
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    # Normalize both to base peak = 100
    ref_mz = np.array([r[0] for r in reference_ions])
    ref_int = np.array([r[1] for r in reference_ions], dtype=float)
    obs_mz = np.array([o[0] for o in observed_ions])
    obs_int = np.array([o[1] for o in observed_ions], dtype=float)

    if ref_int.max() > 0:
        ref_int = ref_int / ref_int.max() * 100
    if obs_int.max() > 0:
        obs_int = obs_int / obs_int.max() * 100

    fig, ax = plt.subplots(figsize=figsize)

    # Reference: upward stem plot
    ax.stem(ref_mz, ref_int, linefmt='#1a5276', markerfmt='none', basefmt='none')
    ax.scatter(ref_mz, ref_int, c='#1a5276', s=15, zorder=5, label=f'{ref_name} (ref)')

    # Observed: downward stem plot
    ax.stem(obs_mz, -obs_int, linefmt='#c0392b', markerfmt='none', basefmt='none')
    ax.scatter(obs_mz, -obs_int, c='#c0392b', s=15, zorder=5, label='Observed')

    # Zero line
    ax.axhline(y=0, color='black', linewidth=0.8)

    # Calculate match factor
    from public_library_manager import cosine_similarity_forward, cosine_similarity_reverse
    mf_fwd = cosine_similarity_forward(observed_ions, reference_ions)
    mf_rev = cosine_similarity_reverse(observed_ions, reference_ions)

    # Labels
    ax.set_xlabel('m/z', fontsize=12)
    ax.set_ylabel('Relative Abundance (%)', fontsize=12)
    t = title or f'Mirror Plot: {ref_name}'
    ax.set_title(f'{t}\nMatch: Fwd={mf_fwd} | Rev={mf_rev}',
                 fontsize=13, fontweight='bold')
    ax.legend(fontsize=10, loc='upper right')
    ax.set_ylim(-110, 110)
    ax.grid(True, alpha=0.2)

    # Save
    if output_path is None:
        import os
        os.makedirs('output/agent_results/plots', exist_ok=True)
        safe_name = ref_name.replace('/', '_').replace('\\', '_')[:40]
        output_path = f'output/agent_results/plots/mirror_{safe_name}.png'

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    plt.close()

    return {
        'status': 'done',
        'file': output_path,
        'match_forward': mf_fwd,
        'match_reverse': mf_rev,
        'note': f'Mirror plot saved. Forward={mf_fwd}, Reverse={mf_rev}.'
    }


# ================================================================
# Batch Parallel Search
# ================================================================
def batch_identify_unknowns(df, library_manager, data_dirs=None,
                            min_match=600, max_per_sample=20, n_workers=4):
    """Identify all unknown (RT_*) peaks across samples in parallel.

    Args:
        df: DataFrame with compound data
        library_manager: PublicLibraryManager instance
        data_dirs: dict mapping sample_name → .D directory path
        min_match: minimum match factor
        max_per_sample: max unknown peaks to search per sample
        n_workers: parallel workers

    Returns:
        list of identification results with compound, sample, match info
    """
    import numpy as np
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path

    unknowns = df[df['compound'].str.startswith('RT_', na=False)]
    if unknowns.empty:
        return []

    # Group by sample
    tasks = []
    for sample in unknowns['sample'].unique()[:8]:
        sdf = unknowns[unknowns['sample'] == sample]
        peaks = sdf[['compound', 'rt']].drop_duplicates()
        for _, row in peaks.head(max_per_sample).iterrows():
            tasks.append((sample, row['compound'], row['rt']))

    def search_one(task):
        sample, compound, rt = task
        # Find data.ms path
        d_path = None
        if data_dirs and sample in data_dirs:
            d_path = Path(data_dirs[sample])
        else:
            for pattern in [f'{sample}', f'{sample}.D']:
                for base in [Path('.'), Path('D:/Tina')]:
                    p = base / pattern
                    if (p / 'data.ms').exists():
                        d_path = p
                        break

        # Extract spectrum
        ions = []
        if d_path and (d_path / 'data.ms').exists():
            try:
                from aston.tracefile.agilent_ms import AgilentMS
                reader = AgilentMS(str(d_path / 'data.ms'))
                # Get scan at RT
                times = np.array(reader.data.traces[0].index)
                # time unit detection: if max > 100 → ms, else → min
                if times.max() > 100:
                    times = times / 60000
                scan_idx = np.argmin(np.abs(times - rt))
                # Get spectrum from CSR matrix
                V = reader.data.values
                import scipy.sparse
                row = V[scan_idx]
                if scipy.sparse.issparse(row):
                    row = row.toarray().ravel()
                traces = reader.data.traces
                for i in np.where(row > 0)[0]:
                    ions.append((float(traces[i].name), float(row[i])))
            except Exception:
                pass

        if not ions or len(ions) < 3:
            return {'compound': compound, 'sample': sample, 'rt': rt,
                    'match_factor': 0, 'best_match': None, 'error': 'no_spectrum'}

        # Search
        results = library_manager.search_by_spectrum(ions, min_match=min_match, max_results=3)
        best = results[0] if results else None

        return {
            'compound': compound, 'sample': sample, 'rt': rt,
            'match_factor': best['match_factor'] if best else 0,
            'best_match': best['name'] if best else None,
            'cas': best.get('cas', '') if best else '',
            'all_matches': results[:3],
            'n_ions': len(ions),
        }

    # Run in parallel
    results = []
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(search_one, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                results.append({'error': str(e)})

    results.sort(key=lambda x: x.get('match_factor', 0), reverse=True)
    return results
    return None
