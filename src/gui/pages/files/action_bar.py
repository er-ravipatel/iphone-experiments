"""
ActionBar — file operation buttons + indeterminate progress indicator.

Decoupled from business logic: it emits signals and exposes
set_state() so the page can drive enabled/disabled state.

Signals
-------
upload_requested()
download_requested()
delete_requested()
rename_requested()
mkdir_requested()
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QProgressBar, QLabel,
)
from PySide6.QtCore import Signal

log = logging.getLogger(__name__)


class ActionBar(QWidget):
    """
    Horizontal bar with five file-operation buttons and a progress indicator.

    The bar owns no state about the device or the current selection;
    the page calls set_state() after every relevant change.
    """

    upload_requested:   Signal = Signal()
    download_requested: Signal = Signal()
    delete_requested:   Signal = Signal()
    rename_requested:   Signal = Signal()
    mkdir_requested:    Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def set_state(
        self,
        *,
        has_device: bool,
        has_file_sel: bool,
        has_any_sel: bool,
        busy: bool,
    ) -> None:
        """
        Drive button enabled/disabled from the outside.

        Parameters
        ----------
        has_device    : a device is connected
        has_file_sel  : a *file* (not folder) row is selected
        has_any_sel   : any row (file or folder) is selected
        busy          : a transfer is in progress
        """
        can_act = has_device and not busy
        self._upload_btn.setEnabled(can_act)
        self._mkdir_btn.setEnabled(can_act)
        self._download_btn.setEnabled(can_act and has_file_sel)
        self._delete_btn.setEnabled(can_act and has_any_sel)
        self._rename_btn.setEnabled(can_act and has_any_sel)

    def show_progress(self, label: str) -> None:
        self._progress.show()
        self._op_lbl.setText(label)
        self._op_lbl.show()
        log.debug("ActionBar: progress shown — %s", label)

    def hide_progress(self) -> None:
        self._progress.hide()
        self._op_lbl.hide()
        self._op_lbl.setText("")

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._upload_btn   = self._make_btn("⬆ Upload",     self.upload_requested)
        self._download_btn = self._make_btn("⬇ Download",   self.download_requested)
        self._delete_btn   = self._make_btn("🗑 Delete",     self.delete_requested)
        self._rename_btn   = self._make_btn("✎ Rename",     self.rename_requested)
        self._mkdir_btn    = self._make_btn("+ New Folder", self.mkdir_requested)

        for btn in (self._upload_btn, self._download_btn, self._delete_btn,
                    self._rename_btn, self._mkdir_btn):
            layout.addWidget(btn)

        layout.addStretch()

        # Indeterminate spinner shown during operations
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(180)
        self._progress.setFixedHeight(16)
        self._progress.hide()
        layout.addWidget(self._progress)

        self._op_lbl = QLabel()
        self._op_lbl.setStyleSheet("color: #4fc3f7; font-size: 11px;")
        self._op_lbl.hide()
        layout.addWidget(self._op_lbl)

        # Start fully disabled; page will call set_state() on first device connect
        self.set_state(has_device=False, has_file_sel=False, has_any_sel=False, busy=False)

    @staticmethod
    def _make_btn(label: str, signal: Signal) -> QPushButton:
        btn = QPushButton(label)
        btn.clicked.connect(signal.emit)
        return btn
