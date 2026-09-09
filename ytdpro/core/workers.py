"""Qt-side concurrency: runnables that drive the engine off the GUI thread.

Every blocking yt-dlp call happens inside a ``QRunnable`` on a ``QThreadPool``.
Results travel back as signals, which Qt delivers on the GUI thread, so no widget
is ever touched from a worker.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from . import engine
from .formats import QualityPreset
from .tasks import DownloadTask, Progress, TaskStatus

# yt-dlp fires its progress hook far faster than a UI can usefully repaint.
PROGRESS_INTERVAL_S = 0.12


class DownloadSignals(QObject):
    started = Signal(int)  # task_id
    progress = Signal(int, object)  # task_id, Progress
    finished = Signal(int, str)  # task_id, output path
    failed = Signal(int, str)  # task_id, error message
    cancelled = Signal(int)  # task_id
    message = Signal(int, str)  # task_id, log line


class DownloadWorker(QRunnable):
    """Downloads one task, reporting progress through :class:`DownloadSignals`."""

    def __init__(
        self,
        task: DownloadTask,
        destination: Path,
        preset: QualityPreset,
        *,
        cancel_event: threading.Event | None = None,
        concurrent_fragments: int = 4,
        output_template: str = "%(title)s.%(ext)s",
    ) -> None:
        super().__init__()
        self.signals = DownloadSignals()
        self.task = task
        self.destination = destination
        self.preset = preset
        self.cancel_event = cancel_event or threading.Event()
        self.concurrent_fragments = concurrent_fragments
        self.output_template = output_template
        self._last_emit = 0.0
        # Python keeps the reference (DownloadPool._workers), so Qt must not
        # delete the C++ object out from under a later cancel() call.
        self.setAutoDelete(False)

    def cancel(self) -> None:
        self.cancel_event.set()

    def _on_progress(self, progress: Progress) -> None:
        now = time.monotonic()
        # Always let a phase change (e.g. downloading -> merging) through.
        throttled = now - self._last_emit < PROGRESS_INTERVAL_S
        if progress.status is TaskStatus.DOWNLOADING and throttled:
            return
        self._last_emit = now
        self.signals.progress.emit(self.task.task_id, progress)

    def _on_log(self, line: str) -> None:
        self.signals.message.emit(self.task.task_id, line)

    @Slot()
    def run(self) -> None:
        task_id = self.task.task_id
        # A task cancelled while still queued never starts work.
        if self.cancel_event.is_set():
            self.signals.cancelled.emit(task_id)
            return

        self.signals.started.emit(task_id)
        self.signals.progress.emit(task_id, Progress(status=TaskStatus.FETCHING))
        try:
            path = engine.download(
                self.task,
                self.destination,
                self.preset,
                cancel_event=self.cancel_event,
                on_progress=self._on_progress,
                log_callback=self._on_log,
                concurrent_fragments=self.concurrent_fragments,
                output_template=self.output_template,
            )
        except engine.DownloadCancelled:
            self.signals.cancelled.emit(task_id)
        except Exception as exc:
            self.signals.failed.emit(task_id, str(exc))
        else:
            self.signals.finished.emit(task_id, path)


class PlaylistSignals(QObject):
    ready = Signal(str, object)  # playlist title, list[DownloadTask]
    failed = Signal(str)
    message = Signal(str)


class PlaylistFetchWorker(QRunnable):
    """Resolves a playlist URL into tasks without blocking the GUI."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.signals = PlaylistSignals()
        self.url = url

    @Slot()
    def run(self) -> None:
        try:
            title, tasks = engine.fetch_playlist(self.url, log_callback=self.signals.message.emit)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.ready.emit(title, tasks)


class VideoInfoSignals(QObject):
    ready = Signal(object)  # yt-dlp info dict
    failed = Signal(str)
    message = Signal(str)


class VideoInfoWorker(QRunnable):
    """Resolves a single video URL's metadata."""

    def __init__(self, url: str) -> None:
        super().__init__()
        self.signals = VideoInfoSignals()
        self.url = url

    @Slot()
    def run(self) -> None:
        try:
            info = engine.fetch_video_info(self.url, log_callback=self.signals.message.emit)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.ready.emit(info)


class DownloadPool:
    """A thread pool whose width is the user's 'max parallel downloads' setting.

    Workers submitted beyond the current width wait in the pool's queue, so a
    500-video playlist can be queued at once without spawning 500 threads.
    """

    def __init__(self, max_parallel: int = 3) -> None:
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(max(1, max_parallel))
        self._workers: dict[int, DownloadWorker] = {}

    @property
    def max_parallel(self) -> int:
        return self._pool.maxThreadCount()

    def set_max_parallel(self, value: int) -> None:
        """Widen or narrow the pool. Downloads already running are left alone."""
        self._pool.setMaxThreadCount(max(1, value))

    @property
    def active_count(self) -> int:
        return self._pool.activeThreadCount()

    def submit(self, worker: DownloadWorker) -> None:
        self._workers[worker.task.task_id] = worker
        self._pool.start(worker)

    def cancel(self, task_id: int) -> None:
        worker = self._workers.get(task_id)
        if worker is not None:
            worker.cancel()

    def cancel_all(self) -> None:
        for worker in self._workers.values():
            worker.cancel()

    def release(self, task_id: int) -> None:
        """Drop a finished worker so its signals object can be collected."""
        self._workers.pop(task_id, None)

    def wait_for_done(self, timeout_ms: int = 5000) -> bool:
        return self._pool.waitForDone(timeout_ms)
