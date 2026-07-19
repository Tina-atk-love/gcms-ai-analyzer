@echo off
title GC-MS AI Analyzer
cd /d "%~dp0"

echo.
echo   ============================================
echo     GC-MS AI Analyzer - Starting...
echo   ============================================
echo.

:: Step 1: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python not found. Install Python 3.10+
    pause
    exit /b 1
)

:: Step 2: Start Streamlit (main app)
echo   [1/2] Starting web server...
start "GCMS-Web" /min python -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false

:: Step 3: Start NIST server (if JCAMP data exists)
if exist "C:\Users\86150\Desktop\JCAMP_Export" (
    echo   [2/2] Starting NIST spectrum server...
    start "NIST-Server" /min python tools/nist_local_server.py --nist "C:\Users\86150\Desktop\NIST17.L" --jcamp-dir "C:\Users\86150\Desktop\JCAMP_Export" --port 8765
) else (
    echo   [2/2] NIST server skipped (no JCAMP data found)
)

:: Step 4: Wait then open browser
echo.
echo   Waiting for server to start...
timeout /t 8 /nobreak >nul
start http://localhost:8501

echo.
echo   ============================================
echo     App is running at http://localhost:8501
echo     Close this window to stop all services
echo   ============================================
echo.
pause
