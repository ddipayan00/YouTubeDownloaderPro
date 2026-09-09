# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec.

Drop an ffmpeg binary in ./bin before building and it is bundled alongside the
executable, so the app works on a machine with no ffmpeg installed.
"""

import sys
from pathlib import Path

binaries = []
bin_dir = Path("bin")
if bin_dir.is_dir():
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("ffmpeg", "ffprobe"):
        candidate = bin_dir / f"{name}{suffix}"
        if candidate.is_file():
            binaries.append((str(candidate), "bin"))

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=["yt_dlp.compat", "yt_dlp.utils", "yt_dlp.extractor"],
    hookspath=[],
    excludes=["tkinter", "matplotlib", "numpy", "PySide6.QtWebEngineCore"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="youtube-downloader-pro",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/icon.ico" if Path("assets/icon.ico").is_file() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="youtube-downloader-pro",
)
