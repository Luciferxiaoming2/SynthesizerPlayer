# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

ROOT = Path(SPECPATH).parents[1]


a = Analysis(
    [str(ROOT / "scripts" / "packaging" / "audio_forge_cli.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "README.md"), "."),
        (str(ROOT / "docs" / "runbooks" / "packaging_windows.md"), "docs/runbooks"),
        (
            str(ROOT / "core_engine" / "player" / "demucs_soundfile_runner.py"),
            "core_engine/player",
        ),
    ],
    hiddenimports=[
        "soundfile",
        "numpy",
        "pedalboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt6",
        "librosa",
        "pyworld",
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
    name="audio-forge-cli",
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
    name="audio-forge-cli",
)
