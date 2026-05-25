# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import importlib.util

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parents[1]


def collect_optional_package(package_name):
    if importlib.util.find_spec(package_name) is None:
        return [], [], []
    return collect_data_files(package_name), collect_dynamic_libs(package_name), [package_name]


optional_datas = []
optional_binaries = []
optional_hiddenimports = []
for package in [
    "faster_whisper",
    "ctranslate2",
    "av",
    "tokenizers",
    "onnxruntime",
    "huggingface_hub",
    "tqdm",
]:
    datas, binaries, hiddenimports = collect_optional_package(package)
    optional_datas += datas
    optional_binaries += binaries
    optional_hiddenimports += hiddenimports

local_model_datas = []
for model_name in ["small", "base"]:
    local_asr_model = ROOT / "plugins" / "models" / "faster-whisper" / model_name
    if (local_asr_model / "model.bin").exists():
        local_model_datas.append((str(local_asr_model), f"plugins/models/faster-whisper/{model_name}"))

rubberband_dir = ROOT / "plugins" / "models" / "rubberband"
if (rubberband_dir / "rubberband.exe").exists():
    local_model_datas.append((str(rubberband_dir), "plugins/models/rubberband"))


a = Analysis(
    [str(ROOT / "ui" / "main_window.py")],
    pathex=[str(ROOT)],
    binaries=optional_binaries,
    datas=[
        (str(ROOT / "ui" / "qml"), "ui/qml"),
        (str(ROOT / "README.md"), "."),
        (str(ROOT / "docs" / "runbooks" / "packaging_windows.md"), "docs/runbooks"),
        (
            str(ROOT / "core_engine" / "player" / "demucs_soundfile_runner.py"),
            "core_engine/player",
        ),
    ] + optional_datas + local_model_datas,
    hiddenimports=[
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "soundfile",
        "sounddevice",
        "numpy",
        "pedalboard",
    ] + optional_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "librosa",
        "pyworld",
        "torch",
        "torchaudio",
        "torchvision",
        "scipy",
        "numba",
        "llvmlite",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="audio-forge-ui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="audio-forge-ui",
)
