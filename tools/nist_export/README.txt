=================================================================
  NIST Library -> JCAMP Batch Exporter
=================================================================

  WHAT IT DOES:
    Converts your licensed NIST .L spectral library into JCAMP
    (.jdx) files that the GC-MS AI Analyzer can search.

  REQUIREMENTS:
    - Agilent MassHunter Quantitative Analysis (with NIST)
    - Your NIST library in .L format (e.g., NIST17.L folder)
    - Windows

  HOW TO USE:
    1. Edit export_nist_to_jcamp.py
       Set LIBRARY_PATH = your NIST .L folder path
       Set OUTPUT_DIR   = where to save JCAMP files

    2. Double-click run_export.bat

    3. Wait (NIST17 full library: ~15 minutes)
       You can close the window anytime.
       Re-run to resume from where it left off.

    4. Load the JCAMP folder into GC-MS AI Analyzer

  OUTPUT STRUCTURE:
    JCAMP_Export/
      00000/000000.jdx ... 009999.jdx
      10000/010000.jdx ... 019999.jdx
      20000/020000.jdx ... 029999.jdx
      ...

  LEGAL:
    This tool reads YOUR licensed NIST library on YOUR
    computer. No NIST spectra, names, or formulas are
    distributed. You must own a valid NIST license.

  TROUBLESHOOTING:
    - "Access Denied": Close MassHunter software first
    - "Library not found": Check LIBRARY_PATH has header,
      header.ind, CONDENSE files
    - Export stops early: Just re-run, it resumes

=================================================================
