@echo off
chcp 65001 >nul
title GC-MS AI Analyzer
color 1F

echo.
echo   ╔══════════════════════════════════════════╗
echo   ║     🧬  GC-MS AI Analyzer  v3.5         ║
echo   ║     Open-Source NIST Alternative          ║
echo   ╚══════════════════════════════════════════╝
echo.
echo   Starting... Please wait.
echo.

cd /d "%~dp0"

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python not found!
    echo   Please install Python 3.10+ from https://python.org
    echo   Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Install dependencies (quiet, only if needed)
echo   [1/2] Checking dependencies...
pip install -r requirements.txt -q 2>nul
if %errorlevel% neq 0 (
    echo   [WARN] Some dependencies failed to install. Trying without cache...
    pip install -r requirements.txt --no-cache-dir -q 2>nul
)

:: Start app
echo   [2/2] Starting web server...
echo.
echo   ╔══════════════════════════════════════════╗
echo   ║  Opening http://localhost:8501             ║
echo   ║  Press Ctrl+C in this window to stop       ║
echo   ╚══════════════════════════════════════════╝
echo.
timeout /t 2 /nobreak >nul
start http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false --theme.primaryColor "#1a5276"

echo.
echo   App stopped.
pause
