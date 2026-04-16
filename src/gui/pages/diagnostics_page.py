"""
DiagnosticsPage — 3uTools-style device info panel.

Layout
------
Left column  : categorised info table (Identity / Hardware / Connectivity / Battery & Storage)
Right column : status cards (Activation, Find My, Passcode, Developer Mode)
               + live screenshot refreshed every 3 s
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QScrollArea, QPushButton, QSizePolicy,
    QGridLayout, QAbstractScrollArea,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QColor, QFont, QPixmap, QImage

from ...device.info import DeviceInfo


# ── Screenshot worker ──────────────────────────────────────────────────────────

class _ScreenshotWorker(QThread):
    """Captures one screenshot via pymobiledevice3 and emits raw PNG bytes."""
    ready  = Signal(bytes)
    failed = Signal(str)   # carries error reason

    def __init__(self, udid: str) -> None:
        super().__init__()
        self._udid = udid

    def run(self) -> None:
        import asyncio, sys
        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.screenshot import ScreenshotService

            async def _take() -> bytes:
                lockdown = await create_using_usbmux(serial=self._udid)
                async with ScreenshotService(lockdown) as svc:
                    return await svc.take_screenshot()

            # Suppress asyncio "Future exception never retrieved" noise
            loop = asyncio.new_event_loop()
            loop.set_exception_handler(lambda l, ctx: None)
            try:
                data = loop.run_until_complete(_take())
            finally:
                loop.close()

            self.ready.emit(data)
        except Exception as e:
            self.failed.emit(str(e))


# ── Status card widget ─────────────────────────────────────────────────────────

class _StatusCard(QWidget):
    """A small card with a coloured dot + label + value."""

    _DOT_OK   = "#4caf50"   # green
    _DOT_WARN = "#ef5350"   # red
    _DOT_GREY = "#555555"   # unknown

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedHeight(52)
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(10, 6, 10, 6)
        hbox.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(f"color: {self._DOT_GREY}; font-size: 10px;")
        hbox.addWidget(self._dot)

        info = QVBoxLayout()
        info.setSpacing(1)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #757575; font-size: 10px; background: transparent;")
        info.addWidget(lbl)
        self._val = QLabel("—")
        self._val.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: bold; background: transparent;")
        info.addWidget(self._val)
        hbox.addLayout(info)

    def set_ok(self, text: str) -> None:
        self._dot.setStyleSheet(f"color: {self._DOT_OK}; font-size: 10px;")
        self._val.setText(text)

    def set_warn(self, text: str) -> None:
        self._dot.setStyleSheet(f"color: {self._DOT_WARN}; font-size: 10px;")
        self._val.setText(text)

    def set_neutral(self, text: str) -> None:
        self._dot.setStyleSheet(f"color: {self._DOT_GREY}; font-size: 10px;")
        self._val.setText(text)

    def reset(self) -> None:
        self.set_neutral("—")


# ── Section header helper ──────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    lbl.setContentsMargins(0, 10, 0, 2)
    return lbl


# ── Main page ─────────────────────────────────────────────────────────────────

class DiagnosticsPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._live_workers: set = set()
        self._shot_timer: QTimer | None = None
        self._build_ui()
        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(10)

        # Title row
        title_row = QHBoxLayout()
        title = QLabel("Diagnostics")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("StatusLabel")
        title_row.addWidget(self._status_lbl)
        root.addLayout(title_row)

        # Body: left info table | right status + screenshot
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_info_panel(), stretch=3)
        body.addWidget(self._build_right_panel(), stretch=2)
        root.addLayout(body, stretch=1)

    # ── Left: scrollable info table ────────────────────────────────────────

    def _build_info_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 8, 0)
        vbox.setSpacing(0)

        def make_table() -> QTableWidget:
            t = QTableWidget(0, 2)
            t.horizontalHeader().setVisible(False)
            t.verticalHeader().setVisible(False)
            t.setEditTriggers(QTableWidget.NoEditTriggers)
            t.setSelectionBehavior(QTableWidget.SelectRows)
            t.setShowGrid(False)
            t.setAlternatingRowColors(True)
            t.setStyleSheet(
                "QTableWidget { background: #1c1c1c; border: 1px solid #272727;"
                "  border-radius: 6px; alternate-background-color: #191919; }"
                "QTableWidget::item { padding: 5px 10px; color: #e0e0e0; }"
            )
            t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
            t.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            t.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            return t

        vbox.addWidget(_section_label("DEVICE IDENTITY"))
        self._tbl_identity = make_table()
        vbox.addWidget(self._tbl_identity)

        vbox.addWidget(_section_label("HARDWARE"))
        self._tbl_hardware = make_table()
        vbox.addWidget(self._tbl_hardware)

        vbox.addWidget(_section_label("CONNECTIVITY"))
        self._tbl_connectivity = make_table()
        vbox.addWidget(self._tbl_connectivity)

        vbox.addWidget(_section_label("BATTERY & STORAGE"))
        self._tbl_battery = make_table()
        vbox.addWidget(self._tbl_battery)

        vbox.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Right: status cards + screenshot ──────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        # Outer scroll area so the whole right column is reachable at any
        # window height — the 5 status cards alone occupy ~300 px, leaving
        # too little room for the screenshot panel without scrolling.
        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer_scroll.setFrameShape(QFrame.NoFrame)
        outer_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        panel = QWidget()
        panel.setStyleSheet("background: transparent;")
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 8, 0)
        vbox.setSpacing(8)

        vbox.addWidget(_section_label("DEVICE STATUS"))

        self._card_activation  = _StatusCard("Activation")
        self._card_icloud      = _StatusCard("iCloud Lock")
        self._card_find_my     = _StatusCard("Find My")
        self._card_passcode    = _StatusCard("Passcode")
        self._card_dev_mode    = _StatusCard("Developer Mode")

        for card in (self._card_activation, self._card_icloud,
                     self._card_find_my, self._card_passcode, self._card_dev_mode):
            vbox.addWidget(card)

        vbox.addWidget(_section_label("DEVICE SCREEN"))

        # Screenshot card — fixed visible area with its own inner scroll for the image
        shot_frame = QWidget()
        shot_frame.setObjectName("Card")
        shot_frame.setMinimumHeight(320)
        shot_vbox = QVBoxLayout(shot_frame)
        shot_vbox.setContentsMargins(6, 6, 6, 6)
        shot_vbox.setSpacing(6)

        # Capture button row — always visible at the top of the card
        shot_ctrl = QHBoxLayout()
        self._shot_refresh_btn = QPushButton("📷  Capture Screenshot")
        self._shot_refresh_btn.setEnabled(False)
        self._shot_refresh_btn.setFixedHeight(30)
        self._shot_refresh_btn.clicked.connect(self._capture_screenshot)
        shot_ctrl.addWidget(self._shot_refresh_btn)

        self._shot_auto_lbl = QLabel()
        self._shot_auto_lbl.setObjectName("StatusLabel")
        self._shot_auto_lbl.setStyleSheet("color: #444; font-size: 10px;")
        shot_ctrl.addWidget(self._shot_auto_lbl)
        shot_ctrl.addStretch()
        shot_vbox.addLayout(shot_ctrl)

        # Scrollable image area below the button
        self._shot_scroll = QScrollArea()
        self._shot_scroll.setWidgetResizable(False)
        self._shot_scroll.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self._shot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._shot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._shot_scroll.setMinimumHeight(240)
        self._shot_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #272727; border-radius: 4px;"
            "  background: #111111; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        self._shot_lbl = QLabel("No screenshot yet")
        self._shot_lbl.setAlignment(Qt.AlignCenter)
        self._shot_lbl.setStyleSheet("color: #444; font-size: 12px; background: transparent;")
        self._shot_lbl.setMinimumSize(180, 220)
        self._shot_scroll.setWidget(self._shot_lbl)
        shot_vbox.addWidget(self._shot_scroll, stretch=1)

        vbox.addWidget(shot_frame)
        vbox.addStretch()

        outer_scroll.setWidget(panel)
        return outer_scroll

    # ── Table population ───────────────────────────────────────────────────

    @staticmethod
    def _fill_table(table: QTableWidget, rows: list[tuple[str, str]]) -> None:
        table.setRowCount(len(rows))
        for i, (label, value) in enumerate(rows):
            lbl_item = QTableWidgetItem(label)
            lbl_item.setForeground(QColor("#9e9e9e"))
            val_item = QTableWidgetItem(value or "—")
            val_item.setForeground(QColor("#e0e0e0"))
            table.setItem(i, 0, lbl_item)
            table.setItem(i, 1, val_item)
        table.resizeRowsToContents()
        # Resize table height to content so scroll area works naturally
        h = sum(table.rowHeight(r) for r in range(table.rowCount())) + 4
        table.setFixedHeight(max(h, 30))

    # ── Screenshot ────────────────────────────────────────────────────────

    def _capture_screenshot(self) -> None:
        if not self._udid:
            return
        self._shot_auto_lbl.setText("Capturing…")
        w = _ScreenshotWorker(self._udid)
        w.ready.connect(self._on_screenshot)
        w.failed.connect(self._on_screenshot_failed)
        w.finished.connect(lambda: self._live_workers.discard(w))
        self._live_workers.add(w)
        w.start()

    def _on_screenshot(self, data: bytes) -> None:
        img = QImage.fromData(data)
        if img.isNull():
            self._shot_auto_lbl.setText("Bad image")
            return
        # Scale image to the viewport width; height overflows into the scrollbar
        avail_w = self._shot_scroll.viewport().width() or 260
        px = QPixmap.fromImage(img).scaledToWidth(avail_w, Qt.SmoothTransformation)
        self._shot_lbl.setPixmap(px)
        self._shot_lbl.resize(px.size())
        self._shot_lbl.setText("")
        self._shot_auto_lbl.setText("Live  ●")
        self._shot_auto_lbl.setStyleSheet("color: #4caf50; font-size: 10px;")

    def _on_screenshot_failed(self, reason: str) -> None:
        if "InvalidService" in reason or "DeveloperMode" in reason:
            # Service needs developer mode — stop retrying
            self._stop_auto_screenshot()
            self._shot_lbl.setText("Requires Developer Mode\non device")
            self._shot_auto_lbl.setText("Unavailable")
            self._shot_auto_lbl.setStyleSheet("color: #555; font-size: 10px;")
        else:
            self._shot_auto_lbl.setText("Failed — retrying…")

    def _start_auto_screenshot(self) -> None:
        if self._shot_timer:
            return
        self._shot_timer = QTimer(self)
        self._shot_timer.timeout.connect(self._capture_screenshot)
        self._shot_timer.start(4000)
        self._capture_screenshot()   # immediate first shot

    def _stop_auto_screenshot(self) -> None:
        if self._shot_timer:
            self._shot_timer.stop()
            self._shot_timer = None

    # ── State setters ──────────────────────────────────────────────────────

    def abort_all(self) -> None:
        self._stop_auto_screenshot()
        for w in list(self._live_workers):
            if hasattr(w, "quit"):
                w.quit()

    def show_no_device(self) -> None:
        self._udid = None
        self._status_lbl.setText("No device connected.")
        self._stop_auto_screenshot()
        self._shot_refresh_btn.setEnabled(False)
        self._shot_lbl.setPixmap(QPixmap())
        self._shot_lbl.resize(self._shot_lbl.minimumSize())
        self._shot_lbl.setText("No device connected")
        self._shot_auto_lbl.setText("")
        for tbl in (self._tbl_identity, self._tbl_hardware,
                    self._tbl_connectivity, self._tbl_battery):
            tbl.setRowCount(0)
            tbl.setFixedHeight(30)
        for card in (self._card_activation, self._card_icloud, self._card_find_my,
                     self._card_passcode, self._card_dev_mode):
            card.reset()

    def show_connecting(self) -> None:
        self._status_lbl.setText("Connecting…")

    def show_device(self, info: DeviceInfo) -> None:
        self._udid = info.udid
        self._status_lbl.setText(f"Connected: {info.name}")
        self._shot_refresh_btn.setEnabled(True)

        # ── Identity table ─────────────────────────────────────────────
        identity_rows: list[tuple[str, str]] = [
            ("Device Name",    info.name),
            ("Model",          info.model),
            ("Product Type",   info.product_type),
            ("Model Number",   info.model_number),
            ("Hardware Model", info.hardware_model),
            ("iOS Version",    info.ios_version),
            ("Build",          info.build_version),
            ("Serial Number",  info.serial),
            ("UDID",           info.udid),
            ("IMEI",           info.imei),
            ("IMEI 2",         info.imei2),
            ("MEID",           info.meid),
            ("ICCID",          info.iccid),
            ("Phone Number",   info.phone_number),
            ("Region",         info.region_info),
            ("Color",          info.color),
        ]
        self._fill_table(self._tbl_identity, [r for r in identity_rows if r[1]])

        # ── Hardware table ─────────────────────────────────────────────
        hardware_rows: list[tuple[str, str]] = [
            ("CPU Architecture",  info.cpu_architecture),
            ("Platform",          info.hardware_platform),
            ("Board ID",          info.board_id),
            ("Chip ID",           info.chip_id_hex),
            ("Die ID",            info.die_id),
            ("Baseband Version",  info.baseband_version),
            ("Firmware",          info.firmware_version),
            ("Board Serial",      info.mlb_serial),
        ]
        self._fill_table(self._tbl_hardware, [r for r in hardware_rows if r[1]])

        # ── Connectivity table ─────────────────────────────────────────
        conn_rows: list[tuple[str, str]] = [
            ("Wi-Fi",      info.wifi_address),
            ("Bluetooth",  info.bluetooth_address),
            ("Ethernet",   info.ethernet_address),
        ]
        self._fill_table(self._tbl_connectivity, [r for r in conn_rows if r[1]])

        # ── Battery & storage table ────────────────────────────────────
        charge_status = "Charging" if info.battery_charging else (
            "Full" if info.battery_fully_charged else "On Battery"
        )
        battery_rows: list[tuple[str, str]] = [
            ("Battery Level",    f"{info.battery_level}%"),
            ("Charge Status",    charge_status),
            ("Plugged In",       "Yes" if info.battery_external_connected else "No"),
            ("Total Storage",    f"{info.total_storage_gb} GB"),
            ("Used Storage",     f"{info.used_storage_gb} GB  ({info.storage_percent_used}%)"),
            ("Free Storage",     f"{info.free_storage_gb} GB"),
        ]
        self._fill_table(self._tbl_battery, battery_rows)

        # ── Status cards ───────────────────────────────────────────────
        if info.activation_state == "Activated":
            self._card_activation.set_ok("Activated")
        elif info.activation_state:
            self._card_activation.set_warn(info.activation_state)
        else:
            self._card_activation.set_neutral("Unknown")

        if info.icloud_locked:
            self._card_icloud.set_warn("Locked")
        else:
            self._card_icloud.set_ok("Not Locked")

        if info.find_my_locked:
            self._card_find_my.set_warn("Enabled & Locked")
        else:
            self._card_find_my.set_ok("Not Locked")

        if info.password_protected:
            self._card_passcode.set_ok("Enabled")
        else:
            self._card_passcode.set_warn("Disabled")

        if info.developer_mode:
            self._card_dev_mode.set_ok("Enabled")
        else:
            self._card_dev_mode.set_neutral("Disabled")

        # ── Start auto screenshot (only when page is visible) ──────────
        if self.isVisible():
            self._start_auto_screenshot()

    def showEvent(self, event) -> None:   # type: ignore[override]
        super().showEvent(event)
        if self._udid:
            self._start_auto_screenshot()

    def hideEvent(self, event) -> None:   # type: ignore[override]
        super().hideEvent(event)
        self._stop_auto_screenshot()
