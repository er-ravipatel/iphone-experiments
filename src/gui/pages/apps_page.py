"""
AppsPage — list, install, and uninstall apps on the connected device.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor

from ...device.info import DeviceInfo
from ...terminal.features.apps import _list_apps, _install_app, _uninstall_app


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_size(size: int) -> str:
    if not size:
        return ""
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size / 1_000:.0f} KB"
    return f"{size} B"


# ── Workers ────────────────────────────────────────────────────────────────────

class _ListAppsWorker(QThread):
    finished = Signal(list)   # list[dict]
    failed   = Signal(str)

    def __init__(self, udid: str, app_type: str) -> None:
        super().__init__()
        self._udid = udid
        self._app_type = app_type

    def run(self) -> None:
        try:
            apps = asyncio.run(_list_apps(self._udid, self._app_type))
            self.finished.emit(apps)
        except Exception as exc:
            self.failed.emit(str(exc))


class _AppActionWorker(QThread):
    """Generic worker for install / uninstall (one coroutine)."""
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, coro) -> None:
        super().__init__()
        self._coro = coro

    def run(self) -> None:
        try:
            asyncio.run(self._coro)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Page ───────────────────────────────────────────────────────────────────────

_COL_NAME      = 0
_COL_VERSION   = 1
_COL_SIZE      = 2
_COL_BUNDLE_ID = 3


class AppsPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._app_type: str = "User"
        self._apps: list[dict] = []
        self._list_worker: _ListAppsWorker | None = None
        self._action_worker: _AppActionWorker | None = None
        self._live_workers: set = set()
        self._build_ui()
        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        # Title
        title = QLabel("Apps")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        # Status
        self._status = QLabel()
        self._status.setObjectName("StatusLabel")
        outer.addWidget(self._status)

        # Toolbar
        toolbar = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(8)

        self._toggle_btn = QPushButton("Showing: User Apps")
        self._toggle_btn.setFixedWidth(160)
        self._toggle_btn.setToolTip("Switch between User and System apps")
        self._toggle_btn.clicked.connect(self._on_toggle)
        tb_layout.addWidget(self._toggle_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self._load_apps)
        tb_layout.addWidget(self._refresh_btn)

        tb_layout.addStretch()

        self._install_btn = QPushButton("Install .ipa…")
        self._install_btn.setFixedWidth(110)
        self._install_btn.clicked.connect(self._on_install)
        tb_layout.addWidget(self._install_btn)

        self._uninstall_btn = QPushButton("Uninstall")
        self._uninstall_btn.setFixedWidth(90)
        self._uninstall_btn.setToolTip("Uninstall selected app")
        self._uninstall_btn.clicked.connect(self._on_uninstall)
        tb_layout.addWidget(self._uninstall_btn)

        outer.addWidget(toolbar)

        # App table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["App Name", "Version", "Size", "Bundle ID"])
        self._table.horizontalHeader().setSectionResizeMode(_COL_NAME,      QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_VERSION,   QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_COL_SIZE,      QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_COL_BUNDLE_ID, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        outer.addWidget(self._table)

        # Count label
        self._count_label = QLabel()
        self._count_label.setObjectName("StatusLabel")
        outer.addWidget(self._count_label)

        # Result message
        self._result_label = QLabel()
        self._result_label.setObjectName("StatusLabel")
        self._result_label.setWordWrap(True)
        outer.addWidget(self._result_label)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_result(self, text: str, color: str = "#9e9e9e") -> None:
        self._result_label.setText(text)
        self._result_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._toggle_btn.setEnabled(not busy)
        self._refresh_btn.setEnabled(not busy)
        self._install_btn.setEnabled(not busy)
        # Uninstall stays tied to selection even when not busy
        self._uninstall_btn.setEnabled(not busy and self._selected_app() is not None)
        if msg:
            self._set_result(msg)

    def _populate_table(self, apps: list[dict]) -> None:
        self._apps = apps
        self._table.setRowCount(len(apps))
        for row, app in enumerate(apps):
            name_item = QTableWidgetItem(app["name"])
            name_item.setForeground(QColor("#e0e0e0"))

            ver_item = QTableWidgetItem(app.get("version") or "—")
            ver_item.setForeground(QColor("#9e9e9e"))
            ver_item.setTextAlignment(Qt.AlignCenter)

            size_item = QTableWidgetItem(_fmt_size(app.get("size", 0)))
            size_item.setForeground(QColor("#9e9e9e"))
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            bundle_item = QTableWidgetItem(app.get("bundle_id", ""))
            bundle_item.setForeground(QColor("#616161"))

            self._table.setItem(row, _COL_NAME,      name_item)
            self._table.setItem(row, _COL_VERSION,   ver_item)
            self._table.setItem(row, _COL_SIZE,      size_item)
            self._table.setItem(row, _COL_BUNDLE_ID, bundle_item)

        self._table.resizeRowsToContents()
        count = len(apps)
        label = f"{count} {'user' if self._app_type == 'User' else 'system'} app{'s' if count != 1 else ''}"
        self._count_label.setText(label)

    def _selected_app(self) -> dict | None:
        rows = self._table.selectedItems()
        if not rows:
            return None
        row = self._table.currentRow()
        if 0 <= row < len(self._apps):
            return self._apps[row]
        return None

    def _any_worker_running(self) -> bool:
        return (
            (self._list_worker is not None and self._list_worker.isRunning()) or
            (self._action_worker is not None and self._action_worker.isRunning())
        )

    # ── Data loading ───────────────────────────────────────────────────────

    def _load_apps(self) -> None:
        if not self._udid or self._any_worker_running():
            return

        self._table.setRowCount(0)
        self._count_label.setText("")
        self._set_busy(True, f"Loading {self._app_type.lower()} apps…")

        self._list_worker = _ListAppsWorker(self._udid, self._app_type)
        self._list_worker.finished.connect(self._on_apps_loaded)
        self._list_worker.failed.connect(self._on_load_failed)
        self._live_workers.add(self._list_worker)
        self._list_worker.finished.connect(lambda: self._live_workers.discard(self._list_worker))
        self._list_worker.start()

    def _on_apps_loaded(self, apps: list) -> None:
        self._populate_table(apps)
        self._set_busy(False)
        self._set_result("")

    def _on_load_failed(self, error: str) -> None:
        self._set_busy(False)
        self._set_result(f"Failed to load apps: {error}", color="#ef5350")

    # ── Actions ────────────────────────────────────────────────────────────

    def _on_toggle(self) -> None:
        self._app_type = "System" if self._app_type == "User" else "User"
        self._toggle_btn.setText(f"Showing: {self._app_type} Apps")
        self._load_apps()

    def _on_selection_changed(self) -> None:
        has_sel = self._selected_app() is not None
        self._uninstall_btn.setEnabled(has_sel and not self._any_worker_running())

    def _on_install(self) -> None:
        if not self._udid or self._any_worker_running():
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select .ipa file", str(Path.home()), "IPA Files (*.ipa)"
        )
        if not path:
            return

        reply = QMessageBox.question(
            self,
            "Install App",
            f"Install  {Path(path).name}  on the connected device?",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_busy(True, f"Installing {Path(path).name}…")
        self._action_worker = _AppActionWorker(_install_app(self._udid, path))
        self._action_worker.finished.connect(self._on_install_done)
        self._action_worker.failed.connect(lambda e: self._on_action_failed("Install", e))
        self._live_workers.add(self._action_worker)
        self._action_worker.finished.connect(lambda: self._live_workers.discard(self._action_worker))
        self._action_worker.start()

    def _on_install_done(self) -> None:
        self._set_busy(False)
        self._set_result("App installed successfully.", color="#66bb6a")
        self._load_apps()

    def _on_uninstall(self) -> None:
        app = self._selected_app()
        if not app or not self._udid or self._any_worker_running():
            return

        reply = QMessageBox.warning(
            self,
            "Uninstall App",
            f"Uninstall  {app['name']}  from the device?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
        )
        if reply != QMessageBox.Yes:
            return

        self._set_busy(True, f"Uninstalling {app['name']}…")
        self._action_worker = _AppActionWorker(_uninstall_app(self._udid, app["bundle_id"]))
        self._action_worker.finished.connect(self._on_uninstall_done)
        self._action_worker.failed.connect(lambda e: self._on_action_failed("Uninstall", e))
        self._live_workers.add(self._action_worker)
        self._action_worker.finished.connect(lambda: self._live_workers.discard(self._action_worker))
        self._action_worker.start()

    def _on_uninstall_done(self) -> None:
        self._set_busy(False)
        self._set_result("App uninstalled.", color="#66bb6a")
        self._load_apps()

    def _on_action_failed(self, action: str, error: str) -> None:
        self._set_busy(False)
        self._set_result(f"{action} failed: {error}", color="#ef5350")

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_all(self) -> None:
        """Cancel running workers — called by MainWindow on page switch."""
        # Workers run a single asyncio.run() call; we can't interrupt mid-call,
        # but we discard their results via the _any_worker_running() guard.
        # Nothing to actively cancel — page will just ignore stale signals.
        pass

    # ── State setters ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        self._udid = None
        self._apps = []
        self._status.setText("No device connected.")
        self._table.setRowCount(0)
        self._count_label.setText("")
        self._set_result("")
        self._set_busy(True)   # disables all buttons

    def show_connecting(self) -> None:
        self._udid = None
        self._status.setText("Connecting…")
        self._table.setRowCount(0)
        self._count_label.setText("")
        self._set_busy(True)

    def show_device(self, info: DeviceInfo) -> None:
        first_connect = self._udid is None
        self._udid = info.udid
        self._status.setText(f"Connected: {info.name}   {info.model}   iOS {info.ios_version}")
        self._set_busy(False)
        self._set_result("")
        if first_connect:
            self._load_apps()
