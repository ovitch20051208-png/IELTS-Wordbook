from datetime import datetime
import traceback

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QLabel, QTableView, QHeaderView, QAbstractItemView


def local_time(stamp):
    if not stamp:
        return "—"
    try:
        return datetime.fromisoformat(stamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return stamp


def label(text="", style=""):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if style:
        widget.setStyleSheet(style)
    return widget


def button(text, callback, kind=""):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if kind:
        widget.setProperty("kind", kind)
    widget.clicked.connect(callback)
    return widget


class TableModel(QAbstractTableModel):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.columns = columns  # (title, field) pairs
        self.rows = []

    def replace(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.columns[index.column()][1]
        value = row.get(key, "") if isinstance(row, dict) else getattr(row, key, "")
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            if key.endswith("_at"):
                return local_time(value)
            if key == "ipa" and not value:
                return "音标待补充"
            if key == "pos" and not isinstance(row, dict):
                return row.pos_display
            return str(value) if value is not None else "—"
        if role == Qt.ItemDataRole.ForegroundRole and key == "status":
            return QColor({"已掌握": "#127658", "有一点印象": "#a56509", "完全记不得": "#c34343"}.get(value, "#64748b"))
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section][0]
        return None


def table(model):
    view = QTableView()
    view.setModel(model)
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    view.setAlternatingRowColors(True)
    view.setWordWrap(False)
    view.verticalHeader().setVisible(False)
    view.verticalHeader().setDefaultSectionSize(40)
    view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    view.horizontalHeader().setStretchLastSection(True)
    return view


class Job(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.succeeded.emit(self.function())
        except Exception as exc:
            import logging
            logging.error("Background operation failed\n%s", traceback.format_exc())
            self.failed.emit(str(exc))
