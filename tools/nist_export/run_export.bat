@echo off
title NIST to JCAMP Export
echo ==============================================
echo   NIST Library -> JCAMP Batch Exporter
echo ==============================================
echo.
echo   This tool reads YOUR licensed NIST library
echo   and exports all spectra as JCAMP files.
echo.
echo   No NIST data is distributed - everything
echo   runs on your computer.
echo.
echo   Supports resume: close and re-run anytime.
echo ==============================================
echo.

"C:\Program Files\Agilent\MassHunter\Workstation\Quant\bin\LibraryEdit.Console.exe" -script="%~dp0export_nist_to_jcamp.py"

echo.
echo Done. JCAMP files are in the output folder.
echo You can now load them into GC-MS AI Analyzer.
pause
