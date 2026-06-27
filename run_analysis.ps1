# GCMS Amino Acid Auto-Analyzer - One-Click Runner
# Run this script to analyze all .D data

$ErrorActionPreference = "Stop"

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  GCMS Amino Acid Data Auto-Analyzer" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# Find Python
$python = $null
$pythonPaths = @(
    "python",
    "python3",
    "C:\Program Files\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
)

foreach ($p in $pythonPaths) {
    try {
        $result = & $p --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $python = $p
            Write-Host "Using Python: $result" -ForegroundColor Green
            break
        }
    } catch {
        continue
    }
}

if (-not $python) {
    Write-Host "ERROR: Python not found! Please install Python 3.12+" -ForegroundColor Red
    Write-Host "Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    pause
    exit 1
}

# Check/install dependencies
Write-Host "`nChecking dependencies..." -ForegroundColor Yellow
$requirementsPath = Join-Path $PSScriptRoot "requirements.txt"
if (Test-Path $requirementsPath) {
    & $python -m pip install -r $requirementsPath --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: Some dependencies may not have installed. Continuing anyway..." -ForegroundColor Yellow
    } else {
        Write-Host "Dependencies OK" -ForegroundColor Green
    }
}

# Run analyzer
$analyzerPath = Join-Path $PSScriptRoot "gcms_analyzer.py"
Write-Host "`nRunning analysis..." -ForegroundColor Yellow
Write-Host ""

& $python $analyzerPath @args

Write-Host "`nDone! Output files are in the 'output' folder." -ForegroundColor Green
Write-Host ""

# Open output folder
$outputDir = Join-Path $PSScriptRoot "output"
if (Test-Path $outputDir) {
    Start-Process "explorer.exe" -ArgumentList $outputDir
}

pause
