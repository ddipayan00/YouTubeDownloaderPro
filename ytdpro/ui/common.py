"""Small shared widgets and helpers used by both tabs."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def looks_like_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


def elide(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Card(QFrame):
    """A rounded panel with an optional title, used as the layout unit everywhere."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            self._layout.addWidget(label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget) -> QWidget:
        self._layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


class StatTile(QWidget):
    """A labelled read-only value, e.g. SPEED / 4.2 MB/s."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._caption = QLabel(label.upper())
        self._caption.setObjectName("StatLabel")
        self._value = QLabel("—")
        self._value.setObjectName("StatValue")

        layout.addWidget(self._caption)
        layout.addWidget(self._value)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, text: str) -> None:
        self._value.setText(text or "—")


class StatRow(QWidget):
    """A horizontal strip of :class:`StatTile` widgets, addressable by key."""

    def __init__(self, labels: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        self._tiles: dict[str, StatTile] = {}
        for label in labels:
            tile = StatTile(label)
            self._tiles[label.lower()] = tile
            layout.addWidget(tile)

    def set(self, key: str, value: str) -> None:
        tile = self._tiles.get(key.lower())
        if tile is not None:
            tile.set_value(value)

    def reset(self) -> None:
        for tile in self._tiles.values():
            tile.set_value("—")


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label
