[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$SourceExe,

    [string]$InstallDirectory = $(Join-Path $env:LOCALAPPDATA "FloatingBar"),

    [switch]$CreateStartMenuShortcut
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $SourceExe -PathType Leaf)) {
    throw "Source executable was not found: $SourceExe"
}

$resolvedSource = (Resolve-Path -LiteralPath $SourceExe).Path
$destination = Join-Path $InstallDirectory "FloatingBar.exe"
$installedUninstaller = Join-Path $InstallDirectory "Uninstall-FloatingBar.ps1"
$bundledUninstaller = Join-Path $PSScriptRoot "Uninstall-FloatingBar.ps1"

$running = Get-Process -Name "FloatingBar" -ErrorAction SilentlyContinue
if ($null -ne $running) {
    throw "Floating Bar is running. Close it before installing or upgrading."
}

New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null

$tempDestination = "$destination.new"
try {
    Copy-Item -LiteralPath $resolvedSource -Destination $tempDestination -Force
    Move-Item -LiteralPath $tempDestination -Destination $destination -Force
}
finally {
    if (Test-Path -LiteralPath $tempDestination) {
        Remove-Item -LiteralPath $tempDestination -Force -ErrorAction SilentlyContinue
    }
}

if ($CreateStartMenuShortcut) {
    $startMenu = Join-Path $env:APPDATA "MicrosoftWindowsStart MenuPrograms"
    New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
    $shortcutPath = Join-Path $startMenu "Floating Bar.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $destination
    $shortcut.WorkingDirectory = $InstallDirectory
    $shortcut.Description = "Floating Bar"
    $shortcut.Save()
}

if (Test-Path -LiteralPath $bundledUninstaller -PathType Leaf) {
    Copy-Item -LiteralPath $bundledUninstaller -Destination $installedUninstaller -Force
    Write-Host "Installed uninstaller: $installedUninstaller"
}

Write-Host "Floating Bar installed at $destination"
Write-Host "Existing settings and quick replies under %APPDATA%\FloatingBar are preserved."
