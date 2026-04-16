"""
ActionBar — bottom action bar for the Backup & Restore page.

Decoupled from all business logic: emits signals and exposes set_state()
so the page drives enabled/disabled state from the outside.

Signals
-------
backup_requested()
restore_requested()
delete_requested()
cancel_requested()
open_folder_requested()
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal

log = logging.getLogger(__name__)

_CANCEL_STYLE_ON  = "background: #b71c1c; color: white; font-weight: bold;"
_CANCEL_STYLE_OFF = ""


class ActionBar(QWidget):
    """
    Four operation buttons (New Backup / Restore / Delete / Cancel) plus
    a plain-text operation label.  The Cancel button is styled red when
    active to signal its destructive intent.

    The bar owns zero state about the device or current selection;
    the page calls set_state() after every relevant change.
    """

    backup_requested:       Signal = Signal()
    restore_requested:      Signal = Signal()
    delete_requested:       Signal = Signal()
    cancel_requested:       Signal = Signal()
    open_folder_requested:  Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def set_state(
        self,
        *,
        has_device: bool,
        has_backup_sel: bool,
        busy: bool,
    ) -> None:
        """
        Drive all button enabled/disabled states.

        Parameters
        ----------
        has_device     : a device is currently connected
        has_backup_sel : a backup row is selected in the table
        busy           : a backup/restore/delete operation is running
        """
        can_act = not busy

        self._backup_btn.setEnabled(has_device and can_act)
        self._restore_btn.setEnabled(has_device and has_backup_sel and can_act)
        self._delete_btn.setEnabled(has_backup_sel and can_act)   # local-only, no device
        self._open_folder_btn.setEnabled(has_backup_sel)          # always, regardless of busy
        self._cancel_btn.setEnabled(busy)
        self._cancel_btn.setStyleSheet(_CANCEL_STYLE_ON if busy else _CANCEL_STYLE_OFF)

    def set_op_label(self, text: str) -> None:
        """Update the operation status label (e.g. '52% Backing up…')."""
        self._op_lbl.setText(text)

    def clear_op_label(self) -> None:
        """Clear the operation label."""
        self._op_lbl.setText("")

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._backup_btn      = self._make_btn("+ New Backup",  self.backup_requested)
        self._restore_btn     = self._make_btn("↩ Restore",     self.restore_requested)
        self._delete_btn      = self._make_btn("🗑 Delete",      self.delete_requested)
        self._open_folder_btn = self._make_btn("📂 Open Folder", self.open_folder_requested)
        self._cancel_btn      = self._make_btn("✕ Cancel",      self.cancel_requested)

        for btn in (self._backup_btn, self._restore_btn,
                    self._delete_btn, self._open_folder_btn, self._cancel_btn):
            layout.addWidget(btn)

        layout.addStretch()

        self._op_lbl = QLabel()
        self._op_lbl.setStyleSheet("color: #4fc3f7; font-size: 11px;")
        layout.addWidget(self._op_lbl)

        # Start fully disabled; page calls set_state() on first device connect
        self.set_state(has_device=False, has_backup_sel=False, busy=False)

    @staticmethod
    def _make_btn(label: str, signal: Signal) -> QPushButton:
        btn = QPushButton(label)
        btn.clicked.connect(signal.emit)
        return btn
