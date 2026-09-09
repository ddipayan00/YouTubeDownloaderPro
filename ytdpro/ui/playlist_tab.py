"""The 'Playlist' tab: fetch a playlist and download its videos in parallel."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..core.formats import ALL_PRESETS, preset_by_label
from ..core.tasks import DownloadTask, Progress, TaskStatus
from ..core.workers import DownloadPool, DownloadWorker, PlaylistFetchWorker
from ..settings import MAX_PARALLEL, MIN_PARALLEL, Settings
from .common import Card, elide, field_label, looks_like_url
from .playlist_model import (
    COL_CHECK,
    COL_ETA,
    COL_INDEX,
    COL_LENGTH,
    COL_PROGRESS,
    COL_SIZE,
    COL_SPEED,
    COL_STATUS,
    COL_TITLE,
    PlaylistModel,
    ProgressDelegate,
)
from .theme import Palette

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_folder_name(name: str) -> str:
    """Make a playlist title usable as a folder name on every platform."""
    cleaned = _INVALID_PATH_CHARS.sub("_", name).strip(" .")
    return cleaned[:120] or "Playlist"


class PlaylistTab(QWidget):
    """Downloads playlist items concurrently, up to the user's parallel limit."""

    log_message = Signal(str)
    busy_changed = Signal(bool)
    status_message = Signal(str)

    def __init__(self, settings: Settings, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._pool = DownloadPool(max_parallel=settings.max_parallel)
        self._meta_pool = QThreadPool()
        self._model = PlaylistModel(self)
        self._model.set_palette(palette)
        self._delegate = ProgressDelegate(palette, self)
        self._playlist_title = ""
        self._running = False
        self._remaining = 0
        self._run_tasks: list[DownloadTask] = []
        self._fetch_worker: PlaylistFetchWorker | None = None

        self._build_ui()
        self._set_running(False)
        self._update_summary()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        outer.addWidget(self._build_source_card())
        outer.addWidget(self._build_options_card())
        outer.addWidget(self._build_queue_card(), 1)

    def _build_source_card(self) -> Card:
        card = Card("Playlist URL")
        row = QHBoxLayout()
        row.setSpacing(8)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/playlist?list=…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.fetch_playlist)

        self.paste_button = QPushButton("Paste")
        self.paste_button.clicked.connect(self._paste)

        self.fetch_button = QPushButton("Fetch playlist")
        self.fetch_button.clicked.connect(self.fetch_playlist)

        row.addWidget(self.url_edit, 1)
        row.addWidget(self.paste_button)
        row.addWidget(self.fetch_button)
        card.add_layout(row)
        return card

    def _build_options_card(self) -> Card:
        card = Card("Options")

        first = QHBoxLayout()
        first.setSpacing(10)

        self.quality_combo = QComboBox()
        self.quality_combo.addItems([p.label for p in ALL_PRESETS])
        self.quality_combo.setCurrentText(self._settings.quality)
        self.quality_combo.setMinimumWidth(180)

        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(MIN_PARALLEL, MAX_PARALLEL)
        self.parallel_spin.setValue(self._settings.max_parallel)
        self.parallel_spin.setToolTip(
            "How many videos download at the same time.\n"
            "Higher is faster on a fast connection; too high can get you rate-limited."
        )
        self.parallel_spin.valueChanged.connect(self._on_parallel_changed)

        self.path_edit = QLineEdit(self._settings.download_dir)
        self.path_edit.setObjectName("PathField")
        self.path_edit.setReadOnly(True)
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._choose_folder)

        first.addWidget(field_label("Quality"))
        first.addWidget(self.quality_combo)
        first.addSpacing(12)
        first.addWidget(field_label("Parallel downloads"))
        first.addWidget(self.parallel_spin)
        first.addSpacing(12)
        first.addWidget(field_label("Save to"))
        first.addWidget(self.path_edit, 1)
        first.addWidget(self.browse_button)
        card.add_layout(first)

        second = QHBoxLayout()
        second.setSpacing(10)
        self.subfolder_check = QCheckBox("Create a subfolder named after the playlist")
        self.subfolder_check.setChecked(self._settings.playlist_subfolder)
        self.subfolder_check.toggled.connect(self._on_subfolder_toggled)

        self.download_button = QPushButton("Download selected")
        self.download_button.setObjectName("Primary")
        self.download_button.setMinimumWidth(170)
        self.download_button.clicked.connect(self.start_downloads)

        self.cancel_button = QPushButton("Cancel all")
        self.cancel_button.clicked.connect(self.cancel_all)

        self.open_folder_button = QPushButton("Open folder")
        self.open_folder_button.setObjectName("Ghost")
        self.open_folder_button.clicked.connect(self._open_folder)

        second.addWidget(self.subfolder_check)
        second.addStretch(1)
        second.addWidget(self.open_folder_button)
        second.addWidget(self.cancel_button)
        second.addWidget(self.download_button)
        card.add_layout(second)
        return card

    def _build_queue_card(self) -> Card:
        card = Card()

        header = QHBoxLayout()
        header.setSpacing(10)
        self.queue_title = QLabel("No playlist loaded")
        self.queue_title.setObjectName("SectionTitle")
        self.summary_label = QLabel()
        self.summary_label.setObjectName("Muted")

        self.select_all_button = QPushButton("Select all")
        self.select_all_button.setObjectName("Ghost")
        self.select_all_button.clicked.connect(lambda: self._model.set_all_selected(True))
        self.select_none_button = QPushButton("Select none")
        self.select_none_button.setObjectName("Ghost")
        self.select_none_button.clicked.connect(lambda: self._model.set_all_selected(False))

        header.addWidget(self.queue_title)
        header.addWidget(self.summary_label)
        header.addStretch(1)
        header.addWidget(self.select_all_button)
        header.addWidget(self.select_none_button)
        card.add_layout(header)

        self.table = QTableView()
        self.table.setObjectName("Queue")
        self.table.setMinimumHeight(220)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setModel(self._model)
        self.table.setItemDelegateForColumn(COL_PROGRESS, self._delegate)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header_view.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        header_view.setHighlightSections(False)
        for column, width in (
            (COL_CHECK, 34),
            (COL_INDEX, 44),
            (COL_LENGTH, 70),
            (COL_STATUS, 118),
            (COL_PROGRESS, 150),
            (COL_SIZE, 80),
            (COL_SPEED, 90),
            (COL_ETA, 70),
        ):
            self.table.setColumnWidth(column, width)
        card.body().addWidget(self.table, 1)

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(False)
        card.add(self.overall_progress)
        return card

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def apply_palette(self, palette: Palette) -> None:
        self._model.set_palette(palette)
        self._delegate.set_palette(palette)
        self.table.viewport().update()

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)

    def _on_parallel_changed(self, value: int) -> None:
        self._settings.max_parallel = value
        self._pool.set_max_parallel(value)
        if self._running:
            self.status_message.emit(f"Parallel limit is now {value}.")

    def _on_subfolder_toggled(self, checked: bool) -> None:
        self._settings.playlist_subfolder = checked

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self.path_edit.text()
        )
        if folder:
            self.path_edit.setText(folder)
            self._settings.download_dir = folder

    def set_download_dir(self, folder: str) -> None:
        # The two tabs mirror each other; bail out early or they ping-pong.
        if folder and folder != self.path_edit.text():
            self.path_edit.setText(folder)

    def _destination(self) -> Path:
        base = Path(self.path_edit.text())
        if self.subfolder_check.isChecked() and self._playlist_title:
            return base / safe_folder_name(self._playlist_title)
        return base

    def _open_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._destination())))

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.download_button.setEnabled(not running and bool(self._model.tasks))
        self.cancel_button.setEnabled(running)
        self.fetch_button.setEnabled(not running)
        self.url_edit.setReadOnly(running)
        self.quality_combo.setEnabled(not running)
        self.browse_button.setEnabled(not running)
        self.subfolder_check.setEnabled(not running)
        self.select_all_button.setEnabled(not running)
        self.select_none_button.setEnabled(not running)
        self.busy_changed.emit(running)

    def _update_summary(self) -> None:
        tasks = self._model.tasks
        if not tasks:
            self.summary_label.setText("")
            self.overall_progress.setValue(0)
            return
        done = self._model.count_by_status(TaskStatus.COMPLETED)
        failed = self._model.count_by_status(TaskStatus.FAILED)
        cancelled = self._model.count_by_status(TaskStatus.CANCELLED)
        selected = len(self._model.selected_tasks())

        parts = [f"{selected} of {len(tasks)} selected", f"{done} done"]
        if failed:
            parts.append(f"{failed} failed")
        if cancelled:
            parts.append(f"{cancelled} cancelled")
        self.summary_label.setText("  •  ".join(parts))

        # Measure the bar against the videos in this run, not every row loaded:
        # picking 2 of 100 videos should still be able to reach 100%.
        tracked = self._run_tasks or self._model.selected_tasks() or tasks
        total_percent = sum(
            100.0 if t.status is TaskStatus.COMPLETED else t.progress.percent for t in tracked
        )
        self.overall_progress.setValue(int(total_percent / len(tracked)))

    # ------------------------------------------------------------------
    # fetching
    # ------------------------------------------------------------------
    @Slot()
    def fetch_playlist(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Paste a YouTube playlist URL first.")
            return
        if not looks_like_url(url):
            QMessageBox.warning(
                self, "Invalid URL", "That does not look like a link. It should start with http."
            )
            return

        self.fetch_button.setEnabled(False)
        self.queue_title.setText("Fetching playlist…")
        self.status_message.emit("Fetching playlist contents…")

        worker = PlaylistFetchWorker(url)
        worker.signals.ready.connect(self._on_playlist_ready)
        worker.signals.failed.connect(self._on_playlist_failed)
        worker.signals.message.connect(self.log_message)
        self._fetch_worker = worker
        self._meta_pool.start(worker)

    @Slot(str, object)
    def _on_playlist_ready(self, title: str, tasks: list[DownloadTask]) -> None:
        self.fetch_button.setEnabled(True)
        self._playlist_title = title
        self._model.set_tasks(tasks)
        self.queue_title.setText(f"{elide(title, 60)} — {len(tasks)} videos")
        self.download_button.setEnabled(True)
        self._update_summary()
        self.status_message.emit(f"Loaded {len(tasks)} videos.")
        self.log_message.emit(f"Playlist '{title}' resolved with {len(tasks)} videos.")

    @Slot(str)
    def _on_playlist_failed(self, error: str) -> None:
        self.fetch_button.setEnabled(True)
        self.queue_title.setText("No playlist loaded")
        self.status_message.emit("Could not read that playlist.")
        self.log_message.emit(f"Playlist error: {error}")
        QMessageBox.critical(self, "Could not read that playlist", error)

    # ------------------------------------------------------------------
    # downloading
    # ------------------------------------------------------------------
    @Slot()
    def start_downloads(self) -> None:
        pending = self._model.pending_tasks()
        if not pending:
            QMessageBox.information(
                self, "Nothing to download", "Tick at least one video that has not finished yet."
            )
            return
        if not self.path_edit.text():
            QMessageBox.warning(self, "No folder", "Choose where to save the downloads.")
            return

        destination = self._destination()
        preset = preset_by_label(self.quality_combo.currentText())
        self._model.reset_pending()
        self._run_tasks = list(pending)
        self._remaining = len(pending)
        self._pool.set_max_parallel(self.parallel_spin.value())
        self._set_running(True)
        self.status_message.emit(
            f"Downloading {len(pending)} videos, {self.parallel_spin.value()} at a time…"
        )
        self.log_message.emit(
            f"Queued {len(pending)} videos into {destination} "
            f"[{preset.label}, parallel={self.parallel_spin.value()}]"
        )

        numbered = self.subfolder_check.isChecked()
        for task in pending:
            # Each item is downloaded on its own, so yt-dlp cannot fill in
            # %(playlist_index)s -- bake the position we resolved into the name.
            template = (
                f"{task.index:03d} - %(title)s.%(ext)s" if numbered else "%(title)s.%(ext)s"
            )
            worker = DownloadWorker(task, destination, preset, output_template=template)
            worker.signals.started.connect(self._on_task_started)
            worker.signals.progress.connect(self._on_task_progress)
            worker.signals.finished.connect(self._on_task_finished)
            worker.signals.failed.connect(self._on_task_failed)
            worker.signals.cancelled.connect(self._on_task_cancelled)
            worker.signals.message.connect(self._on_task_message)
            self._pool.submit(worker)

    @Slot()
    def cancel_all(self) -> None:
        self._pool.cancel_all()
        self.status_message.emit("Cancelling remaining downloads…")
        self.log_message.emit("Cancel requested for all queued downloads.")

    @Slot(int)
    def _on_task_started(self, task_id: int) -> None:
        self._model.set_status(task_id, TaskStatus.FETCHING)

    @Slot(int, object)
    def _on_task_progress(self, task_id: int, progress: Progress) -> None:
        self._model.update_progress(task_id, progress)
        self._update_summary()

    @Slot(int, str)
    def _on_task_message(self, task_id: int, line: str) -> None:
        task = self._model.task_by_id(task_id)
        prefix = f"[{task.index}] " if task else ""
        self.log_message.emit(f"{prefix}{line}")

    @Slot(int, str)
    def _on_task_finished(self, task_id: int, path: str) -> None:
        task = self._model.task_by_id(task_id)
        if task is not None:
            task.output_path = path
        self._model.set_status(task_id, TaskStatus.COMPLETED)
        self.log_message.emit(f"Completed: {path}")
        self._task_done(task_id)

    @Slot(int, str)
    def _on_task_failed(self, task_id: int, error: str) -> None:
        self._model.set_status(task_id, TaskStatus.FAILED, error)
        self.log_message.emit(f"Failed: {error}")
        self._task_done(task_id)

    @Slot(int)
    def _on_task_cancelled(self, task_id: int) -> None:
        self._model.set_status(task_id, TaskStatus.CANCELLED)
        self._task_done(task_id)

    def _task_done(self, task_id: int) -> None:
        self._pool.release(task_id)
        self._remaining = max(0, self._remaining - 1)
        self._update_summary()
        if self._remaining == 0:
            self._on_all_done()

    def _on_all_done(self) -> None:
        self._set_running(False)
        done = self._model.count_by_status(TaskStatus.COMPLETED)
        failed = self._model.count_by_status(TaskStatus.FAILED)
        cancelled = self._model.count_by_status(TaskStatus.CANCELLED)
        summary = f"{done} downloaded"
        if failed:
            summary += f", {failed} failed"
        if cancelled:
            summary += f", {cancelled} cancelled"
        self.status_message.emit(summary)
        self.log_message.emit(f"Playlist run finished — {summary}.")
        QMessageBox.information(self, "Playlist finished", summary + ".")

    # ------------------------------------------------------------------
    # row context menu
    # ------------------------------------------------------------------
    def _show_context_menu(self, position) -> None:
        index = self.table.indexAt(position)
        task = self._model.task_at(index.row()) if index.isValid() else None
        if task is None:
            return

        menu = QMenu(self)
        if task.status.is_active or task.status is TaskStatus.QUEUED:
            menu.addAction("Cancel this download", lambda: self._pool.cancel(task.task_id))
        menu.addAction("Copy video URL", lambda: QGuiApplication.clipboard().setText(task.url))
        menu.addAction("Open in browser", lambda: QDesktopServices.openUrl(QUrl(task.url)))
        if task.output_path:
            menu.addAction(
                "Open containing folder",
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(task.output_path).parent))
                ),
            )
        if task.error:
            menu.addSeparator()
            menu.addAction("Copy error", lambda: QGuiApplication.clipboard().setText(task.error))
        menu.exec(self.table.viewport().mapToGlobal(position))

    def shutdown(self) -> None:
        self._pool.cancel_all()
        self._pool.wait_for_done(3000)
