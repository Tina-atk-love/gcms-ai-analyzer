# GC-MS AI Analyzer — One-Click Installer
# Run: powershell -ExecutionPolicy Bypass -File install.ps1
# Creates desktop shortcut + Start Menu entry

$ErrorActionPreference = "Stop"
$AppName = "GC-MS AI Analyzer"
$InstallDir = "$env:LOCALAPPDATA\$AppName"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║  🧬  GC-MS AI Analyzer — Installer        ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Copy files
Write-Host "  [1/3] Installing to $InstallDir..."
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force "$SourceDir\*" "$InstallDir\"

# Create launcher
$LauncherPath = "$InstallDir\launch.bat"
@"
@echo off
title GC-MS AI Analyzer
cd /d "$InstallDir"
start http://localhost:8501
call run_web.bat
"@ | Out-File -FilePath $LauncherPath -Encoding ASCII

# Shortcuts
Write-Host "  [2/3] Creating shortcuts..."
$WshShell = New-Object -ComObject WScript.Shell

# Desktop
$DesktopShortcut = "$env:USERPROFILE\Desktop\$AppName.lnk"
$Shortcut = $WshShell.CreateShortcut($DesktopShortcut)
$Shortcut.TargetPath = "cmd.exe"
$Shortcut.Arguments = "/c `"$LauncherPath`""
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.IconLocation = "C:\Windows\System32\imageres.dll,102"
$Shortcut.Save()
Write-Host "    Desktop shortcut created"

# Start Menu
$StartMenuDir = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\$AppName"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null
$StartShortcut = $WshShell.CreateShortcut("$StartMenuDir\$AppName.lnk")
$StartShortcut.TargetPath = "cmd.exe"
$StartShortcut.Arguments = "/c `"$LauncherPath`""
$StartShortcut.WorkingDirectory = $InstallDir
$StartShortcut.IconLocation = "C:\Windows\System32\imageres.dll,102"
$StartShortcut.Save()
Write-Host "    Start Menu entry created"

Write-Host "  [3/3] Starting app..."
Start-Process "http://localhost:8501"
Start-Process cmd.exe -ArgumentList "/c `"$LauncherPath`"" -WindowStyle Minimized

Write-Host ""
Write-Host "  ✅ Installation complete!" -ForegroundColor Green
Write-Host "  🚀 App opening at http://localhost:8501" -ForegroundColor Green
Write-Host ""
