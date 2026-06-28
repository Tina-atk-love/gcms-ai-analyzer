"""
Compound Classifier for GC-MS Spectral Library
===============================================
Classifies library compounds into categories to improve match quality:
- food_flavor: volatile aroma compounds, natural products
- pharmaceutical: drugs, drug metabolites, synthetic medicines
- industrial: solvents, polymers, industrial chemicals
- natural_product: terpenes, alkaloids, fatty acids, etc.
- other: unclassified

Used by spectral_match.py to filter/boost results by category.
"""

import re
from pathlib import Path


# ----- Name-based classification patterns -----

# Suffix patterns for common compound classes
FLAVOR_SUFFIXES = [
    'al', 'ol', 'one', 'oate', 'al$', 'oic acid',
    'ester', 'ether', 'ketone', 'aldehyde',
    'furan', 'pyran', 'lactone', 'thiol', 'thioether',
    'pyrazine', 'thiazole', 'oxazole', 'pyrrole',
    'terpene', 'phenol', 'quinone', 'ionone',
]

PHARMA_SUFFIXES = [
    'ine$', 'azole', 'avir', 'artan', 'vastatin', 'pril',
    'olol', 'dipine', 'sartan', 'cycline', 'mycin',
    'oxacin', 'bital', 'zepam', 'profen', 'vir$',
    'dronate', 'mab$', 'tinib', 'zomib', 'parib',
    'amine$', 'ium$', 'chloride', 'sulfate', 'sodium',
    'hydrochloride', 'phosphate', 'nitrate', 'citrate',
    'metabolite',
]

INDUSTRIAL_PATTERNS = [
    'silane', 'siloxane', 'phosphate', 'phosphonate',
    'polyethylene', 'polypropylene', 'polystyrene',
    'benzene, 1,', 'benzene, 1-',  # heavily substituted benzenes
    'crown-', 'peg ', 'ethoxylate',
    'isocyanate', 'epoxy', 'acrylate', 'methacrylate',
]

NATURAL_PRODUCT_PATTERNS = [
    'terpene', 'sesquiterpene', 'diterpene', 'triterpene',
    'alkaloid', 'flavonoid', 'steroid', 'carotenoid',
    'fatty acid', 'amino acid', 'sugar', 'glucose',
    'acid methyl ester', 'acid ethyl ester',
]

# Known food aroma compounds (partial list)
KNOWN_FOOD_COMPOUNDS = set([
    'hexanal', 'heptanal', 'octanal', 'nonanal', 'decanal',
    'benzaldehyde', 'phenylacetaldehyde', 'vanillin', 'ethyl vanillin',
    'acetoin', 'diacetyl', '2,3-pentanedione',
    'furfural', '5-methylfurfural', '5-hydroxymethylfurfural',
    'maltol', 'ethyl maltol', 'furaneol', 'sotolon',
    '2-acetyl-1-pyrroline', '2-acetylpyridine', '2-acetylpyrazine',
    '2-acetylthiazole', '2-acetyloxazole',
    '2-methylpyrazine', '2,5-dimethylpyrazine', '2,6-dimethylpyrazine',
    '2,3,5-trimethylpyrazine', '2-ethyl-3,5-dimethylpyrazine',
    'tetramethylpyrazine', '2,3,5,6-tetramethylpyrazine',
    'guaiacol', '4-ethylguaiacol', '4-vinylguaiacol', 'eugenol', 'isoeugenol',
    'limonene', 'alpha-pinene', 'beta-pinene', 'myrcene', 'linalool',
    'geraniol', 'nerol', 'citronellol', 'citronellal', 'camphor',
    'menthol', 'thymol', 'carvacrol', 'estragole', 'anethole',
    'ethyl acetate', 'ethyl butanoate', 'ethyl hexanoate', 'ethyl octanoate',
    'ethyl decanoate', 'isoamyl acetate', 'isobutyl acetate',
    'methyl butanoate', 'methyl hexanoate', 'methyl octanoate',
    'acetic acid', 'butanoic acid', 'hexanoic acid', 'octanoic acid',
    '3-methylbutanoic acid', '3-methylbutanal', '2-methylbutanal',
    '2-heptanone', '2-nonanone', '2-undecanone', '2-tridecanone',
    'dimethyl sulfide', 'dimethyl disulfide', 'dimethyl trisulfide',
    'methional', 'methionol',
    '2-phenylethanol', 'phenylethyl acetate', 'benzyl alcohol',
    'gamma-decalactone', 'gamma-nonalactone', 'gamma-octalactone',
    'delta-decalactone', 'delta-dodecalactone',
    'skatole', 'indole', 'cresol', '4-ethylphenol', '4-vinylphenol',
])


