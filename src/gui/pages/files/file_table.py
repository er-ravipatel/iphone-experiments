"""
FileTableWidget — reusable sortable file-list table.

Shows Name / Type / Size columns with folders first.
Emits signals for navigation and selection; no business logic inside.

Signals
-------
entry_activated(dict)       — double-click on any row.
selection_changed(object)   — selected entry dict, or None if nothing selected.
"""
from __future__ import annotations

import logging
from pathlib import PurePosixPath

from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

log = logging.getLogger(__name__)

_COL_NAME = 0
_COL_TYPE = 1
_COL_SIZE = 2

_DIR_ICON  = "📁"
_FILE_ICON = "📄"


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


class FileTableWidget(QTableWidget):
    """
    A sortable, signal-driven file-list widget.

    Reusable in any page that needs to display a directory listing.
    """

    entry_activated:  Signal = Signal(dict)   # double-click
    selection_changed: Signal = Signal(object)  # dict | None

    def __init__(self, parent=None) -> None:
        super().__init__(0, 3, parent)
        self._entries: list[dict] = []
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def load_entries(self, entries: list[dict]) -> None:
        """
        Populate the table.

        Parameters
        ----------
        entries : list[dict]
            Each dict must have: name (str), path (str), is_dir (bool), size (int).
        """
        sorted_entries = self._sort(entries)
        self._entries = sorted_entries
        self._render()
        log.debug("FileTableWidget: loaded %d entries", len(sorted_entries))

    def clear_entries(self) -> None:
        # Block signals while clearing so _on_selection_changed doesn't fire
        # with an empty _entries list (QTableWidget emits itemSelectionChanged
        # when rows are removed even if nothing was selected).
        self.blockSignals(True)
        self._entries = []
        self.setRowCount(0)
        self.blockSignals(False)

    def selected_entry(self) -> dict | None:
        """Return the currently selected entry dict, or None."""
        items = self.selectedItems()
        if not items:
            return None
        row = self.row(items[0])
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    # ── Sorting strategy ───────────────────────────────────────────────────

    @staticmethod
    def _sort(entries: list[dict]) -> list[dict]:
        """Folders first, then files; each group sorted alphabetically."""
        dirs  = sorted([e for e in entries if e["is_dir"]],
                       key=lambda e: e["name"].lower())
        files = sorted([e for e in entries if not e["is_dir"]],
                       key=lambda e: e["name"].lower())
        return dirs + files

    # ── Rendering ──────────────────────────────────────────────────────────

    def _render(self) -> None:
        self.setRowCount(len(self._entries))
        for row, e in enumerate(self._entries):
            icon = _DIR_ICON if e["is_dir"] else _FILE_ICON

            name_item = QTableWidgetItem(f"{icon}  {e['name']}")
            name_item.setData(Qt.UserRole, row)

            type_item = QTableWidgetItem("DIR" if e["is_dir"] else "FILE")
            type_item.setForeground(
                QColor("#4fc3f7") if e["is_dir"] else QColor("#aaaaaa")
            )
            type_item.setTextAlignment(Qt.AlignCenter)

            size_str  = "" if e["is_dir"] else _fmt_size(e["size"])
            size_item = QTableWidgetItem(size_str)
            size_item.setForeground(QColor("#888888"))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.setItem(row, _COL_NAME, name_item)
            self.setItem(row, _COL_TYPE, type_item)
            self.setItem(row, _COL_SIZE, size_item)
            self.setRowHeight(row, 30)

    # ── UI setup ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setHorizontalHeaderLabels(["Name", "Type", "Size"])
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)
        hdr.setSectionResizeMode(_COL_TYPE, QHeaderView.Fixed)
        hdr.setSectionResizeMode(_COL_SIZE, QHeaderView.Fixed)
        self.setColumnWidth(_COL_TYPE, 60)
        self.setColumnWidth(_COL_SIZE, 100)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setStyleSheet(
            "QTableWidget { background: #111; alternate-background-color: #161616; "
            "selection-background-color: #1e3a4a; border: 1px solid #222; border-radius: 6px; }"
            "QHeaderView::section { background: #1a1a1a; color: #777; font-size: 11px; "
            "padding: 6px 8px; border: none; border-bottom: 1px solid #222; }"
        )

        # Wire Qt signals to our own typed signals
        self.doubleClicked.connect(self._on_double_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    # ── Qt event forwarding ────────────────────────────────────────────────

    def _on_double_clicked(self, index) -> None:
        row = index.row()
        if 0 <= row < len(self._entries):
            log.debug("FileTableWidget: activated row %d (%s)", row, self._entries[row]["name"])
            self.entry_activated.emit(self._entries[row])

    def _on_selection_changed(self) -> None:
        entry = self.selected_entry()
        log.debug("FileTableWidget: selection → %s", entry["name"] if entry else None)
        self.selection_changed.emit(entry)
