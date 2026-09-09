#!/usr/bin/env python3
"""Run the packaged app's --self-test and fail loudly if it does not start.

A green PyInstaller run only proves the build succeeded, not that the result
launches or can find its bundled ffmpeg. This locates whatever the current
platform produced under dist/ and actually executes it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DIST = Path("dist")


def locate() -> Path | None:
    """Find the built executable for this platform."""
    candidates = [
        # macOS .app bundle
        DIST / "YouTube Downloader Pro.app/Contents/MacOS/YouTube Downloader Pro",
        # Windows
        DIST / "youtube-downloader-pro/youtube-downloader-pro.exe",
        # Linux / macOS onedir
        DIST / "youtube-downloader-pro/youtube-downloader-pro",
        DIST / "YouTube Downloader Pro/YouTube Downloader Pro",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    executable = locate()
    if executable is None:
        print("No built executable found under dist/:", file=sys.stderr)
        for path in sorted(DIST.rglob("*"))[:40]:
            print(f"  {path}", file=sys.stderr)
        return 1

    print(f"Smoke-testing {executable}")
    try:
        result = subprocess.run(
            [str(executable), "--self-test"],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        print("The app did not exit within 180s.", file=sys.stderr)
        return 1

    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        print(f"Self-test failed with exit code {result.returncode}.", file=sys.stderr)
        return result.returncode

    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"Bundle size: {size / 1_048_576:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
