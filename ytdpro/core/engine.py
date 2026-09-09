"""Thin, GUI-agnostic wrapper around yt-dlp.

Nothing in here imports Qt: the engine is callable from a plain script or a test,
and every long-running call takes a ``threading.Event`` so a caller can abort it.
"""

from __future__ import annotations

import logging
import shutil
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import yt_dlp

from .formats import QualityPreset
from .tasks import DownloadTask, Progress, TaskStatus

log = logging.getLogger(__name__)

ProgressCallback = Callable[[Progress], None]
LogCallback = Callable[[str], None]


class DownloadCancelled(Exception):
    """Raised inside the progress hook to unwind a download the user stopped."""


class MetadataError(Exception):
    """Raised when a URL cannot be resolved into video or playlist metadata."""


FFMPEG_HINT = (
    "This video is only published as separate video and audio streams, which "
    "have to be merged with ffmpeg — and ffmpeg was not found. Install ffmpeg "
    "(or drop the binary into the app's bin/ folder) and try again."
)


def explain_error(message: str, *, has_ffmpeg: bool) -> str:
    """Replace yt-dlp's opaque format error with the real cause when we know it."""
    if not has_ffmpeg and "Requested format is not available" in message:
        return FFMPEG_HINT
    return message


def _app_root() -> Path:
    """Directory to look in for a bundled ffmpeg, frozen or not."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def find_ffmpeg() -> str | None:
    """Locate ffmpeg: a copy bundled in ./bin wins, otherwise fall back to PATH."""
    suffix = ".exe" if sys.platform == "win32" else ""
    bundled = _app_root() / "bin" / f"ffmpeg{suffix}"
    if bundled.is_file():
        return str(bundled.parent)
    system = shutil.which("ffmpeg")
    if system:
        return str(Path(system).parent)
    return None


class _YdlLogger:
    """Adapts yt-dlp's logger interface onto an optional callback."""

    def __init__(self, callback: LogCallback | None) -> None:
        self._callback = callback

    def _emit(self, msg: str) -> None:
        log.debug(msg)
        if self._callback:
            self._callback(msg)

    def debug(self, msg: str) -> None:
        # yt-dlp routes its normal stdout chatter through debug() prefixed with
        # "[debug] "; only the unprefixed lines are worth showing a user.
        if not msg.startswith("[debug] "):
            self._emit(msg)

    def info(self, msg: str) -> None:
        self._emit(msg)

    def warning(self, msg: str) -> None:
        self._emit(f"Warning: {msg}")

    def error(self, msg: str) -> None:
        self._emit(f"Error: {msg}")


def _base_options(log_callback: LogCallback | None) -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "ignoreerrors": False,
        "logger": _YdlLogger(log_callback),
    }


