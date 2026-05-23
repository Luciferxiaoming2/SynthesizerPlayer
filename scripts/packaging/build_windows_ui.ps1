param(
    [string]$Python = "D:\uv\venvs\audio_forge\Scripts\python.exe",
    [switch]$InstallPackagingDeps
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Spec = Join-Path $Root "scripts\packaging\audio_forge_ui.spec"

if ($InstallPackagingDeps) {
    & $Python -m pip install -e "${Root}[package]"
}

& $Python -m PyInstaller --clean --noconfirm $Spec

Write-Host ""
Write-Host "Built:"
Write-Host (Join-Path $Root "dist\audio-forge-ui\audio-forge-ui.exe")
