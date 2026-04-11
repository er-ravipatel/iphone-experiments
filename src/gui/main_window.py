"""
MainWindow — app shell with sidebar navigation, device header, page area,
and activity log.

Device polling runs on a QTimer (main thread, cheap idevice_id call).
Device info fetching runs on a QThread (blocks on ideviceinfo + pymobiledevice3).
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QPushButton, QFrame, QPlainTextEdit,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal

from ..core.results import ServiceResult
from ..device.info import DeviceInfo
from ..services.device_service import DeviceService
from .widgets.device_header import DeviceHeader
from .pages.dashboard_page import DashboardPage
from .pages.diagnostics_page import DiagnosticsPage


# ── Background worker ──────────────────────────────────────────────────────────

class _DeviceInfoWorker(QThread):
    """Runs get_device_info() off the main thread and emits the result."""
    finished: Signal = Signal(object)   # ServiceResult[DeviceInfo]

    def __init__(self, udid: str, service: DeviceService) -> None:
        super().__init__()
        self._udid = udid
        self._service = service

    def run(self) -> None:
        result = self._service.get_device_info(self._udid)
        self.finished.emit(result)


# ── Navigation constants ───────────────────────────────────────────────────────

_PAGE_DASHBOARD   = 0
_PAGE_DIAGNOSTICS = 1

# (label, page_index_or_None, enabled)
_NAV_ITEMS: list[tuple[str, int | None, bool]] = [
    ("Dashboard",        _PAGE_DASHBOARD,   True),
    ("Diagnostics",      _PAGE_DIAGNOSTICS, True),
    # ── Milestone 2+ ──────────────────────────────
    ("Files",            None,              False),
    ("Apps",             None,              False),
    ("Photos & Videos",  None,              False),
    ("Backup & Restore", None,              False),
    ("Screenshot",       None,              False),
    ("Screen Mirror",    None,              False),
    ("Settings",         None,              False),
]


# ── Main window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self._service = DeviceService()
        self._current_info: DeviceInfo | None = None
        self._worker: _DeviceInfoWorker | None = None
        self._nav_buttons: list[QPushButton] = []
        self._active_page = _PAGE_DASHBOARD

        self.setWindowTitle("iPhone Storage Explorer")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._build_ui()
        self._navigate(_PAGE_DASHBOARD)
        self._start_polling()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        root_vbox = QVBoxLayout(root)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # 1. Device header (top)
        self._header = DeviceHeader()
        self._header.refresh_requested.connect(self._on_refresh)
        root_vbox.addWidget(self._header)

        # 2. Body: sidebar + pages
        body = QWidget()
        body_hbox = QHBoxLayout(body)
        body_hbox.setContentsMargins(0, 0, 0, 0)
        body_hbox.setSpacing(0)
        body_hbox.addWidget(self._build_sidebar())

        self._stack = QStackedWidget()
        self._dash_page = DashboardPage()
        self._diag_page = DiagnosticsPage()
        self._stack.addWidget(self._dash_page)    # index 0
        self._stack.addWidget(self._diag_page)    # index 1
        body_hbox.addWidget(self._stack)

        root_vbox.addWidget(body, stretch=1)

        # 3. Activity log (bottom)
        root_vbox.addWidget(self._build_activity_log())

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(196)

        vbox = QVBoxLayout(sidebar)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # App name header
        app_label = QLabel("iPhone\nExplorer")
        app_label.setAlignment(Qt.AlignCenter)
        app_label.setStyleSheet(
            "color: #4fc3f7; font-size: 13px; font-weight: bold;"
            "padding: 18px 0 14px 0;"
        )
        vbox.addWidget(app_label)

        # Thin divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #1e1e1e; margin: 0 16px 10px 16px;")
        vbox.addWidget(div)

        # Nav buttons
        first_disabled = True
        for label, page_idx, enabled in _NAV_ITEMS:
            if not enabled and first_disabled:
                # Insert a subtle separator before the "coming soon" group
                spacer = QWidget()
                spacer.setFixedHeight(8)
                vbox.addWidget(spacer)

                sep_label = QLabel("COMING SOON")
                sep_label.setAlignment(Qt.AlignCenter)
                sep_label.setStyleSheet(
                    "color: #2a2a2a; font-size: 9px; letter-spacing: 1px;"
                    "padding: 4px 0 2px 0;"
                )
                vbox.addWidget(sep_label)
                first_disabled = False

            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setEnabled(enabled)

            if enabled and page_idx is not None:
                _idx = page_idx
                btn.clicked.connect(lambda _checked, i=_idx: self._navigate(i))

            vbox.addWidget(btn)
            self._nav_buttons.append(btn)

        vbox.addStretch()

        # Version stamp
        ver = QLabel("Milestone 1")
        ver.setAlignment(Qt.AlignCenter)
        ver.setStyleSheet("color: #2a2a2a; font-size: 10px; padding: 10px 0;")
        vbox.addWidget(ver)

        return sidebar

    def _build_activity_log(self) -> QWidget:
        container = QWidget()
        container.setObjectName("ActivityLog")
        container.setFixedHeight(96)

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(14, 6, 14, 6)
        vbox.setSpacing(2)

        hdr = QLabel("ACTIVITY")
        hdr.setObjectName("SectionLabel")
        vbox.addWidget(hdr)

        self._log = QPlainTextEdit()
        self._log.setObjectName("ActivityLogText")
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(300)
        vbox.addWidget(self._log)

        return container

    # ── Navigation ─────────────────────────────────────────────────────────

    def _navigate(self, page_idx: int) -> None:
        self._active_page = page_idx
        self._stack.setCurrentIndex(page_idx)

        for i, (_label, idx, enabled) in enumerate(_NAV_ITEMS):
            btn = self._nav_buttons[i]
            btn.setChecked(enabled and idx == page_idx)

    # ── Device polling ──────────────────────────────────────────────────────

    def _start_polling(self) -> None:
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_device)
        self._poll_timer.start(2500)
        # First check after a short delay so the window can paint first
        QTimer.singleShot(400, self._poll_device)

    def _poll_device(self) -> None:
        if self._worker and self._worker.isRunning():
            return  # info fetch in progress — wait

        udids = self._service.list_devices()

        if not udids:
            if self._current_info is not None:
                # Device just disconnected
                self._current_info = None
                self._on_disconnected()
        else:
            udid = udids[0]
            if self._current_info is None or self._current_info.udid != udid:
                # New or different device — fetch info
                self._on_connecting(udid)

    def _on_connecting(self, udid: str) -> None:
        self._log_msg(f"Device detected ({udid[:8]}…)  Reading info…")
        self._header.show_connecting()
        self._dash_page.show_connecting()
        self._diag_page.show_connecting()

        self._worker = _DeviceInfoWorker(udid, self._service)
        self._worker.finished.connect(self._on_info_received)
        self._worker.start()

    def _on_info_received(self, result: ServiceResult) -> None:
        if result.success:
            info: DeviceInfo = result.data
            self._current_info = info
            self._header.show_device(info)
            self._dash_page.show_device(info)
            self._diag_page.show_device(info)
            self._log_msg(
                f"Connected  {info.name}   {info.model}   iOS {info.ios_version}   "
                f"Battery {info.battery_level}%   "
                f"Storage {info.used_storage_gb}/{info.total_storage_gb} GB"
            )
        else:
            self._log_msg(f"Could not read device: {result.error}")
            self._header.show_no_device()
            self._dash_page.show_no_device()
            self._diag_page.show_no_device()

    def _on_disconnected(self) -> None:
        self._log_msg("Device disconnected.")
        self._header.show_no_device()
        self._dash_page.show_no_device()
        self._diag_page.show_no_device()

    def _on_refresh(self) -> None:
        self._log_msg("Refresh requested.")
        self._current_info = None
        self._poll_device()

    # ── Activity log ────────────────────────────────────────────────────────

    def _log_msg(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}]  {msg}")

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._poll_timer.stop()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        super().closeEvent(event)
