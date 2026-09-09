"""Tests for the pure-logic parts of the core package (no network, no Qt)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ytdpro.core import engine
from ytdpro.core.engine import FFMPEG_HINT, explain_error
from ytdpro.core.formats import ALL_PRESETS, preset_by_label
from ytdpro.core.tasks import (
    DownloadTask,
    TaskStatus,
    format_bytes,
    format_duration,
    format_speed,
)
from ytdpro.ui.playlist_tab import safe_folder_name


class TestFormats:
    def test_labels_are_unique(self):
        labels = [p.label for p in ALL_PRESETS]
        assert len(labels) == len(set(labels))

    def test_unknown_label_falls_back_to_best(self):
        assert preset_by_label("nonsense").label == "Best available"

    @pytest.mark.parametrize("preset", ALL_PRESETS, ids=lambda p: p.label)
    def test_merging_presets_have_an_ffmpeg_free_fallback(self, preset):
        if preset.needs_ffmpeg:
            assert preset.fallback_selector
            assert "+" not in preset.selector_for(has_ffmpeg=False)

    def test_selector_switches_on_ffmpeg_availability(self):
        preset = preset_by_label("1080p (Full HD)")
        assert "+" in preset.selector_for(has_ffmpeg=True)
        assert "+" not in preset.selector_for(has_ffmpeg=False)

    def test_sd_tiers_prefer_widely_playable_codecs(self):
        # H.264 + AAC plays everywhere; 4K is only published as VP9/AV1.
        assert "avc1" in preset_by_label("720p (HD)").selector
        assert "avc1" not in preset_by_label("2160p (4K)").selector


class TestFormatting:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, "—"), (-1, "—"), (512, "512 B"), (1536, "1.5 KB"), (5 * 1024**2, "5.0 MB")],
    )
    def test_format_bytes(self, value, expected):
        assert format_bytes(value) == expected

    def test_format_speed(self):
        assert format_speed(0) == "—"
        assert format_speed(1024 * 1024) == "1.0 MB/s"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(0, "—"), (45, "0:45"), (125, "2:05"), (3661, "1:01:01")],
    )
    def test_format_duration(self, value, expected):
        assert format_duration(value) == expected


class TestTasks:
    def test_ids_are_unique(self):
        assert DownloadTask(url="a").task_id != DownloadTask(url="b").task_id

    def test_display_title_falls_back_to_url(self):
        assert DownloadTask(url="https://x/1").display_title == "https://x/1"
        assert DownloadTask(url="https://x/1", title="Name").display_title == "Name"

    def test_status_classification(self):
        assert TaskStatus.COMPLETED.is_terminal
        assert TaskStatus.FAILED.is_terminal
        assert not TaskStatus.DOWNLOADING.is_terminal
        assert TaskStatus.DOWNLOADING.is_active
        assert not TaskStatus.QUEUED.is_active


class TestErrorExplanation:
    def test_format_error_is_explained_when_ffmpeg_is_missing(self):
        assert explain_error("Requested format is not available", has_ffmpeg=False) == FFMPEG_HINT

    def test_message_is_untouched_when_ffmpeg_is_present(self):
        message = "Requested format is not available"
        assert explain_error(message, has_ffmpeg=True) == message


class TestFolderNames:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Normal Playlist", "Normal Playlist"),
            ("Bad/Name: v2?", "Bad_Name_ v2_"),
            ("...", "Playlist"),
            ("", "Playlist"),
        ],
    )
    def test_sanitisation(self, raw, expected):
        assert safe_folder_name(raw) == expected

    def test_length_is_capped(self):
        assert len(safe_folder_name("x" * 500)) == 120


class TestFfmpegDiscovery:
    """Regression cover for the packaged-app lookup.

    A PyInstaller onedir build unpacks data into sys._MEIPASS (the _internal
    folder), not next to the executable. Searching only the executable's own
    directory meant a bundled ffmpeg was never found in a real build.
    """

    @staticmethod
    def _make_ffmpeg(root: Path) -> Path:
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True)
        binary = bin_dir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
        binary.write_text("")
        return bin_dir

    def test_finds_ffmpeg_in_meipass(self, tmp_path, monkeypatch):
        bin_dir = self._make_ffmpeg(tmp_path / "_internal")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_internal"), raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "app"), raising=False)
        assert engine.find_ffmpeg() == str(bin_dir)

    def test_finds_ffmpeg_beside_the_executable(self, tmp_path, monkeypatch):
        bin_dir = self._make_ffmpeg(tmp_path)
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "app"), raising=False)
        assert engine.find_ffmpeg() == str(bin_dir)

    def test_finds_ffmpeg_in_macos_app_resources(self, tmp_path, monkeypatch):
        contents = tmp_path / "App.app" / "Contents"
        (contents / "MacOS").mkdir(parents=True)
        bin_dir = self._make_ffmpeg(contents / "Resources")
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", str(contents / "MacOS" / "app"), raising=False)
        assert engine.find_ffmpeg() == str(bin_dir)

    def test_falls_back_to_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "app"), raising=False)
        monkeypatch.setattr(engine.shutil, "which", lambda _: "/usr/bin/ffmpeg")
        assert engine.find_ffmpeg() == str(Path("/usr/bin/ffmpeg").parent)

    def test_returns_none_when_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "app"), raising=False)
        monkeypatch.setattr(engine.shutil, "which", lambda _: None)
        assert engine.find_ffmpeg() is None
