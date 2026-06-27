"""
Read mass spectra from Agilent .D data via msconvert + pyopenms.
Provides spectrum extraction at specific retention times for library matching.
"""
import os, subprocess, tempfile, json
from pathlib import Path
import numpy as np

# Path to msconvert
MSCONVERT = Path(__file__).parent / "tools" / "msconvert.exe"


def convert_to_mzml(d_folder, output_dir=None, verbose=False):
    """Convert Agilent .D folder to mzML using msconvert (ProteoWizard).

    Args:
        d_folder: Path to .D folder (e.g., D:\\Tina\\Sample001.D)
        output_dir: Output directory for mzML file. Default: same as .D folder.

    Returns:
        Path to generated .mzML file, or None on failure.
    """
    d_path = Path(d_folder)
    if not d_path.exists():
        return None

    if output_dir is None:
        output_dir = d_path.parent
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find data.ms inside .D folder
    ms_file = d_path / "data.ms"
    if not ms_file.exists():
        return None

    # Expected output
    mzml_file = output_dir / (d_path.name.replace('.D', '') + '.mzML')

    # Skip if already converted
    if mzml_file.exists():
        return mzml_file

    # Run msconvert
    cmd = [
        str(MSCONVERT),
        str(ms_file),
        '--mzML',
        '--32',  # 32-bit precision (smaller files)
        '-o', str(output_dir),
        '--outfile', str(mzml_file.name),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if verbose and result.returncode != 0:
            print(f"msconvert stderr: {result.stderr[:500]}")
    except subprocess.TimeoutExpired:
        return None
    except FileNotFoundError:
        return None

    if mzml_file.exists():
        return mzml_file
    return None


def read_mzml_spectra(mzml_path):
    """Read all spectra from an mzML file using pyopenms.

    Returns:
        dict: {rt_min: [(mz, intensity), ...]} mapping retention times to ion lists
    """
    try:
        import pyopenms
    except ImportError:
        return None

    if not Path(mzml_path).exists():
        return None

    exp = pyopenms.MSExperiment()
    fh = pyopenms.FileHandler()

    try:
        fh.loadExperiment(str(mzml_path), exp)
    except Exception:
        return None

    spectra_by_rt = {}
    for spectrum in exp:
        if spectrum.size() == 0:
            continue
        rt = spectrum.getRT() / 60.0  # Convert seconds to minutes

        ions = []
        mzs, intensities = spectrum.get_peaks()
        for mz, intensity in zip(mzs, intensities):
            if intensity > 0:
                ions.append((float(mz), float(intensity)))

        if ions:
            # Normalize intensities
            max_int = max(i[1] for i in ions)
            ions = [(mz, int(ab / max_int * 999)) for mz, ab in ions]
            spectra_by_rt[round(rt, 4)] = ions

    return spectra_by_rt


def extract_spectra_at_peaks(mzml_path, peak_rt_list, rt_tolerance=0.05):
    """Extract mass spectra at specific retention times.

    Args:
        mzml_path: Path to mzML file
        peak_rt_list: List of retention times (in minutes)
        rt_tolerance: RT matching tolerance in minutes

    Returns:
        dict: {peak_rt: [(mz, intensity), ...]}
    """
    spectra_by_rt = read_mzml_spectra(mzml_path)
    if not spectra_by_rt:
        return {}

    result = {}
    rts = sorted(spectra_by_rt.keys())

    for target_rt in peak_rt_list:
        # Find closest spectrum
        best_rt = None
        best_diff = rt_tolerance + 1
        for rt in rts:
            diff = abs(rt - target_rt)
            if diff < best_diff:
                best_diff = diff
                best_rt = rt

        if best_rt and best_diff <= rt_tolerance:
            result[target_rt] = spectra_by_rt[best_rt]

    return result


def batch_identify_peaks(sample_dir, peak_rt_list, library=None, min_match=60):
    """Full pipeline: convert, extract spectra, identify compounds.

    Args:
        sample_dir: Path to .D folder
        peak_rt_list: List of (rt, area) tuples for peaks of interest
        library: Spectral library from spectral_library.load_library()
        min_match: Minimum match factor (0-1000)

    Returns:
        list of dicts: [{rt, area, name, cas, match_factor, formula}]
    """
    from spectral_match import identify_compound, search_library
    from spectral_library import load_library as ll

    if library is None:
        library = ll()

    # Convert to mzML
    mzml_path = convert_to_mzml(sample_dir)
    if not mzml_path:
        return None

    # Extract spectra
    rt_list = [rt for rt, area in peak_rt_list]
    spectra = extract_spectra_at_peaks(mzml_path, rt_list)

    # Identify each peak
    results = []
    for rt, area in peak_rt_list:
        if rt in spectra:
            match = identify_compound(spectra[rt], library, min_match)
            if match:
                results.append({
                    'rt': rt,
                    'area': area,
                    'name': match['name'],
                    'cas': match.get('cas', ''),
                    'formula': match.get('formula', ''),
                    'match_factor': match['match_factor'],
                })
            else:
                # No good match — still include peak info
                results.append({
                    'rt': rt,
                    'area': area,
                    'name': None,
                    'match_factor': 0,
                })
        else:
            results.append({
                'rt': rt,
                'area': area,
                'name': None,
                'match_factor': -1,  # -1 = no spectrum available
            })

    return results
