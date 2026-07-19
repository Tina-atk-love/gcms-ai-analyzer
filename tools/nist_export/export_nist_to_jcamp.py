# -*- coding: utf-8 -*-
# ============================================================================
#  NIST Library -> JCAMP Batch Exporter
#  ===========================================================================
#  Converts YOUR licensed NIST .L library to JCAMP files for use with
#  the GC-MS AI Analyzer spectral search engine.
#
#  HOW TO USE:
#    1. Edit LIBRARY_PATH and OUTPUT_DIR below to match your system
#    2. Double-click run_export.bat
#    3. Wait ~15 minutes for full NIST17 library (306K spectra)
#    4. Output goes to OUTPUT_DIR (subdirectories, 10K files each)
#
#  SUPPORTS RESUME: Re-run anytime - already-exported files are skipped.
#
#  REQUIREMENTS:
#    - Agilent MassHunter Quantitative Analysis (any version with NIST)
#    - NIST library in .L format
#    - Windows (IronPython engine built into MassHunter)
#
#  LEGAL: This script reads YOUR licensed NIST library on YOUR computer.
#         No NIST data is distributed. You must own a valid NIST license.
# ============================================================================

import clr, sys, time
sys.path.append(r"C:\Program Files\Agilent\MassHunter\Workstation\Quant\bin")
clr.AddReference("CoreLibraryAccess")

from Agilent.MassSpectrometry.DataAnalysis import *
from System import Array, Double, Int32
from System.IO import Directory, File, Path

# ======================================================================
#  CONFIGURATION - Edit these paths for your system
# ======================================================================
LIBRARY_PATH = r"<YOUR_NIST_L_FOLDER>"    # Your NIST .L folder (e.g. D:\NIST17.L)
OUTPUT_DIR   = r"<YOUR_OUTPUT_FOLDER>"   # Where JCAMP files go (e.g. D:\JCAMP_Export)
# ======================================================================

START_INDEX = 0
MAX_EXPORT  = 0   # 0 = export all compounds

# ======================================================================
if not Directory.Exists(OUTPUT_DIR):
    Directory.CreateDirectory(OUTPUT_DIR)

print "=" * 55
print "  NIST Library -> JCAMP Batch Export"
print "  Library :", LIBRARY_PATH
print "  Output  :", OUTPUT_DIR
print "=" * 55

lib = MSLibraryIO()
lib.Open(LIBRARY_PATH, True, True)

total = lib.GetLibEntryCount()
print "  Total entries:", total

end_index = total if MAX_EXPORT == 0 else min(START_INDEX + MAX_EXPORT, total)
print "  Range: %d -> %d" % (START_INDEX, end_index)
print "=" * 55

exported = 0
errors = 0
t0 = time.time()

for i in range(START_INDEX, end_index):
    entry_num = i + 1   # NIST uses 1-based indexing

    # Subdirectory: 00000/, 10000/, 20000/, ...
    subdir_name = "%05d" % ((i // 10000) * 10000)
    subdir = Path.Combine(OUTPUT_DIR, subdir_name)
    if not Directory.Exists(subdir):
        Directory.CreateDirectory(subdir)

    filepath = Path.Combine(subdir, "%06d.jdx" % i)
    if File.Exists(filepath):
        continue

    try:
        header = lib.GetLibEntryHeader(entry_num)
        name = header.Name or "Unknown"
        formula = header.Formula or ""
        cas_int = header.CASNumber

        mz_ref = clr.Reference[Array[Double]]()
        int_ref = clr.Reference[Array[Double]]()

        try:
            lib.GetSpectrumByEntry(entry_num, mz_ref, int_ref)
            mz = mz_ref.Value
            intensity = int_ref.Value
        except:
            ua_ref = clr.Reference[Array[Double]]()
            lib.GetSpectrumByEntry(entry_num, mz_ref, int_ref, ua_ref)
            mz = mz_ref.Value
            intensity = int_ref.Value

        if mz is None or len(mz) < 3:
            errors += 1
            continue

        max_int = max(intensity)
        if max_int <= 0:
            errors += 1
            continue

        with open(filepath, 'w') as f:
            f.write("##TITLE=%s\n" % name)
            f.write("##JCAMP-DX=4.24\n")
            f.write("##DATA TYPE=MASS SPECTRUM\n")
            f.write("##ORIGIN=NIST Library (user-licensed)\n")
            if formula:
                f.write("##MOLFORM=%s\n" % formula)
            if cas_int and cas_int > 0:
                c = cas_int % 10
                b = (cas_int // 10) % 100
                a = cas_int // 1000
                f.write("##CAS REGISTRY NUMBER=%d-%02d-%d\n" % (a, b, c))
            f.write("##XUNITS=M/Z\n##YUNITS=RELATIVE INTENSITY\n")
            f.write("##NPOINTS=%d\n" % len(mz))
            f.write("##PEAK TABLE=(XY..XY)\n")
            for j in range(0, len(mz), 8):
                chunk = []
                for k in range(j, min(j+8, len(mz))):
                    chunk.append("%d,%d" % (int(mz[k]), int(intensity[k] * 999.0 / max_int)))
                f.write(" ".join(chunk) + "\n")
            f.write("##END=\n")

        exported += 1

    except Exception as e:
        errors += 1
        if errors <= 5:
            print "  Error at #%d: %s" % (i, str(e)[:80])

    if (i + 1) % 1000 == 0:
        elapsed = time.time() - t0
        rate = (i + 1 - START_INDEX) / max(elapsed, 0.001)
        eta_min = (end_index - i - 1) / max(rate, 0.001) / 60.0
        print "  [%d/%d]  ok:%d  err:%d  %.0f/s  ETA:%.0fmin" % (
            i+1, total, exported, errors, rate, eta_min)

elapsed = time.time() - t0
print "=" * 55
print "  Done in %.1f min" % (elapsed / 60.0)
print "  Exported: %d" % exported
print "  Errors:   %d" % errors
print "  Output:   %s" % OUTPUT_DIR
print "=" * 55

lib.Close()
