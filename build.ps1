# Local one-click build of FloatingBar.exe (alternative to the GitHub
# Actions release build). Right-click -> "Run with PowerShell", or run
# from a terminal:  powershell -ExecutionPolicy Bypass -File build.ps1
# Requires Python on PATH.

pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Host "Install failed."; exit 1 }

pyinstaller --onefile --noconsole --name FloatingBar main.py
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed."; exit 1 }

Write-Host ""
Write-Host "Done. Your exe is at: dist\FloatingBar.exe"
Write-Host "Double-click it (or pin it to Start) to run."
