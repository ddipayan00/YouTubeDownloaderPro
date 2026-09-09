"""Table model and progress delegate for the playlist queue."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..core.tasks import (
    DownloadTask,
    Progress,
    TaskStatus,
    format_bytes,
    format_duration,
    format_speed,
)
from .theme import Palette

PROGRESS_ROLE = Qt.ItemDataRole.UserRole + 1
STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
TASK_ID_ROLE = Qt.ItemDataRole.UserRole + 3

COL_CHECK = 0
COL_INDEX = 1
COL_TITLE = 2
COL_LENGTH = 3
COL_STATUS = 4
COL_PROGRESS = 5
COL_SIZE = 6
COL_SPEED = 7
COL_ETA = 8

HEADERS = ("", "#", "Title", "Length", "Status", "Progress", "Size", "Speed", "ETA")


class PlaylistModel(QAbstractTableModel):
    """Holds the playlist's tasks; every cell is derived from a DownloadTask."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tasks: list[DownloadTask] = []
        self._row_by_id: dict[int, int] = {}
        self._status_colors: dict[TaskStatus, QColor] = {}

    # -- palette -----------------------------------------------------
    def set_palette(self, palette: Palette) -> None:
        self._status_colors = {
            TaskStatus.QUEUED: QColor(palette.text_muted),
            TaskStatus.FETCHING: QColor(palette.warning),
            TaskStatus.DOWNLOADING: QColor(palette.text),
            TaskStatus.MERGING: QColor(palette.warning),
            TaskStatus.COMPLETED: QColor(palette.success),
            TaskStatus.FAILED: QColor(palette.danger),
            TaskStatus.CANCELLED: QColor(palette.text_muted),
        }
        if self._tasks:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self.rowCount() - 1, self.columnCount() - 1),
            )

    # -- content -----------------------------------------------------
    @property
    def tasks(self) -> list[DownloadTask]:
        return self._tasks

    def set_tasks(self, tasks: list[DownloadTask]) -> None:
        self.beginResetModel()
        self._tasks = tasks
        self._row_by_id = {task.task_id: row for row, task in enumerate(tasks)}
        self.endResetModel()

    def clear(self) -> None:
        self.set_tasks([])

    def task_at(self, row: int) -> DownloadTask | None:
        return self._tasks[row] if 0 <= row < len(self._tasks) else None

    def task_by_id(self, task_id: int) -> DownloadTask | None:
        row = self._row_by_id.get(task_id)
        return self._tasks[row] if row is not None else None

    def selected_tasks(self) -> list[DownloadTask]:
        return [t for t in self._tasks if t.selected]

    def pending_tasks(self) -> list[DownloadTask]:
        """Selected items that have not already finished successfully."""
        return [t for t in self._tasks if t.selected and t.status is not TaskStatus.COMPLETED]

    def count_by_status(self, status: TaskStatus) -> int:
        return sum(1 for t in self._tasks if t.status is status)

    def set_all_selected(self, selected: bool) -> None:
        if not self._tasks:
            return
        for task in self._tasks:
            task.selected = selected
        self.dataChanged.emit(
            self.index(0, COL_CHECK),
            self.index(self.rowCount() - 1, COL_CHECK),
            [Qt.ItemDataRole.CheckStateRole],
        )

    # -- updates from workers ---------------------------------------
    def _emit_row(self, row: int) -> None:
        self.dataChanged.emit(self.index(row, COL_STATUS), self.index(row, COL_ETA))

    def update_progress(self, task_id: int, progress: Progress) -> None:
        row = self._row_by_id.get(task_id)
        if row is None:
            return
        task = self._tasks[row]
        # Later phases (merging) report no size; keep the figure we already have.
        if not progress.total_bytes and task.progress.total_bytes:
            progress.total_bytes = task.progress.total_bytes
        task.progress = progress
        task.status = progress.status
        self._emit_row(row)

    def set_status(self, task_id: int, status: TaskStatus, error: str = "") -> None:
        row = self._row_by_id.get(task_id)
        if row is None:
            return
        task = self._tasks[row]
        task.status = status
        task.error = error
        if status is TaskStatus.COMPLETED:
            task.progress.percent = 100.0
            task.progress.speed = 0.0
            task.progress.eta = 0
        elif status in (TaskStatus.CANCELLED, TaskStatus.FAILED):
            task.progress.speed = 0.0
            task.progress.eta = 0
        self._emit_row(row)

    def reset_pending(self) -> None:
        """Put unfinished tasks back to Queued before a new run."""
        for row, task in enumerate(self._tasks):
            if task.status is not TaskStatus.COMPLETED:
                task.status = TaskStatus.QUEUED
                task.error = ""
                task.progress = Progress()
                self._emit_row(row)

    # -- QAbstractTableModel ----------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008 (Qt signature)
        return 0 if parent.isValid() else len(self._tasks)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008 (Qt signature)
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == COL_CHECK:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        task = self._tasks[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.CheckStateRole and column == COL_CHECK:
            return Qt.CheckState.Checked if task.selected else Qt.CheckState.Unchecked

        if role == PROGRESS_ROLE:
            return task.progress.percent
        if role == STATUS_ROLE:
            return task.status
        if role == TASK_ID_ROLE:
            return task.task_id

        if role == Qt.ItemDataRole.ToolTipRole:
            if task.error:
                return f"{task.display_title}\n\n{task.error}"
            return task.display_title

        if role == Qt.ItemDataRole.ForegroundRole and column == COL_STATUS:
            return self._status_colors.get(task.status)

        if role == Qt.ItemDataRole.TextAlignmentRole and column in (
            COL_INDEX,
            COL_LENGTH,
            COL_SIZE,
            COL_SPEED,
            COL_ETA,
        ):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if column == COL_INDEX:
            return str(task.index)
        if column == COL_TITLE:
            return task.display_title
        if column == COL_LENGTH:
            return format_duration(task.duration)
        if column == COL_STATUS:
            return "Failed" if task.error else task.status.value
        if column == COL_SIZE:
            return format_bytes(task.progress.total_bytes)
        if column == COL_SPEED:
            return format_speed(task.progress.speed) if task.status.is_active else "—"
        if column == COL_ETA:
            return format_duration(task.progress.eta) if task.status.is_active else "—"
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role == Qt.ItemDataRole.CheckStateRole and index.column() == COL_CHECK:
            task = self._tasks[index.row()]
            task.selected = Qt.CheckState(value) == Qt.CheckState.Checked
            self.dataChanged.emit(index, index, [role])
            return True
        return False


class ProgressDelegate(QStyledItemDelegate):
    """Paints the Progress column as a slim rounded bar with a percentage."""

    def __init__(self, palette: Palette, parent=None) -> None:
        super().__init__(parent)
        self._palette = palette

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        percent = index.data(PROGRESS_ROLE)
        status = index.data(STATUS_ROLE)
        if percent is None:
            super().paint(painter, option, index)
            return

        p = self._palette
        fill_color = QColor(p.accent)
        if status is TaskStatus.COMPLETED:
            fill_color = QColor(p.success)
            percent = 100.0
        elif status is TaskStatus.FAILED:
            fill_color = QColor(p.danger)
        elif status is TaskStatus.CANCELLED:
            fill_color = QColor(p.text_muted)
        elif status is TaskStatus.MERGING:
            fill_color = QColor(p.warning)

        rect = option.rect.adjusted(8, 0, -8, 0)
        bar_height = 8
        bar = QRectF(
            rect.left(),
            rect.center().y() - bar_height / 2 + 1,
            max(rect.width() - 46, 10),
            bar_height,
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QColor(p.track))
        painter.drawRoundedRect(bar, 4, 4)

        ratio = max(0.0, min(float(percent), 100.0)) / 100.0
        if ratio > 0:
            filled = QRectF(bar)
            filled.setWidth(bar.width() * ratio)
            painter.setBrush(fill_color)
            painter.drawRoundedRect(filled, 4, 4)

        painter.setPen(QColor(p.text_muted))
        text_rect = option.rect.adjusted(int(bar.width()) + 12, 0, -6, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{ratio * 100:.0f}%",
        )
        painter.restore()
