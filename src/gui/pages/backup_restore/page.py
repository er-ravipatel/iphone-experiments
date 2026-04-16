"""
BackupRestorePage — Milestone 6 orchestrator.

Composes BackupTableWidget + OutputLog + ActionBar and manages workers.
Contains no rendering logic — delegates everything to child components.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
  abort_all()
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox,
)
from PySide6.QtCore import Qt

from ....device.info import DeviceInfo
from ..media._utils import open_system
from ..media.widgets import GripSplitter
from .backup_table import BackupTableWidget
from .output_log import OutputLog
from .action_bar import ActionBar
from .workers import (
    ListBackupsWorker, BackupWorker, RestoreWorker, DeleteBackupWorker,
    _DEFAULT_BACKUP_DIR,
)

log = logging.getLogger(__name__)


class BackupRestorePage(QWidget):
    """
    Top-level Backup & Restore page.

    Responsibilities
    ----------------
    - Own the page-level state machine (no_device / connecting / ready)
    - Spawn, park, and cancel background workers
    - React to child-component signals and issue commands back

    Everything else lives in child components.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._backup_dir: str  = _DEFAULT_BACKUP_DIR
        self._live_workers: set = set()

        self._list_worker:    ListBackupsWorker  | None = None
        self._backup_worker:  BackupWorker        | None = None
        self._restore_worker: RestoreWorker       | None = None
        self._delete_worker:  DeleteBackupWorker  | None = None

        self._build_ui()
        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # Title + status
        title_row = QHBoxLayout()
        title = QLabel("Backup & Restore")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("StatusLabel")
        title_row.addWidget(self._status_lbl)
        outer.addLayout(title_row)

        # Body: horizontal splitter (backup list | output log)
        self._splitter = GripSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(10)
        self._splitter.setChildrenCollapsible(False)

        self._backup_table = BackupTableWidget()
        self._backup_table.setMinimumWidth(280)
        self._backup_table.selection_changed.connect(self._on_backup_selected)
        self._splitter.addWidget(self._backup_table)

        self._output_log = OutputLog()
        self._output_log.setMinimumWidth(200)
        self._splitter.addWidget(self._output_log)

        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([320, 600])
        outer.addWidget(self._splitter, stretch=1)

        # Action bar
        self._action_bar = ActionBar()
        self._action_bar.backup_requested.connect(self._on_new_backup)
        self._action_bar.restore_requested.connect(self._on_restore)
        self._action_bar.delete_requested.connect(self._on_delete)
        self._action_bar.open_folder_requested.connect(self._on_open_folder)
        self._action_bar.cancel_requested.connect(self._on_cancel)
        outer.addWidget(self._action_bar)

    # ── State machine ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        log.debug("BackupRestorePage: show_no_device")
        self.abort_all()
        self._udid = None
        self._status_lbl.setText("No device connected")
        self._load_backups()   # backups are filesystem-only — still show them
        self._refresh_action_bar()

    def show_connecting(self) -> None:
        log.debug("BackupRestorePage: show_connecting")
        self.abort_all()
        self._udid = None
        self._status_lbl.setText("Connecting…")
        self._refresh_action_bar()

    def show_device(self, info: DeviceInfo) -> None:
        log.debug("BackupRestorePage: show_device udid=%s", info.udid)
        self._udid = info.udid
        self._status_lbl.setText(f"Connected: {info.name}")
        self._load_backups()
        self._refresh_action_bar()

    def abort_all(self) -> None:
        """Cancel all running workers and park them in _live_workers."""
        log.debug("BackupRestorePage: abort_all")
        for w in (self._backup_worker, self._restore_worker, self._delete_worker):
            if w is not None and w.isRunning():
                log.debug("BackupRestorePage: cancelling + parking %s", type(w).__name__)
                if hasattr(w, "cancel"):
                    w.cancel()
                self._live_workers.add(w)
                try:
                    w.finished.disconnect()
                    w.failed.disconnect()
                except RuntimeError:
                    pass
                w.finished.connect(lambda _w=w: self._live_workers.discard(_w))
                w.failed.connect(lambda _msg, _w=w: self._live_workers.discard(_w))
        self._backup_worker = self._restore_worker = self._delete_worker = None
        self._output_log.hide_progress()
        self._action_bar.clear_op_label()

    # ── Backup list ────────────────────────────────────────────────────────

    def _load_backups(self) -> None:
        """Spawn ListBackupsWorker to scan the local backup directory."""
        if self._list_worker and self._list_worker.isRunning():
            old = self._list_worker
            self._live_workers.add(old)
            try:
                old.finished.disconnect()
                old.failed.disconnect()
            except RuntimeError:
                pass
            old.finished.connect(lambda _p, _w=old: self._live_workers.discard(_w))
            old.failed.connect(lambda _m, _w=old: self._live_workers.discard(_w))

        w = ListBackupsWorker(self._backup_dir)
        self._list_worker = w
        self._live_workers.add(w)
        w.finished.connect(self._on_backups_loaded)
        w.failed.connect(self._on_backups_failed)
        w.finished.connect(lambda _p, _w=w: self._live_workers.discard(_w))
        w.failed.connect(lambda _m, _w=w: self._live_workers.discard(_w))
        w.start()

    def _on_backups_loaded(self, paths: list) -> None:
        log.debug("BackupRestorePage: backups loaded — %d entries", len(paths))
        self._backup_table.load_backups(paths)
        self._refresh_action_bar()

    def _on_backups_failed(self, msg: str) -> None:
        log.error("BackupRestorePage: backup list failed: %s", msg)
        self._backup_table.load_backups([])
        self._refresh_action_bar()

    # ── Action handlers ────────────────────────────────────────────────────

    def _on_new_backup(self) -> None:
        if not self._udid or self._is_busy():
            return
        log.debug("BackupRestorePage: starting backup")
        self._output_log.clear()
        self._action_bar.set_op_label("Starting backup…")

        w = BackupWorker(self._udid, self._backup_dir)
        self._backup_worker = w
        self._live_workers.add(w)
        w.line_ready.connect(self._output_log.append_line)
        w.progress.connect(self._output_log.set_progress)
        w.finished.connect(self._on_backup_finished)
        w.failed.connect(self._on_backup_failed)
        w.finished.connect(lambda _w=w: self._live_workers.discard(_w))
        w.failed.connect(lambda _m, _w=w: self._live_workers.discard(_w))
        w.start()
        self._refresh_action_bar()

    def _on_restore(self) -> None:
        backup_path = self._backup_table.selected_backup()
        if not backup_path or not self._udid or self._is_busy():
            return
        if not self._confirm_restore(backup_path):
            return
        log.debug("BackupRestorePage: starting restore from %s", backup_path)
        self._output_log.clear()
        self._action_bar.set_op_label("Starting restore…")

        w = RestoreWorker(self._udid, backup_path)
        self._restore_worker = w
        self._live_workers.add(w)
        w.line_ready.connect(self._output_log.append_line)
        w.progress.connect(self._output_log.set_progress)
        w.finished.connect(self._on_restore_finished)
        w.failed.connect(self._on_restore_failed)
        w.finished.connect(lambda _w=w: self._live_workers.discard(_w))
        w.failed.connect(lambda _m, _w=w: self._live_workers.discard(_w))
        w.start()
        self._refresh_action_bar()

    def _on_delete(self) -> None:
        backup_path = self._backup_table.selected_backup()
        if not backup_path or self._is_busy():
            return
        reply = QMessageBox.question(
            self,
            "Delete Backup",
            f"Permanently delete this backup?\n\n{backup_path}\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return
        log.debug("BackupRestorePage: deleting %s", backup_path)
        self._action_bar.set_op_label(f"Deleting {backup_path.name}…")

        w = DeleteBackupWorker(backup_path)
        self._delete_worker = w
        self._live_workers.add(w)
        w.finished.connect(self._on_delete_finished)
        w.failed.connect(self._on_delete_failed)
        w.finished.connect(lambda _w=w: self._live_workers.discard(_w))
        w.failed.connect(lambda _m, _w=w: self._live_workers.discard(_w))
        w.start()
        self._refresh_action_bar()

    def _on_cancel(self) -> None:
        log.debug("BackupRestorePage: cancel requested")
        for w in (self._backup_worker, self._restore_worker):
            if w is not None and w.isRunning():
                w.cancel()
        self._action_bar.set_op_label("Cancelling…")

    def _on_open_folder(self) -> None:
        """Open the selected backup's parent directory in the system file explorer."""
        backup_path = self._backup_table.selected_backup()
        if backup_path is None:
            return
        log.debug("BackupRestorePage: opening folder %s", backup_path)
        open_system(str(backup_path))

    # ── Operation completion handlers ──────────────────────────────────────

    def _on_backup_finished(self) -> None:
        log.debug("BackupRestorePage: backup finished")
        self._backup_worker = None
        self._output_log.hide_progress()
        self._action_bar.set_op_label("Backup complete.")
        self._status_lbl.setText("Backup completed successfully.")
        self._load_backups()
        self._refresh_action_bar()

    def _on_backup_failed(self, msg: str) -> None:
        log.error("BackupRestorePage: backup failed: %s", msg)
        self._backup_worker = None
        self._output_log.hide_progress()
        self._action_bar.set_op_label(f"Failed: {msg[:60]}")
        self._status_lbl.setText(f"Backup failed: {msg}")
        self._refresh_action_bar()

    def _on_restore_finished(self) -> None:
        log.debug("BackupRestorePage: restore finished")
        self._restore_worker = None
        self._output_log.hide_progress()
        self._action_bar.set_op_label("Restore complete.")
        self._status_lbl.setText("Restore completed successfully.")
        self._refresh_action_bar()

    def _on_restore_failed(self, msg: str) -> None:
        log.error("BackupRestorePage: restore failed: %s", msg)
        self._restore_worker = None
        self._output_log.hide_progress()
        self._action_bar.set_op_label(f"Failed: {msg[:60]}")
        self._status_lbl.setText(f"Restore failed: {msg}")
        self._refresh_action_bar()

    def _on_delete_finished(self) -> None:
        log.debug("BackupRestorePage: delete finished")
        self._delete_worker = None
        self._backup_table.remove_selected()
        self._action_bar.set_op_label("")
        self._status_lbl.setText("Backup deleted.")
        self._load_backups()
        self._refresh_action_bar()

    def _on_delete_failed(self, msg: str) -> None:
        log.error("BackupRestorePage: delete failed: %s", msg)
        self._delete_worker = None
        self._action_bar.clear_op_label()
        self._status_lbl.setText(f"Delete failed: {msg}")
        QMessageBox.critical(self, "Delete Failed", msg)
        self._refresh_action_bar()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _confirm_restore(self, backup_path: Path) -> bool:
        """Show a prominent destructive-action warning. Returns True only on confirm."""
        dlg = QMessageBox(self)
        dlg.setIcon(QMessageBox.Warning)
        dlg.setWindowTitle("Confirm Restore — This is Destructive")
        dlg.setText(
            "<b>Restore will overwrite data on the connected iPhone.</b><br><br>"
            f"Backup: <code>{backup_path.name}</code><br>"
            f"Path: <code>{backup_path}</code><br><br>"
            "Current app data, settings, and files on the device may be replaced.<br>"
            "<b>This cannot be undone.</b>"
        )
        dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        dlg.setDefaultButton(QMessageBox.Cancel)
        yes_btn = dlg.button(QMessageBox.Yes)
        yes_btn.setText("Yes, Restore Now")
        yes_btn.setStyleSheet("background: #b71c1c; color: white; font-weight: bold;")
        return dlg.exec() == QMessageBox.Yes

    def _is_busy(self) -> bool:
        return any(
            w is not None and w.isRunning()
            for w in (self._backup_worker, self._restore_worker, self._delete_worker)
        )

    def _on_backup_selected(self, path) -> None:
        self._refresh_action_bar()

    def _refresh_action_bar(self) -> None:
        self._action_bar.set_state(
            has_device=self._udid is not None,
            has_backup_sel=self._backup_table.selected_backup() is not None,
            busy=self._is_busy(),
        )
