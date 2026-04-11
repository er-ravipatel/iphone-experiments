"""
DashboardPage — summary cards for the connected device.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt

from ...device.info import DeviceInfo


# ── Card widget ────────────────────────────────────────────────────────────────

class _InfoCard(QFrame):
    """A labelled value card used in the dashboard grid."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self._title_lbl = QLabel(title.upper())
        self._title_lbl.setObjectName("CardTitle")

        self._value_lbl = QLabel("—")
        self._value_lbl.setObjectName("CardValue")
        self._value_lbl.setWordWrap(True)

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._value_lbl)

    def set_value(self, text: str, color: str | None = None) -> None:
        self._value_lbl.setText(text)
        style = "font-size: 15px; font-weight: bold;"
        if color:
            style += f" color: {color};"
        else:
            style += " color: #e0e0e0;"
        self._value_lbl.setStyleSheet(style)

    def reset(self) -> None:
        self._value_lbl.setText("—")
        self._value_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #383838;")


# ── Connection banner ──────────────────────────────────────────────────────────

class _Banner(QLabel):
    _BASE = (
        "border-radius: 5px; font-size: 12px; padding: 0 14px;"
    )

    def set_disconnected(self) -> None:
        self.setText("No device connected — connect your iPhone via USB and unlock it")
        self.setStyleSheet(f"background-color: #1a1a1a; border: 1px solid #272727; color: #555555; {self._BASE}")

    def set_connecting(self) -> None:
        self.setText("Connecting — reading device information…")
        self.setStyleSheet(f"background-color: #1f1800; border: 1px solid #ffa726; color: #ffa726; {self._BASE}")

    def set_connected(self, name: str) -> None:
        self.setText(f"Connected   {name}")
        self.setStyleSheet(f"background-color: #0a1f0a; border: 1px solid #2e7d32; color: #66bb6a; {self._BASE}")


# ── Page ───────────────────────────────────────────────────────────────────────

class DashboardPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.show_no_device()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Title
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        # Connection banner
        self._banner = _Banner()
        self._banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._banner.setFixedHeight(34)
        outer.addWidget(self._banner)

        # Cards
        self._cards: dict[str, _InfoCard] = {
            "name":    _InfoCard("Device Name"),
            "model":   _InfoCard("Model"),
            "ios":     _InfoCard("iOS Version"),
            "battery": _InfoCard("Battery"),
            "storage": _InfoCard("Storage"),
            "arch":    _InfoCard("CPU Architecture"),
            "serial":  _InfoCard("Serial Number"),
            "udid":    _InfoCard("UDID"),
        }

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)

        # Row 0: name | model | ios
        grid.addWidget(self._cards["name"],    0, 0)
        grid.addWidget(self._cards["model"],   0, 1)
        grid.addWidget(self._cards["ios"],     0, 2)
        # Row 1: battery | storage | arch
        grid.addWidget(self._cards["battery"], 1, 0)
        grid.addWidget(self._cards["storage"], 1, 1)
        grid.addWidget(self._cards["arch"],    1, 2)
        # Row 2: serial | udid (spans 2 cols)
        grid.addWidget(self._cards["serial"],  2, 0)
        grid.addWidget(self._cards["udid"],    2, 1, 1, 2)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        outer.addLayout(grid)
        outer.addStretch()

    # ── State setters ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        self._banner.set_disconnected()
        for card in self._cards.values():
            card.reset()

    def show_connecting(self) -> None:
        self._banner.set_connecting()
        for card in self._cards.values():
            card.reset()

    def show_device(self, info: DeviceInfo) -> None:
        self._banner.set_connected(info.name)

        self._cards["name"].set_value(info.name)
        self._cards["model"].set_value(info.model)
        self._cards["ios"].set_value(f"iOS {info.ios_version}  ({info.build_version})")
        self._cards["serial"].set_value(info.serial)
        self._cards["udid"].set_value(info.udid)
        self._cards["arch"].set_value(info.cpu_architecture or "—")

        # Storage — colour by usage percent
        pct = info.storage_percent_used
        stor_color = "#ef5350" if pct >= 90 else "#ffa726" if pct >= 75 else None
        self._cards["storage"].set_value(
            f"{info.used_storage_gb} / {info.total_storage_gb} GB  ({pct}%)",
            color=stor_color,
        )

        # Battery — colour by level
        if info.battery_charging:
            bat_color = "#4fc3f7"
            bat_text = f"{info.battery_level}%  (Charging)"
        elif info.battery_level < 20:
            bat_color = "#ef5350"
            bat_text = f"{info.battery_level}%"
        elif info.battery_level < 30:
            bat_color = "#ffa726"
            bat_text = f"{info.battery_level}%"
        else:
            bat_color = None
            bat_text = f"{info.battery_level}%"
        self._cards["battery"].set_value(bat_text, color=bat_color)
