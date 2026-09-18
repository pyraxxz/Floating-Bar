# Local one-click build of FloatingBar.exe (alternative to the GitHub
# Actions release build). Right-click -> "Run with PowerShell", or run
# from a terminal:  powershell -ExecutionPolicy Bypass -File build.ps1
# Requires Python on PATH.

pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Host "Install failed."; exit 1 }

pyinstaller --onefile --noconsole --name FloatingBar main.py
if ($LASTEXITCODE -ne 0) { Write-Host "Build failed."; exit 1 }

Copy-Item -LiteralPath installer\Install-FloatingBar.ps1 -Destination dist\Install-FloatingBar.ps1 -Force
Copy-Item -LiteralPath installer\Uninstall-FloatingBar.ps1 -Destination dist\Uninstall-FloatingBar.ps1 -Force

Write-Host ""
Write-Host "Done. Your exe is at: dist\FloatingBar.exe"
Write-Host "Installer: dist\Install-FloatingBar.ps1"
Write-Host "Uninstaller: dist\Uninstall-FloatingBar.ps1"
