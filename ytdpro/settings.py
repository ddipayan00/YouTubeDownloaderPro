"""Persisted user preferences, backed by QSettings."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from .core.formats import DEFAULT_PRESET_LABEL

ORG = "YTDPro"
APP = "YouTube Downloader Pro"

MIN_PARALLEL = 1
MAX_PARALLEL = 8
DEFAULT_PARALLEL = 3


def default_download_dir() -> str:
    """The OS download folder if there is one, else the home directory."""
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return location or str(Path.home())


class Settings:
    """Thin typed wrapper so the rest of the app never touches raw QSettings keys."""

    def __init__(self) -> None:
        self._store = QSettings(ORG, APP)

    def _get(self, key: str, default, cast):
        value = self._store.value(key, default)
        try:
            return cast(value)
        except (TypeError, ValueError):
            return default

    @property
    def download_dir(self) -> str:
        return self._get("download_dir", default_download_dir(), str)

    @download_dir.setter
    def download_dir(self, value: str) -> None:
        self._store.setValue("download_dir", value)

    @property
    def quality(self) -> str:
        return self._get("quality", DEFAULT_PRESET_LABEL, str)

    @quality.setter
    def quality(self, value: str) -> None:
        self._store.setValue("quality", value)

    @property
    def max_parallel(self) -> int:
        value = self._get("max_parallel", DEFAULT_PARALLEL, int)
        return max(MIN_PARALLEL, min(MAX_PARALLEL, value))

    @max_parallel.setter
    def max_parallel(self, value: int) -> None:
        self._store.setValue("max_parallel", max(MIN_PARALLEL, min(MAX_PARALLEL, value)))

    @property
    def theme(self) -> str:
        return self._get("theme", "dark", str)

    @theme.setter
    def theme(self, value: str) -> None:
        self._store.setValue("theme", value)

    @property
    def playlist_subfolder(self) -> bool:
        return self._store.value("playlist_subfolder", True, type=bool)

    @playlist_subfolder.setter
    def playlist_subfolder(self, value: bool) -> None:
        self._store.setValue("playlist_subfolder", bool(value))

    @property
    def geometry(self):
        """Returns whatever QSettings stored (bytes or QByteArray), or None."""
        return self._store.value("geometry") or None

    @geometry.setter
    def geometry(self, value: bytes) -> None:
        self._store.setValue("geometry", value)
