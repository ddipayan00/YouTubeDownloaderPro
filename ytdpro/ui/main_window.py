"""Application shell: header, tabs, activity log and status bar."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.engine import find_ffmpeg
from ..settings import Settings
from .playlist_tab import PlaylistTab
from .single_tab import SingleVideoTab
from .theme import apply_qt_palette, palette_for, stylesheet

LOG_LIMIT = 2000


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        self._palette = palette_for(settings.theme)
        self._busy_tabs: set[str] = set()

        self.setWindowTitle("YouTube Downloader Pro")
        self.setMinimumSize(QSize(940, 660))

        self.single_tab = SingleVideoTab(settings, self)
        self.playlist_tab = PlaylistTab(settings, self._palette, self)

        self._build_ui()
        self._connect_tabs()
        self._apply_theme()
        self._restore_geometry()
        self._check_ffmpeg()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 16, 18, 12)
        body_layout.setSpacing(12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.single_tab, "Single Video")
        self.tabs.addTab(self.playlist_tab, "Playlist")
        body_layout.addWidget(self.tabs, 1)

        body_layout.addWidget(self._build_log_panel())
        layout.addWidget(body, 1)

        self.setCentralWidget(central)
        self.ffmpeg_label = QLabel()
        self.statusBar().addPermanentWidget(self.ffmpeg_label)
        self.statusBar().showMessage("Ready")

        self._build_shortcuts()

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)

        mark = QLabel("▶")
        mark.setObjectName("Brand")

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("YouTube Downloader Pro")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Single videos and whole playlists, downloaded in parallel")
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("Ghost")
        self.theme_button.setToolTip("Switch between the light and dark theme")
        self.theme_button.clicked.connect(self.toggle_theme)

        self.log_button = QPushButton("Activity log")
        self.log_button.setObjectName("Ghost")
        self.log_button.setCheckable(True)
        self.log_button.toggled.connect(self._toggle_log)

        layout.addWidget(mark)
        layout.addLayout(titles)
        layout.addStretch(1)
        layout.addWidget(self.log_button)
        layout.addWidget(self.theme_button)
        return header

    def _build_log_panel(self) -> QPlainTextEdit:
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(LOG_LIMIT)
        self.log_view.setMinimumHeight(90)
        self.log_view.setMaximumHeight(150)
        self.log_view.setVisible(False)
        self.log_view.setPlaceholderText("Download activity appears here.")
        return self.log_view

    def _build_shortcuts(self) -> None:
        for key, slot in (
            (QKeySequence("Ctrl+L"), lambda: self.log_button.toggle()),
            (QKeySequence("Ctrl+D"), lambda: self.tabs.setCurrentIndex(0)),
            (QKeySequence("Ctrl+P"), lambda: self.tabs.setCurrentIndex(1)),
            (QKeySequence("Ctrl+T"), self.toggle_theme),
            (QKeySequence("Ctrl+Q"), self.close),
        ):
            action = QAction(self)
            action.setShortcut(key)
            action.triggered.connect(slot)
            self.addAction(action)

    def _connect_tabs(self) -> None:
        for name, tab in (("single", self.single_tab), ("playlist", self.playlist_tab)):
            tab.log_message.connect(self.append_log)
            tab.status_message.connect(self.statusBar().showMessage)
            tab.busy_changed.connect(
                lambda busy, name=name: self._set_tab_busy(name, busy)
            )
        # Keep the chosen folder consistent across both tabs.
        self.single_tab.path_edit.textChanged.connect(self.playlist_tab.set_download_dir)
        self.playlist_tab.path_edit.textChanged.connect(self.single_tab.set_download_dir)

    # ------------------------------------------------------------------
    # behaviour
    # ------------------------------------------------------------------
    def _set_tab_busy(self, name: str, busy: bool) -> None:
        """Track which tabs have work in flight, so closing can warn about it."""
        if busy:
            self._busy_tabs.add(name)
        else:
            self._busy_tabs.discard(name)

    @property
    def is_busy(self) -> bool:
        return bool(self._busy_tabs)

    @Slot(str)
    def append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"{timestamp}  {message}")

    def _toggle_log(self, visible: bool) -> None:
        self.log_view.setVisible(visible)

    @Slot()
    def toggle_theme(self) -> None:
        self._settings.theme = "light" if self._settings.theme == "dark" else "dark"
        self._palette = palette_for(self._settings.theme)
        self._apply_theme()

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_qt_palette(app, self._palette)
        self.setStyleSheet(stylesheet(self._palette))
        self.theme_button.setText(
            "Light mode" if self._palette.name == "dark" else "Dark mode"
        )
        self.playlist_tab.apply_palette(self._palette)
        self._style_ffmpeg_label()

    def _check_ffmpeg(self) -> None:
        self._has_ffmpeg = find_ffmpeg() is not None
        if self._has_ffmpeg:
            self.ffmpeg_label.setText("ffmpeg ready")
        else:
            self.ffmpeg_label.setText("ffmpeg not found")
            self.ffmpeg_label.setToolTip(
                "Without ffmpeg, high-resolution video and audio streams cannot be merged.\n"
                "Install ffmpeg, or drop the binary in the app's bin/ folder."
            )
            self.append_log(
                "ffmpeg was not found — quality above 720p and audio extraction need it."
            )
        self._style_ffmpeg_label()

    def _style_ffmpeg_label(self) -> None:
        found = getattr(self, "_has_ffmpeg", False)
        colour = self._palette.success if found else self._palette.warning
        self.ffmpeg_label.setStyleSheet(f"color: {colour};")

    def _restore_geometry(self) -> None:
        saved = self._settings.geometry
        if saved:
            self.restoreGeometry(saved)
        else:
            self.resize(1040, 720)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.is_busy:
            answer = QMessageBox.question(
                self,
                "Downloads in progress",
                "Downloads are still running. Cancel them and quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._settings.geometry = self.saveGeometry().data()
        self.single_tab.shutdown()
        self.playlist_tab.shutdown()
        super().closeEvent(event)
