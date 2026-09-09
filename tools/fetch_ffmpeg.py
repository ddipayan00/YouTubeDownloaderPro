#!/usr/bin/env python3
"""Download a static ffmpeg/ffprobe into ./bin for the current platform.

The build spec bundles whatever it finds in ./bin, so run this before
PyInstaller if you want a self-contained app. ./bin is gitignored, which is why
CI calls this rather than committing 150 MB of binaries.

Static builds are used on purpose: a package-manager ffmpeg is dynamically
linked against that machine's libraries and will not run on a user's machine.

    python tools/fetch_ffmpeg.py            # into ./bin
    python tools/fetch_ffmpeg.py --dest x   # somewhere else
    python tools/fetch_ffmpeg.py --force    # re-download

Only the Linux path has been exercised on this machine; the Windows and macOS
sources are the standard community builds that CI pulls.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

WANTED = ("ffmpeg", "ffprobe")

# One or more archives per platform; each is searched for the wanted binaries.
SOURCES: dict[tuple[str, str], tuple[str, ...]] = {
    ("Linux", "x86_64"): (
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    ),
    ("Linux", "aarch64"): (
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz",
    ),
    ("Windows", "AMD64"): (
        "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
        "ffmpeg-master-latest-win64-gpl.zip",
    ),
    ("Darwin", "x86_64"): (
        "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
        "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
    ),
    ("Darwin", "arm64"): ("https://www.osxexperts.net/ffmpeg711arm.zip",),
}


def platform_key() -> tuple[str, str]:
    system, machine = platform.system(), platform.machine()
    # Normalise the aliases the same CPU reports under different OSes.
    if system == "Linux" and machine in ("arm64", "armv8l"):
        machine = "aarch64"
    if system == "Darwin" and machine == "aarch64":
        machine = "arm64"
    if system == "Windows" and machine in ("x86_64", "amd64"):
        machine = "AMD64"
    return system, machine


def download(url: str, target: Path, *, attempts: int = 3) -> None:
    print(f"  downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ytdpro-build"})
    for attempt in range(1, attempts + 1):
        with urllib.request.urlopen(request, timeout=180) as response, target.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        size = target.stat().st_size
        if size > 0:
            print(f"  got {size / 1_048_576:.1f} MB")
            return
        if attempt < attempts:
            print(f"  got an empty response, retrying ({attempt}/{attempts})...")
            time.sleep(5 * attempt)
    raise RuntimeError(f"{url} kept returning an empty response after {attempts} attempts.")


def _wanted_name(member_name: str, is_windows: bool) -> str | None:
    """Return the destination filename if this archive member is one we want."""
    base = Path(member_name).name
    for name in WANTED:
        expected = f"{name}.exe" if is_windows else name
        if base == expected:
            return expected
    return None


def extract(archive: Path, dest: Path, is_windows: bool) -> list[str]:
    found: list[str] = []
    if archive.suffix == ".zip" or zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                name = _wanted_name(member, is_windows)
                if not name or member.endswith("/"):
                    continue
                with zf.open(member) as src, (dest / name).open("wb") as out:
                    shutil.copyfileobj(src, out)
                found.append(name)
    else:
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                name = _wanted_name(member.name, is_windows)
                if not name or not member.isfile():
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                with src, (dest / name).open("wb") as out:
                    shutil.copyfileobj(src, out)
                found.append(name)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", default="bin", help="where to put the binaries (default: bin)")
    parser.add_argument("--force", action="store_true", help="re-download even if present")
    args = parser.parse_args()

    key = platform_key()
    urls = SOURCES.get(key)
    if not urls:
        print(f"No static ffmpeg source configured for {key[0]}/{key[1]}.", file=sys.stderr)
        print("Install ffmpeg yourself and copy ffmpeg/ffprobe into ./bin.", file=sys.stderr)
        return 1

    is_windows = key[0] == "Windows"
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    suffix = ".exe" if is_windows else ""
    if not args.force and all((dest / f"{n}{suffix}").is_file() for n in WANTED):
        print(f"ffmpeg and ffprobe are already in {dest}/ — use --force to replace them.")
        return 0

    print(f"Fetching ffmpeg for {key[0]}/{key[1]} into {dest}/")
    collected: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, url in enumerate(urls):
            archive = Path(tmp) / f"ffmpeg-{index}{'.zip' if 'zip' in url else '.tar.xz'}"
            download(url, archive)
            collected += extract(archive, dest, is_windows)

    if not collected:
        print("Archive did not contain ffmpeg/ffprobe.", file=sys.stderr)
        return 1

    for name in set(collected):
        target = dest / name
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  {target}  ({target.stat().st_size / 1_048_576:.1f} MB)")

    missing = [n for n in WANTED if not (dest / f"{n}{suffix}").is_file()]
    if missing:
        print(f"Warning: {', '.join(missing)} not found in the archive.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
