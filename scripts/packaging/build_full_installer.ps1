param(
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Script = Join-Path $Root "scripts\packaging\audio_forge_full_setup.iss"
$ReleaseDir = Join-Path $Root "release\AudioForgePortable_next"
$Exe = Join-Path $ReleaseDir "audio-forge-ui.exe"

if (!(Test-Path $Exe)) {
    throw "Main executable not found: $Exe. Build the UI package first."
}

if (!$InnoCompiler) {
    $command = Get-Command iscc.exe -ErrorAction SilentlyContinue
    if ($command) {
        $InnoCompiler = $command.Source
    }
}

if (!$InnoCompiler -or !(Test-Path $InnoCompiler)) {
    throw "Inno Setup compiler ISCC.exe was not found. Install Inno Setup and run this script again."
}

& $InnoCompiler $Script

Write-Host "Full installer generated:"
Write-Host (Join-Path $Root "release\AudioForge_Full_Setup.exe")
