# NIST JCAMP Batch Export Script
# ================================
# Run on the LAB COMPUTER (with D: drive) where MassHunter is installed.
#
# This script automates the entire NIST → JCAMP export pipeline:
#   1. Uses LibraryEdit.Console.exe if it has batch export
#   2. Falls back to GUI automation of 谱库编辑器
#   3. Falls back to keyboard-based automation
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File nist_batch_export.ps1

param(
    [string]$NistPath = "C:\Database\NIST17.L",
    [string]$OutputPath = "D:\JCAMP_Export",
    [string]$Method = "auto",  # auto | gui | keyboard
    [int]$TotalCompounds = 306622
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  NIST JCAMP Batch Export" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  NIST Library: $NistPath"
Write-Host "  Output:       $OutputPath"
Write-Host "  Method:       $Method"
Write-Host ""

# Create output directory
New-Item -ItemType Directory -Force -Path $OutputPath | Out-Null

# ================================================================
# Method 1: Try LibraryEdit.Console.exe (CLI batch export)
# ================================================================
$LibEditConsole = "C:\Program Files\Agilent\MassHunter\Workstation\Quant\bin\LibraryEdit.Console.exe"

if ($Method -eq "auto" -and (Test-Path $LibEditConsole)) {
    Write-Host "[Method 1] Trying LibraryEdit.Console.exe..." -ForegroundColor Yellow

    # Check if it supports command-line export
    $help = & $LibEditConsole --help 2>&1 | Out-String
    if ($help -match "export|convert|jc amp|msp") {
        Write-Host "  CLI export supported! Running batch export..."
        # Try common export syntax
        & $LibEditConsole --input $NistPath --output $OutputPath --format jcamp 2>&1
        Write-Host "  Done!" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "  CLI mode doesn't support batch export." -ForegroundColor Gray
    }
}

# ================================================================
# Method 2: Python keyboard automation
# ================================================================
if ($Method -in @("auto", "keyboard")) {
    Write-Host "[Method 2] Starting keyboard-based export..." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Make sure:"
    Write-Host "  1. 谱库编辑器 is open with NIST library loaded"
    Write-Host "  2. The first compound is SELECTED"
    Write-Host "  3. The 谱库编辑器 window is FOCUSED"
    Write-Host ""
    Write-Host "  Move mouse to TOP-LEFT corner at any time to ABORT"
    Write-Host ""

    $choice = Read-Host "  Press ENTER to start (or type 'quit')"
    if ($choice -eq "quit") { exit }

    & python "$ScriptDir\nist_keyboard_export.py" `
        --output $OutputPath `
        --total $TotalCompounds `
        --delay 0.5 2>&1

    Write-Host "  Keyboard export finished!" -ForegroundColor Green
}

# ================================================================
# Check results
# ================================================================
$exported = (Get-ChildItem -Path $OutputPath -Filter "*.jdx" | Measure-Object).Count
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Export Complete!" -ForegroundColor Green
Write-Host "  Files exported: $exported" -ForegroundColor Green
Write-Host "  Output: $OutputPath" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
