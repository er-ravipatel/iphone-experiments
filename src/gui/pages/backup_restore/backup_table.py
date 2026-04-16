"""
BackupTableWidget — left-panel widget showing local iPhone backups.

Reads the filesystem directly; requires no device connection.
Reusable in any page that needs to display a list of local backups.

Signals
-------
selection_changed(object)  — emits Path of selected backup, or None.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from .workers import _dir_size_bytes

log = logging.getLogger(__name__)

_COL_DATE = 0
_COL_UDID = 1
_COL_SIZE = 2


def _fmt_size(n: int) -> str:
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


class BackupTableWidget(QWidget):
    """
    Displays local backup directories as a sortable three-column table.

    The widget owns no business logic — it emits signals and exposes
    a simple API for the page to drive.
    """

    selection_changed: Signal = Signal(object)   # Path | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_backups(self, paths: list[Path]) -> None:
        """Populate the table from a pre-scanned list of backup Paths."""
        log.debug("BackupTableWidget: loading %d backups", len(paths))
        self._paths = list(paths)

        # Clear without firing selection signal
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(0)
        self._tbl.blockSignals(False)

        if not paths:
            self._render_placeholder()
            self.selection_changed.emit(None)
            return

        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(paths))
        for row, p in enumerate(paths):
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size  = _fmt_size(_dir_size_bytes(p))
            udid  = p.name

            date_item = QTableWidgetItem(mtime)
            date_item.setData(Qt.UserRole, p)   # store Path on date column
            date_item.setForeground(QColor("#cccccc"))

            udid_item = QTableWidgetItem(udid)
            udid_item.setForeground(QColor("#aaaaaa"))

            size_item = QTableWidgetItem(size)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor("#888888"))

            self._tbl.setItem(row, _COL_DATE, date_item)
            self._tbl.setItem(row, _COL_UDID, udid_item)
            self._tbl.setItem(row, _COL_SIZE, size_item)
            self._tbl.setRowHeight(row, 30)

        self._tbl.setSortingEnabled(True)
        self.selection_changed.emit(None)
        log.debug("BackupTableWidget: rendered %d rows", len(paths))

    def clear(self) -> None:
        """Clear all rows and emit selection_changed(None)."""
        self._tbl.blockSignals(True)
        self._tbl.setRowCount(0)
        self._paths = []
        self._tbl.blockSignals(False)
        self.selection_changed.emit(None)

    def selected_backup(self) -> Path | None:
        """Return the Path of the currently selected backup, or None."""
        item = self._tbl.item(self._tbl.currentRow(), _COL_DATE)
        if item is None:
            return None
        val = item.data(Qt.UserRole)
        return val if isinstance(val, Path) else None

    def remove_selected(self) -> None:
        """Remove the currently selected row (call after successful delete)."""
        row = self._tbl.currentRow()
        if row >= 0:
            self._tbl.removeRow(row)
        self.selection_changed.emit(None)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel("LOCAL BACKUPS")
        lbl.setObjectName("SectionLabel")
        layout.addWidget(lbl)

        self._tbl = QTableWidget(0, 3)
        self._tbl.setHorizontalHeaderLabels(["Date", "UDID", "Size"])
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(_COL_DATE, QHeaderView.Fixed)
        hdr.setSectionResizeMode(_COL_UDID, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_SIZE, QHeaderView.Fixed)
        self._tbl.setColumnWidth(_COL_DATE, 130)
        self._tbl.setColumnWidth(_COL_SIZE, 80)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setShowGrid(False)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setSortingEnabled(True)
        self._tbl.setStyleSheet(
            "QTableWidget { background: #111; alternate-background-color: #161616; "
            "selection-background-color: #1e3a4a; border: 1px solid #222; border-radius: 6px; }"
            "QHeaderView::section { background: #1a1a1a; color: #777; font-size: 11px; "
            "padding: 6px 8px; border: none; border-bottom: 1px solid #222; }"
        )
        self._tbl.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._tbl, stretch=1)

    def _render_placeholder(self) -> None:
        self._tbl.setRowCount(1)
        item = QTableWidgetItem("No backups found")
        item.setForeground(QColor("#555555"))
        item.setFlags(Qt.ItemIsEnabled)   # not selectable
        font = QFont()
        font.setItalic(True)
        item.setFont(font)
        self._tbl.setItem(0, _COL_DATE, item)
        self._tbl.setSpan(0, _COL_DATE, 1, 3)
        self._tbl.setRowHeight(0, 30)

    # ── Qt event forwarding ────────────────────────────────────────────────

    def _on_selection_changed(self) -> None:
        sel = self.selected_backup()
        log.debug("BackupTableWidget: selection → %s", sel)
        self.selection_changed.emit(sel)