def classify_compound(name, formula='', cas='', num_peaks=0, mw=None):
    """Classify a compound into categories.

    Args:
        name: compound name
        formula: molecular formula (optional)
        cas: CAS number (optional)
        num_peaks: number of MS peaks (optional)
        mw: molecular weight (optional, calculated from formula if not given)

    Returns:
        dict with 'category' and 'confidence' (0.0-1.0)
    """
    if not name:
        return {'category': 'other', 'confidence': 0.0}

    name_lower = name.lower().strip()

    # Check known food compounds first
    if name_lower in KNOWN_FOOD_COMPOUNDS:
        return {'category': 'food_flavor', 'confidence': 1.0}

    scores = {'food_flavor': 0, 'pharmaceutical': 0,
              'industrial': 0, 'natural_product': 0}

    # Suffix matching
    for pat in FLAVOR_SUFFIXES:
        if re.search(pat + r'$', name_lower):
            scores['food_flavor'] += 1.5
        elif re.search(pat, name_lower):
            scores['food_flavor'] += 0.5

    for pat in PHARMA_SUFFIXES:
        if re.search(pat + r'$', name_lower):
            scores['pharmaceutical'] += 2.0
        elif re.search(pat, name_lower):
            scores['pharmaceutical'] += 1.0

    for pat in INDUSTRIAL_PATTERNS:
        if re.search(pat, name_lower):
            scores['industrial'] += 2.0

    for pat in NATURAL_PRODUCT_PATTERNS:
        if re.search(pat, name_lower):
            scores['natural_product'] += 1.0

    # Formula-based heuristics
    if formula:
        formula_upper = formula.upper()
        # Count heteroatoms
        n_count = formula_upper.count('N')
        p_count = formula_upper.count('P')
        s_count = formula_upper.count('S')
        cl_count = formula_upper.count('CL')
        br_count = formula_upper.count('BR')
        si_count = formula_upper.count('SI')

        # Nitrogen-rich → likely pharmaceutical
        if n_count >= 2:
            scores['pharmaceutical'] += n_count - 1
        # P/Cl/Br → synthetic/pharma
        if p_count > 0 or cl_count > 0 or br_count > 0:
            scores['pharmaceutical'] += 1
        # Silicon → industrial (column bleed, siloxanes)
        if si_count > 0:
            scores['industrial'] += 3
        # Sulfur → could be food (thiols, thioethers) or industrial
        if s_count > 0:
            if scores['food_flavor'] > 0:
                scores['food_flavor'] += 1
            else:
                scores['industrial'] += 0.5

    # MW heuristic (if available)
    if mw is not None:
        if mw > 500:
            # Too heavy for typical GC-MS volatiles
            scores['pharmaceutical'] += 2
            scores['food_flavor'] -= 1
        elif mw < 300:
            scores['food_flavor'] += 0.5

    # Peak count heuristic (more peaks = more complex = less likely simple flavor)
    if num_peaks > 0:
        if num_peaks < 15:
            scores['food_flavor'] += 0.3

    # Find best category
    best_cat = 'other'
    best_score = 0.5  # threshold

    for cat, score in scores.items():
        if score > best_score:
            best_score = score
            best_cat = cat

    # Confidence based on score margin
    sorted_scores = sorted(scores.values(), reverse=True)
    if len(sorted_scores) >= 2:
        margin = sorted_scores[0] - sorted_scores[1]
        confidence = min(1.0, margin / 3.0 + 0.3)
    else:
        confidence = 0.3

    return {'category': best_cat, 'confidence': confidence,
            'scores': scores}


def classify_library(library):
    """Classify all compounds in a library.

    Returns updated library with 'compound_class' and 'class_confidence' fields.
    Reports classification statistics.
    """
    counts = {}
    for entry in library:
        name = entry.get('name', '')
        formula = entry.get('formula', '')
        num_peaks = entry.get('num_peaks', 0)

        result = classify_compound(name, formula, num_peaks=num_peaks)

        entry['compound_class'] = result['category']
        entry['class_confidence'] = result['confidence']

        counts[result['category']] = counts.get(result['category'], 0) + 1

    print(f"Library classification ({len(library)} compounds):")
    for cat in sorted(counts.keys(), key=lambda c: counts[c], reverse=True):
        pct = counts[cat] / len(library) * 100
        print(f"  {cat:>20s}: {counts[cat]:>6d} ({pct:.1f}%)")

    return library


def filter_library(library, allowed_categories=None, min_confidence=0.3):
    """Filter library to only include certain compound categories.

    Args:
        library: list of library entries
        allowed_categories: set of categories to keep
        min_confidence: minimum classification confidence

    Returns filtered list.
    """
    if allowed_categories is None:
        allowed_categories = {'food_flavor', 'natural_product', 'other'}

    filtered = [e for e in library
                if e.get('compound_class', 'other') in allowed_categories
                and e.get('class_confidence', 0) >= min_confidence]

    return filtered


if __name__ == "__main__":
    # Test on library
    from public_library_manager import parse_msp_file

    lib = parse_msp_file(
        str(Path(__file__).parent / "public_libraries" / "ei_ms_with_ri.msp")
    )
    classify_library(lib)

    filtered = filter_library(lib)
    print(f"\nFiltered (food_flavor + natural_product + other): {len(filtered)} compounds")

    pharma = sum(1 for e in lib if e.get('compound_class') == 'pharmaceutical')
    industrial = sum(1 for e in lib if e.get('compound_class') == 'industrial')
    print(f"Removed: {pharma} pharmaceutical + {industrial} industrial = {pharma + industrial}")
