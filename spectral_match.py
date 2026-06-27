"""
Spectral matching engine: cosine similarity NIST-style library search
Compares experimental mass spectra against MSP spectral library.
"""
import numpy as np
from spectral_library import load_library


def cosine_similarity(observed_ions, reference_ions, tolerance=0.5):
    """Compute weighted cosine similarity between two mass spectra.

    Args:
        observed_ions: list of (mz, intensity) tuples
        reference_ions: list of (mz, intensity) tuples
        tolerance: m/z tolerance for matching ions (default 0.5 Da for unit mass)

    Returns:
        float: match score 0-999 (NIST-style, higher = better)
    """
    if not observed_ions or not reference_ions:
        return 0

    # Build intensity vectors aligned by m/z
    # Use weighted matching: each reference ion matches the closest observed ion
    score = 0.0
    total_ref = sum(r[1]**2 for r in reference_ions)
    total_obs = sum(o[1]**2 for o in observed_ions)

    if total_ref == 0 or total_obs == 0:
        return 0

    # For each reference ion, find the closest observed ion
    obs_mz = np.array([o[0] for o in observed_ions])
    obs_int = np.array([o[1] for o in observed_ions])

    ref_intensity_weighted = 0
    for ref_mz, ref_int in reference_ions:
        # Find closest observed ion
        diffs = np.abs(obs_mz - ref_mz)
        best_idx = np.argmin(diffs)
        if diffs[best_idx] <= tolerance:
            ref_intensity_weighted += ref_int * obs_int[best_idx]

    # Cosine similarity
    if total_ref > 0:
        cosine = ref_intensity_weighted / np.sqrt(total_ref * total_obs)
    else:
        cosine = 0

    # Scale to 0-999 (NIST-style match factor)
    match_factor = int(cosine * 999)
    return min(999, max(0, match_factor))


def search_library(observed_ions, library=None, min_match=0):
    """Search observed mass spectrum against spectral library.

    Args:
        observed_ions: list of (mz, intensity) tuples
        library: list of library entries (from spectral_library.load_library())
        min_match: minimum match factor to include in results

    Returns:
        list of dicts: [{name, cas, match_factor, formula}], sorted by match desc
    """
    if library is None:
        library = load_library()

    results = []
    for entry in library:
        if 'peaks' not in entry:
            continue
        mf = cosine_similarity(observed_ions, entry['peaks'])
        if mf >= min_match:
            results.append({
                'name': entry['name'],
                'cas': entry.get('cas', ''),
                'formula': entry.get('formula', ''),
                'match_factor': mf,
            })

    results.sort(key=lambda x: x['match_factor'], reverse=True)
    return results


def identify_compound(observed_ions, library=None, min_match=60):
    """Identify a single compound from its mass spectrum.

    Returns best match or None.
    """
    results = search_library(observed_ions, library, min_match)
    if results:
        return results[0]
    return None
