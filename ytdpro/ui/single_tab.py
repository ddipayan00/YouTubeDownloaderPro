"""The 'Single Video' tab: fetch metadata, pick a quality, download one video."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.formats import ALL_PRESETS, preset_by_label
from ..core.tasks import (
    DownloadTask,
    Progress,
    TaskStatus,
    format_bytes,
    format_duration,
    format_speed,
)
from ..core.workers import DownloadPool, DownloadWorker, VideoInfoWorker
from ..settings import Settings
from .common import Card, StatRow, elide, field_label, looks_like_url

THUMB_W, THUMB_H = 168, 94


class SingleVideoTab(QWidget):
    """One video at a time — the pool here is deliberately one thread wide."""

    log_message = Signal(str)
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._pool = DownloadPool(max_parallel=1)
        self._meta_pool = QThreadPool()
        self._network = QNetworkAccessManager(self)
        self._task: DownloadTask | None = None
        self._worker: DownloadWorker | None = None
        self._info_worker: VideoInfoWorker | None = None

        self._build_ui()
        self._set_running(False)

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        outer.addWidget(self._build_url_card())
        outer.addWidget(self._build_preview_card())
        outer.addWidget(self._build_download_card())
        outer.addStretch(1)

    def _build_url_card(self) -> Card:
        card = Card("Video URL")
        row = QHBoxLayout()
        row.setSpacing(8)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.fetch_info)

        self.paste_button = QPushButton("Paste")
        self.paste_button.setToolTip("Paste a URL from the clipboard")
        self.paste_button.clicked.connect(self._paste)

        self.fetch_button = QPushButton("Fetch info")
        self.fetch_button.clicked.connect(self.fetch_info)

        row.addWidget(self.url_edit, 1)
        row.addWidget(self.paste_button)
        row.addWidget(self.fetch_button)
        card.add_layout(row)
        return card

    def _build_preview_card(self) -> QFrame:
        self.preview_card = Card()
        self.preview_card.setVisible(False)

        row = QHBoxLayout()
        row.setSpacing(14)

        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(THUMB_W, THUMB_H)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail.setStyleSheet("border-radius: 8px;")

        details = QVBoxLayout()
        details.setSpacing(4)
        self.video_title = QLabel()
        self.video_title.setObjectName("VideoTitle")
        self.video_title.setWordWrap(True)
        self.video_meta = QLabel()
        self.video_meta.setObjectName("Muted")
        details.addWidget(self.video_title)
        details.addWidget(self.video_meta)
        details.addStretch(1)

        row.addWidget(self.thumbnail)
        row.addLayout(details, 1)
        self.preview_card.add_layout(row)
        return self.preview_card

    def _build_download_card(self) -> Card:
        card = Card("Download")

        options = QHBoxLayout()
        options.setSpacing(10)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems([p.label for p in ALL_PRESETS])
        self.quality_combo.setCurrentText(self._settings.quality)
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        self.quality_combo.setMinimumWidth(180)

        self.path_edit = QLineEdit(self._settings.download_dir)
        self.path_edit.setObjectName("PathField")
        self.path_edit.setReadOnly(True)
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._choose_folder)

        options.addWidget(field_label("Quality"))
        options.addWidget(self.quality_combo)
        options.addSpacing(12)
        options.addWidget(field_label("Save to"))
        options.addWidget(self.path_edit, 1)
        options.addWidget(self.browse_button)
        card.add_layout(options)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.download_button = QPushButton("Download")
        self.download_button.setObjectName("Primary")
        self.download_button.setMinimumWidth(140)
        self.download_button.clicked.connect(self.start_download)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_download)

        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.clicked.connect(self._open_folder)

        actions.addWidget(self.download_button)
        actions.addWidget(self.cancel_button)
        actions.addStretch(1)
        actions.addWidget(self.open_folder_button)
        card.add_layout(actions)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        card.add(self.progress_bar)

        self.stats = StatRow(("Status", "Size", "Speed", "ETA"))
        card.add(self.stats)
        return card

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _paste(self) -> None:
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)

    def _on_quality_changed(self, label: str) -> None:
        self._settings.quality = label

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.path_edit.text()
        )
        if folder:
            self.path_edit.setText(folder)
            self._settings.download_dir = folder

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.path_edit.text()))

    def set_download_dir(self, folder: str) -> None:
        # The two tabs mirror each other; bail out early or they ping-pong.
        if folder and folder != self.path_edit.text():
            self.path_edit.setText(folder)

    def _set_running(self, running: bool) -> None:
        self.download_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.fetch_button.setEnabled(not running)
        self.url_edit.setReadOnly(running)
        self.quality_combo.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.busy_changed.emit(running)

    def _validated_url(self) -> str | None:
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Paste a YouTube video URL first.")
            return None
        if not looks_like_url(url):
            QMessageBox.warning(
                self, "Invalid URL", "That does not look like a link. It should start with http."
            )
            return None
        return url

    # ------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------
    @Slot()
    def fetch_info(self) -> None:
        url = self._validated_url()
        if not url:
            return
        self.fetch_button.setEnabled(False)
        self.status_message.emit("Fetching video information…")
        self.stats.set("status", "Fetching")

        worker = VideoInfoWorker(url)
        worker.signals.ready.connect(self._on_info_ready)
        worker.signals.failed.connect(self._on_info_failed)
        worker.signals.message.connect(self.log_message)
        self._info_worker = worker
        self._meta_pool.start(worker)

    @Slot(object)
    def _on_info_ready(self, info: dict) -> None:
        self.fetch_button.setEnabled(True)
        self.video_title.setText(elide(info.get("title", "Untitled"), 90))
        pieces = [
            info.get("uploader") or info.get("channel") or "",
            format_duration(info.get("duration") or 0),
        ]
        views = info.get("view_count")
        if views:
            pieces.append(f"{views:,} views")
        self.video_meta.setText("  •  ".join(p for p in pieces if p and p != "—"))
        self.preview_card.setVisible(True)
        self.stats.set("status", "Ready")
        self.status_message.emit("Video information loaded.")
        self.log_message.emit(f"Resolved: {info.get('title', '')}")

        thumbnail = info.get("thumbnail")
        if thumbnail:
            self._load_thumbnail(thumbnail)
        else:
            self.thumbnail.clear()

    @Slot(str)
    def _on_info_failed(self, error: str) -> None:
        self.fetch_button.setEnabled(True)
        self.stats.set("status", "—")
        self.status_message.emit("Could not read that URL.")
        self.log_message.emit(f"Metadata error: {error}")
        QMessageBox.critical(self, "Could not read that URL", error)

    def _load_thumbnail(self, url: str) -> None:
        reply = self._network.get(QNetworkRequest(QUrl(url)))

        def done() -> None:
            data = reply.readAll()
            reply.deleteLater()
            pixmap = QPixmap()
            if pixmap.loadFromData(data):
                self.thumbnail.setPixmap(
                    pixmap.scaled(
                        THUMB_W,
                        THUMB_H,
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

        reply.finished.connect(done)

    # ------------------------------------------------------------------
    # downloading
    # ------------------------------------------------------------------
    @Slot()
    def start_download(self) -> None:
        url = self._validated_url()
        if not url:
            return
        destination = Path(self.path_edit.text())
        if not self.path_edit.text():
            QMessageBox.warning(self, "No folder", "Choose where to save the download.")
            return

        preset = preset_by_label(self.quality_combo.currentText())
        self._task = DownloadTask(url=url, title=self.video_title.text())
        worker = DownloadWorker(self._task, destination, preset)
        worker.signals.started.connect(lambda _: self.stats.set("status", "Starting"))
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        worker.signals.cancelled.connect(self._on_cancelled)
        worker.signals.message.connect(lambda _tid, line: self.log_message.emit(line))
        self._worker = worker

        self.progress_bar.setValue(0)
        self.stats.reset()
        self._set_running(True)
        self.status_message.emit(f"Downloading at {preset.label}…")
        self.log_message.emit(f"Starting download: {url} [{preset.label}]")
        self._pool.submit(worker)

    @Slot()
    def cancel_download(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            self.stats.set("status", "Cancelling")
            self.status_message.emit("Cancelling…")

    @Slot(int, object)
    def _on_progress(self, _task_id: int, progress: Progress) -> None:
        if progress.status is TaskStatus.MERGING:
            self.progress_bar.setValue(100)
            self.stats.set("status", "Merging")
            self.stats.set("speed", "—")
            self.stats.set("eta", "—")
            return
        if progress.status is TaskStatus.FETCHING:
            self.stats.set("status", "Fetching")
            return
        self.progress_bar.setValue(int(progress.percent))
        label = "Downloading"
        if progress.format_note:
            label = f"Downloading · {progress.format_note}"
        self.stats.set("status", label)
        self.stats.set("size", format_bytes(progress.total_bytes))
        self.stats.set("speed", format_speed(progress.speed))
        self.stats.set("eta", format_duration(progress.eta))

    @Slot(int, str)
    def _on_finished(self, task_id: int, path: str) -> None:
        self._pool.release(task_id)
        self.progress_bar.setValue(100)
        self.stats.set("status", "Completed")
        self.stats.set("speed", "—")
        self.stats.set("eta", "—")
        self._set_running(False)
        name = Path(path).name if path else "the video"
        self.status_message.emit(f"Saved {name}")
        self.log_message.emit(f"Completed: {path}")
        QMessageBox.information(
            self, "Download complete", f"Saved to:\n{path or self.path_edit.text()}"
        )

    @Slot(int, str)
    def _on_failed(self, task_id: int, error: str) -> None:
        self._pool.release(task_id)
        self.stats.set("status", "Failed")
        self._set_running(False)
        self.status_message.emit("Download failed.")
        self.log_message.emit(f"Failed: {error}")
        QMessageBox.critical(self, "Download failed", error)

    @Slot(int)
    def _on_cancelled(self, task_id: int) -> None:
        self._pool.release(task_id)
        self.progress_bar.setValue(0)
        self.stats.set("status", "Cancelled")
        self._set_running(False)
        self.status_message.emit("Download cancelled.")
        self.log_message.emit("Download cancelled by user.")

    def shutdown(self) -> None:
        self._pool.cancel_all()
        self._pool.wait_for_done(3000)
