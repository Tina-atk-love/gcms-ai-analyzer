@echo off
title GC-MS AI Analyzer
echo ============================================
echo   GC-MS AI Analyzer - Starting...
echo ============================================
echo.
echo   Opening http://localhost:8501
echo   Press Ctrl+C to stop
echo.
cd /d "%~dp0"
pip install -r requirements.txt -q 2>nul
streamlit run app.py --server.port 8501 --server.headless true
pause