def fetch_video_info(url: str, log_callback: LogCallback | None = None) -> dict:
    """Resolve a single video URL to its metadata dict."""
    options = _base_options(log_callback) | {"skip_download": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # yt-dlp raises a wide range of error types
        raise MetadataError(str(exc)) from exc
    if not info:
        raise MetadataError("No video information returned for this URL.")
    if info.get("_type") == "playlist":
        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            raise MetadataError("This playlist is empty.")
        return entries[0]
    return info


def fetch_playlist(
    url: str, log_callback: LogCallback | None = None
) -> tuple[str, list[DownloadTask]]:
    """Resolve a playlist URL to its title and one task per entry.

    Uses a flat extraction so a 200-video playlist resolves in one request
    instead of one request per video.
    """
    options = _base_options(log_callback) | {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": False,
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise MetadataError(str(exc)) from exc

    if not info:
        raise MetadataError("Nothing could be read from this URL.")
    if info.get("_type") != "playlist":
        # A single video URL: treat it as a one-item playlist rather than erroring.
        return info.get("title", "Video"), [
            DownloadTask(
                url=info.get("webpage_url") or url,
                title=info.get("title", ""),
                duration=int(info.get("duration") or 0),
                uploader=info.get("uploader", ""),
                index=1,
            )
        ]

    tasks: list[DownloadTask] = []
    for position, entry in enumerate(info.get("entries") or [], start=1):
        if not entry:
            continue  # private / deleted videos come through as None
        entry_url = entry.get("url") or entry.get("webpage_url")
        if not entry_url:
            continue
        if not entry_url.startswith("http"):
            entry_url = f"https://www.youtube.com/watch?v={entry_url}"
        tasks.append(
            DownloadTask(
                url=entry_url,
                title=entry.get("title") or f"Video {position}",
                duration=int(entry.get("duration") or 0),
                uploader=entry.get("uploader") or entry.get("channel") or "",
                index=position,
            )
        )

    if not tasks:
        raise MetadataError("This playlist has no downloadable videos.")
    return info.get("title") or "Playlist", tasks


def _build_progress(data: dict) -> Progress:
    """Normalise one yt-dlp progress dict into a Progress snapshot."""
    total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
    downloaded = int(data.get("downloaded_bytes") or 0)
    percent = (downloaded / total * 100.0) if total else 0.0
    info = data.get("info_dict") or {}
    return Progress(
        status=TaskStatus.DOWNLOADING,
        percent=min(percent, 100.0),
        downloaded_bytes=downloaded,
        total_bytes=total,
        speed=float(data.get("speed") or 0.0),
        eta=int(data.get("eta") or 0),
        format_note=info.get("format_note") or info.get("resolution") or "",
        filename=data.get("filename", ""),
    )


def build_download_options(
    preset: QualityPreset,
    destination: Path,
    *,
    ffmpeg_location: str | None = None,
    concurrent_fragments: int = 4,
    output_template: str = "%(title)s.%(ext)s",
    log_callback: LogCallback | None = None,
) -> dict:
    """Assemble the yt-dlp option dict for one download."""
    has_ffmpeg = bool(ffmpeg_location)
    if preset.needs_ffmpeg and not has_ffmpeg and log_callback:
        log_callback(
            f"ffmpeg is not available — falling back to a single-stream format "
            f"for '{preset.label}'. Install ffmpeg for the full quality range."
        )

    options = _base_options(log_callback) | {
        "format": preset.selector_for(has_ffmpeg),
        "outtmpl": str(destination / output_template),
        "concurrent_fragment_downloads": max(1, concurrent_fragments),
        "retries": 5,
        "fragment_retries": 5,
        "restrictfilenames": False,
        "windowsfilenames": sys.platform == "win32",
        "overwrites": False,
        "continuedl": True,
    }

    if preset.audio_only:
        # Converting to mp3/m4a is an ffmpeg job; without it, keep the source audio.
        if has_ffmpeg:
            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": preset.audio_codec or "mp3",
                    "preferredquality": "192",
                }
            ]
    elif has_ffmpeg:
        options["merge_output_format"] = preset.container

    if ffmpeg_location:
        options["ffmpeg_location"] = ffmpeg_location
    return options


def download(
    task: DownloadTask,
    destination: Path,
    preset: QualityPreset,
    *,
    cancel_event: threading.Event | None = None,
    on_progress: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
    concurrent_fragments: int = 4,
    output_template: str = "%(title)s.%(ext)s",
) -> str:
    """Download one video. Returns the final file path.

    Raises :class:`DownloadCancelled` if ``cancel_event`` is set part-way through.
    """
    destination.mkdir(parents=True, exist_ok=True)
    final_path = ""

    def check_cancelled() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled

    def progress_hook(data: dict) -> None:
        check_cancelled()
        status = data.get("status")
        if status == "downloading" and on_progress:
            on_progress(_build_progress(data))
        elif status == "finished" and on_progress:
            # The stream is on disk; ffmpeg merge/extract may still follow.
            on_progress(
                Progress(
                    status=TaskStatus.MERGING,
                    percent=100.0,
                    downloaded_bytes=int(data.get("downloaded_bytes") or 0),
                    total_bytes=int(data.get("total_bytes") or 0),
                    filename=data.get("filename", ""),
                )
            )

    def postprocessor_hook(data: dict) -> None:
        check_cancelled()
        if data.get("status") == "started" and on_progress:
            on_progress(Progress(status=TaskStatus.MERGING, percent=100.0))

    options = build_download_options(
        preset,
        destination,
        ffmpeg_location=find_ffmpeg(),
        concurrent_fragments=concurrent_fragments,
        output_template=output_template,
        log_callback=log_callback,
    )
    options["progress_hooks"] = [progress_hook]
    options["postprocessor_hooks"] = [postprocessor_hook]

    check_cancelled()
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(task.url, download=True)
            if info:
                requested = info.get("requested_downloads") or []
                if requested:
                    final_path = requested[0].get("filepath", "")
                if not final_path:
                    final_path = ydl.prepare_filename(info)
    except DownloadCancelled:
        raise
    except Exception as exc:
        # yt-dlp wraps a cancelled hook in its own DownloadError, so re-check.
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled from exc
        raise RuntimeError(explain_error(str(exc), has_ffmpeg=bool(find_ffmpeg()))) from exc

    check_cancelled()
    return final_path
