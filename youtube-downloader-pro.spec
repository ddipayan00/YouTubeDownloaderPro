# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec — produces a native app for whichever OS runs it.

PyInstaller does not cross-compile: run this on Windows for a .exe, on macOS
for a .app, on Linux for an ELF binary. See .github/workflows/build.yml for the
CI matrix that builds all three, and tools/fetch_ffmpeg.py to populate ./bin.

Anything in ./bin (ffmpeg, ffprobe) is bundled so the app works on a machine
with no ffmpeg installed.
"""

import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

APP_NAME = "YouTube Downloader Pro" if IS_MACOS else "youtube-downloader-pro"
BUNDLE_ID = "com.ddipayan00.youtubedownloaderpro"

# ---------------------------------------------------------------- ffmpeg ----
# Collected into "bin" so it sits next to the app's other internals; the
# runtime looks in sys._MEIPASS/bin, beside the executable, and in
# Contents/Resources/bin, so every layout below is covered.
binaries = []
bin_dir = Path("bin")
if bin_dir.is_dir():
    suffix = ".exe" if IS_WINDOWS else ""
    for name in ("ffmpeg", "ffprobe"):
        candidate = bin_dir / f"{name}{suffix}"
        if candidate.is_file():
            binaries.append((str(candidate), "bin"))

# ------------------------------------------------------------------ icon ----
# Each platform wants its own format; a missing file just means no custom icon.
icon_candidates = {
    "win32": "assets/icon.ico",
    "darwin": "assets/icon.icns",
}
icon_path = icon_candidates.get(sys.platform)
icon = icon_path if icon_path and Path(icon_path).is_file() else None

# --------------------------------------------------------------- excludes ----
# The UI is plain QtWidgets: Qml/Quick, 3D, multimedia and friends are never
# imported, and dropping them takes a large bite out of the bundle.
EXCLUDES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "PIL",
    "pytest",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
]

# Listing these under `excludes` is not enough: PyInstaller pulls the Qml/Quick
# libraries in as binary dependencies of Qt *plugins*, not as Python imports.
# They have to be filtered out of the collected trees after analysis.
#
# The virtual-keyboard plugin is what drags QML into a plain QtWidgets app, so
# it goes too — but the ibus/fcitx input-method plugins stay, or users typing
# non-Latin scripts lose their input method.
UNWANTED_BINARIES = (
    "qt6qml",
    "qt6quick",
    "qt6pdf",
    "qt6virtualkeyboard",
    "qtqml",
    "qtquick",
    "qtpdf",
    "qtvirtualkeyboard",
)
UNWANTED_DATA_DIRS = ("pyside6/qt/qml", "pyside6/qt6/qml", "qt/qml")


def _drop_unwanted(entries, patterns, directories=()):
    kept = []
    for entry in entries:
        dest = str(entry[0]).replace("\\", "/").lower()
        name = dest.rsplit("/", 1)[-1]
        if any(pattern in name for pattern in patterns):
            continue
        if directories and any(d in dest for d in directories):
            continue
        kept.append(entry)
    return kept


a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=["yt_dlp.compat", "yt_dlp.utils", "yt_dlp.extractor"],
    hookspath=[],
    excludes=EXCLUDES,
    noarchive=False,
)
a.binaries = _drop_unwanted(a.binaries, UNWANTED_BINARIES)
a.datas = _drop_unwanted(a.datas, UNWANTED_BINARIES, UNWANTED_DATA_DIRS)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    # UPX is off deliberately: it trips Windows SmartScreen/AV heuristics and
    # invalidates macOS code signatures, for a saving that is not worth either.
    upx=False,
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

# macOS gets a real .app bundle rather than a bare Unix executable.
if IS_MACOS:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon,
        bundle_identifier=BUNDLE_ID,
        info_plist={
            "CFBundleShortVersionString": "2.0.0",
            "CFBundleVersion": "2.0.0",
            "NSHighResolutionCapable": True,
            # Qt apps must not be treated as a background agent.
            "LSBackgroundOnly": False,
            "LSMinimumSystemVersion": "11.0",
        },
    )
