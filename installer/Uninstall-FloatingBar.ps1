[CmdletBinding()]
param(
    [string]$InstallDirectory = $(Join-Path $env:LOCALAPPDATA "FloatingBar"),
    [switch]$RemoveSettings
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$running = Get-Process -Name "FloatingBar" -ErrorAction SilentlyContinue
if ($null -ne $running) {
    throw "Floating Bar is running. Close it before uninstalling."
}

$shortcutPath = Join-Path $env:APPDATA "MicrosoftWindowsStart MenuProgramsFloating Bar.lnk"
if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
}

$exePath = Join-Path $InstallDirectory "FloatingBar.exe"
if (Test-Path -LiteralPath $exePath) {
    Remove-Item -LiteralPath $exePath -Force
}

if (Test-Path -LiteralPath $InstallDirectory -PathType Container) {
    $remaining = Get-ChildItem -LiteralPath $InstallDirectory -Force -ErrorAction SilentlyContinue
    if ($null -eq $remaining) {
        Remove-Item -LiteralPath $InstallDirectory -Force
    }
}

if ($RemoveSettings) {
    $settingsDirectory = Join-Path $env:APPDATA "FloatingBar"
    if (Test-Path -LiteralPath $settingsDirectory -PathType Container) {
        Remove-Item -LiteralPath $settingsDirectory -Recurse -Force
    }
    Write-Host "Removed user settings and quick replies under %APPDATA%\FloatingBar."
}
else {
    Write-Host "Preserved user settings and quick replies under %APPDATA%\FloatingBar."
}

Write-Host "Floating Bar uninstalled."
