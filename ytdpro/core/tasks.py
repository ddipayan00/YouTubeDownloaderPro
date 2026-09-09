"""Data model for a single download and the progress it reports."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum

_ids = itertools.count(1)


class TaskStatus(Enum):
    QUEUED = "Queued"
    FETCHING = "Fetching"
    DOWNLOADING = "Downloading"
    MERGING = "Merging"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

    @property
    def is_active(self) -> bool:
        return self in (TaskStatus.FETCHING, TaskStatus.DOWNLOADING, TaskStatus.MERGING)


@dataclass
class Progress:
    """A snapshot of one download, normalised out of yt-dlp's progress hook."""

    status: TaskStatus = TaskStatus.QUEUED
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    speed: float = 0.0  # bytes/sec
    eta: int = 0  # seconds
    format_note: str = ""
    filename: str = ""


@dataclass
class DownloadTask:
    """One queued video. Playlist items and single downloads share this type."""

    url: str
    title: str = ""
    duration: int = 0
    uploader: str = ""
    index: int = 0
    selected: bool = True
    status: TaskStatus = TaskStatus.QUEUED
    progress: Progress = field(default_factory=Progress)
    output_path: str = ""
    error: str = ""
    task_id: int = field(default_factory=lambda: next(_ids))

    @property
    def display_title(self) -> str:
        return self.title or self.url


def format_bytes(num: float) -> str:
    """Human-readable byte count, e.g. 1.4 GB."""
    if num <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec <= 0:
        return "—"
    return f"{format_bytes(bytes_per_sec)}/s"


def format_duration(seconds: float) -> str:
    """Seconds as H:MM:SS (or M:SS when under an hour)."""
    if not seconds or seconds < 0:
        return "—"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
