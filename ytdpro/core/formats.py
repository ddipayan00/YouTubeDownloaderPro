"""Quality presets and their yt-dlp format selectors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QualityPreset:
    """A user-facing quality choice and the yt-dlp options it implies."""

    label: str
    selector: str
    container: str = "mp4"
    audio_only: bool = False
    audio_codec: str = ""
    fallback_selector: str = ""

    @property
    def needs_ffmpeg(self) -> bool:
        """Merging separate video+audio streams or transcoding audio needs ffmpeg."""
        return self.audio_only or "+" in self.selector

    def selector_for(self, has_ffmpeg: bool) -> str:
        """The format string to actually use.

        Without ffmpeg yt-dlp refuses a ``video+audio`` selector outright rather
        than falling through to the alternative after the slash, so swap in a
        progressive-only selector instead of letting the download abort.
        """
        if has_ffmpeg or not self.needs_ffmpeg or not self.fallback_selector:
            return self.selector
        return self.fallback_selector


# Up to 1080p YouTube still offers H.264/AAC, which plays in every player and
# on every phone. Above that it only serves VP9/AV1, so asking for avc1 there
# would silently cap the download at 1080p -- those tiers take whatever is best.
_COMPATIBLE_TIER_MAX = 1080


def _video(label: str, height: int) -> QualityPreset:
    generic = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
    if height <= _COMPATIBLE_TIER_MAX:
        selector = (
            f"bestvideo[height<={height}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/{generic}"
        )
    else:
        selector = generic
    return QualityPreset(
        label=label,
        selector=selector,
        fallback_selector=f"best[height<={height}]/best",
    )


VIDEO_PRESETS: tuple[QualityPreset, ...] = (
    QualityPreset("Best available", "bestvideo+bestaudio/best", fallback_selector="best"),
    QualityPreset(
        "Best compatible (H.264)",
        "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo+bestaudio/best",
        fallback_selector="best",
    ),
    _video("2160p (4K)", 2160),
    _video("1440p (2K)", 1440),
    _video("1080p (Full HD)", 1080),
    _video("720p (HD)", 720),
    _video("480p", 480),
    _video("360p", 360),
    _video("240p", 240),
    _video("144p", 144),
    QualityPreset("Smallest file", "worstvideo+worstaudio/worst", fallback_selector="worst"),
)

AUDIO_PRESETS: tuple[QualityPreset, ...] = (
    QualityPreset("Audio only (MP3)", "bestaudio/best", "mp3", True, "mp3", "bestaudio/best"),
    QualityPreset(
        "Audio only (M4A)", "bestaudio[ext=m4a]/bestaudio/best", "m4a", True, "m4a",
        "bestaudio[ext=m4a]/bestaudio/best",
    ),
)

ALL_PRESETS: tuple[QualityPreset, ...] = VIDEO_PRESETS + AUDIO_PRESETS

DEFAULT_PRESET_LABEL = "1080p (Full HD)"


def preset_by_label(label: str) -> QualityPreset:
    """Look up a preset by its display label, falling back to 'Best available'."""
    for preset in ALL_PRESETS:
        if preset.label == label:
            return preset
    return VIDEO_PRESETS[0]
