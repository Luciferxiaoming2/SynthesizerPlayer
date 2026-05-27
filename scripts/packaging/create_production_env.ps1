param(
    [string]$Target = "release\AudioForgePortable_next\plugins\models\python",
    [string]$Python = "3.11",
    [switch]$WithDemucs = $true
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$TargetPath = Join-Path $Root $Target
$PortableRoot = Join-Path $Root "release\AudioForgePortable_next"
$DemucsConfig = Join-Path $PortableRoot "demucs_python.txt"

$env:UV_CACHE_DIR = Join-Path $Root ".uv-cache"

if (!(Test-Path $TargetPath)) {
    uv venv $TargetPath --python $Python
}

$ProductionPython = Join-Path $TargetPath "Scripts\python.exe"
if (!(Test-Path $ProductionPython)) {
    throw "未找到生产环境 Python：$ProductionPython"
}

$packages = @("-e", ".[asr,f0]")
if ($WithDemucs) {
    $packages += "demucs"
}

uv pip install --python $ProductionPython @packages

New-Item -ItemType Directory -Force -Path $PortableRoot | Out-Null
Set-Content -Path $DemucsConfig -Value "plugins\models\python\Scripts\python.exe" -Encoding UTF8

Write-Host "生产环境已准备完成：$TargetPath"
Write-Host "Demucs Python 配置：$DemucsConfig"
