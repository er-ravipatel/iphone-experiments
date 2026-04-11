"""
DeviceHeader — persistent top bar showing the connected device at a glance.

States:
  show_no_device()   — dim, "No Device Connected"
  show_connecting()  — amber, "Connecting..."
  show_device(info)  — green dot, name, model, iOS, battery, storage
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, Signal

from ...device.info import DeviceInfo


class DeviceHeader(QWidget):
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DeviceHeader")
        self.setFixedHeight(68)
        self._build_ui()
        self.show_no_device()

    # ── Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        # Status dot
        self._dot = QLabel("●")
        self._dot.setFixedWidth(16)
        self._dot.setAlignment(Qt.AlignCenter)
        self._dot.setStyleSheet("font-size: 9px;")
        layout.addWidget(self._dot)

        # Name + subtitle
        text_col = QVBoxLayout()
        text_col.setSpacing(1)

        self._name = QLabel()
        self._name.setStyleSheet("font-size: 15px; font-weight: bold;")

        self._subtitle = QLabel()
        self._subtitle.setStyleSheet("font-size: 11px; color: #616161;")

        text_col.addWidget(self._name)
        text_col.addWidget(self._subtitle)
        layout.addLayout(text_col)
        layout.addStretch()

        # Right-side stats (battery + storage) — hidden when no device
        self._stats = QWidget()
        stats_row = QHBoxLayout(self._stats)
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(28)

        self._battery_lbl = QLabel()
        self._battery_lbl.setStyleSheet("font-size: 12px;")

        self._storage_lbl = QLabel()
        self._storage_lbl.setStyleSheet("font-size: 12px;")

        stats_row.addWidget(self._battery_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedHeight(18)
        sep.setStyleSheet("color: #2a2a2a;")
        stats_row.addWidget(sep)

        stats_row.addWidget(self._storage_lbl)
        layout.addWidget(self._stats)

        # Divider
        vdiv = QFrame()
        vdiv.setFrameShape(QFrame.VLine)
        vdiv.setStyleSheet("color: #252525;")
        layout.addSpacing(8)
        layout.addWidget(vdiv)
        layout.addSpacing(8)

        # Refresh button
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(76)
        self._refresh_btn.setToolTip("Re-read device info")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self._refresh_btn)

    # ── State setters ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        self._dot.setStyleSheet("font-size: 9px; color: #383838;")
        self._name.setText("No Device Connected")
        self._name.setStyleSheet("font-size: 15px; font-weight: bold; color: #555555;")
        self._subtitle.setText("Connect an iPhone via USB and unlock it")
        self._stats.setVisible(False)
        self._refresh_btn.setEnabled(True)

    def show_connecting(self) -> None:
        self._dot.setStyleSheet("font-size: 9px; color: #ffa726;")
        self._name.setText("Connecting…")
        self._name.setStyleSheet("font-size: 15px; font-weight: bold; color: #ffa726;")
        self._subtitle.setText("Reading device information")
        self._stats.setVisible(False)
        self._refresh_btn.setEnabled(False)

    def show_device(self, info: DeviceInfo) -> None:
        self._dot.setStyleSheet("font-size: 9px; color: #66bb6a;")
        self._name.setText(info.name)
        self._name.setStyleSheet("font-size: 15px; font-weight: bold; color: #e0e0e0;")
        self._subtitle.setText(f"{info.model}   iOS {info.ios_version}")
        self._subtitle.setStyleSheet("font-size: 11px; color: #9e9e9e;")

        # Battery
        if info.battery_charging:
            bat_text = f"Charging  {info.battery_level}%"
            bat_color = "#4fc3f7"
        elif info.battery_level < 20:
            bat_text = f"Battery  {info.battery_level}%"
            bat_color = "#ef5350"
        elif info.battery_level < 30:
            bat_text = f"Battery  {info.battery_level}%"
            bat_color = "#ffa726"
        else:
            bat_text = f"Battery  {info.battery_level}%"
            bat_color = "#9e9e9e"
        self._battery_lbl.setText(bat_text)
        self._battery_lbl.setStyleSheet(f"font-size: 12px; color: {bat_color};")

        # Storage
        pct = info.storage_percent_used
        stor_color = "#ef5350" if pct >= 90 else "#ffa726" if pct >= 75 else "#9e9e9e"
        self._storage_lbl.setText(
            f"Storage  {info.used_storage_gb} / {info.total_storage_gb} GB"
        )
        self._storage_lbl.setStyleSheet(f"font-size: 12px; color: {stor_color};")

        self._stats.setVisible(True)
        self._refresh_btn.setEnabled(True)
