"""
DashboardPage — summary cards for the connected device.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout,
    QLabel, QFrame, QProgressBar, QSizePolicy,
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
        style += f" color: {color};" if color else " color: #e0e0e0;"
        self._value_lbl.setStyleSheet(style)

    def reset(self) -> None:
        self._value_lbl.setText("—")
        self._value_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #383838;")


class _BarCard(_InfoCard):
    """Info card with a thin progress bar below the value."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(title, parent)
        self.setMinimumHeight(90)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.layout().addWidget(self._bar)
        self._set_bar_color("#272727")

    def set_bar(self, value: int, color: str) -> None:
        self._bar.setValue(value)
        self._set_bar_color(color)

    def _set_bar_color(self, color: str) -> None:
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: #272727; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )

    def reset(self) -> None:
        super().reset()
        self._bar.setValue(0)
        self._set_bar_color("#272727")


# ── Connection banner ──────────────────────────────────────────────────────────

class _Banner(QLabel):
    _BASE = "border-radius: 5px; font-size: 12px; padding: 0 14px;"

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

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionLabel")
    return lbl


class DashboardPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.show_no_device()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # Title
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        # Connection banner
        self._banner = _Banner()
        self._banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._banner.setFixedHeight(34)
        outer.addWidget(self._banner)

        # Build all cards
        self._cards: dict[str, _InfoCard] = {
            "name":      _InfoCard("Device Name"),
            "model":     _InfoCard("Model"),
            "ios":       _InfoCard("iOS Version"),
            "battery":   _BarCard("Battery"),
            "storage":   _BarCard("Storage"),
            "arch":      _InfoCard("CPU"),
            "serial":    _InfoCard("Serial Number"),
            "wifi":      _InfoCard("Wi-Fi"),
            "bluetooth": _InfoCard("Bluetooth"),
            "udid":      _InfoCard("UDID"),
        }

        # ── DEVICE ────────────────────────────────────────────────
        outer.addSpacing(4)
        outer.addWidget(_section_label("DEVICE"))

        dev_grid = QGridLayout()
        dev_grid.setSpacing(10)
        dev_grid.setContentsMargins(0, 0, 0, 0)
        dev_grid.addWidget(self._cards["name"],  0, 0)
        dev_grid.addWidget(self._cards["model"], 0, 1)
        dev_grid.addWidget(self._cards["ios"],   0, 2)
        dev_grid.setColumnStretch(0, 1)
        dev_grid.setColumnStretch(1, 1)
        dev_grid.setColumnStretch(2, 1)
        outer.addLayout(dev_grid)

        # ── HARDWARE ──────────────────────────────────────────────
        outer.addSpacing(4)
        outer.addWidget(_section_label("HARDWARE"))

        hw_grid = QGridLayout()
        hw_grid.setSpacing(10)
        hw_grid.setContentsMargins(0, 0, 0, 0)
        hw_grid.addWidget(self._cards["battery"], 0, 0)
        hw_grid.addWidget(self._cards["storage"], 0, 1)
        hw_grid.addWidget(self._cards["arch"],    0, 2)
        hw_grid.setColumnStretch(0, 1)
        hw_grid.setColumnStretch(1, 1)
        hw_grid.setColumnStretch(2, 1)
        outer.addLayout(hw_grid)

        # ── CONNECTIVITY ──────────────────────────────────────────
        outer.addSpacing(4)
        outer.addWidget(_section_label("CONNECTIVITY"))

        conn_grid = QGridLayout()
        conn_grid.setSpacing(10)
        conn_grid.setContentsMargins(0, 0, 0, 0)
        conn_grid.addWidget(self._cards["serial"],    0, 0)
        conn_grid.addWidget(self._cards["wifi"],      0, 1)
        conn_grid.addWidget(self._cards["bluetooth"], 0, 2)
        conn_grid.addWidget(self._cards["udid"],      1, 0, 1, 3)
        conn_grid.setColumnStretch(0, 1)
        conn_grid.setColumnStretch(1, 1)
        conn_grid.setColumnStretch(2, 1)
        outer.addLayout(conn_grid)

        outer.addStretch()

    def abort_all(self) -> None:
        """No background workers on this page — satisfies the common interface."""
        pass

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
        self._cards["wifi"].set_value(info.wifi_address or "—")
        self._cards["bluetooth"].set_value(info.bluetooth_address or "—")

        # Storage bar
        pct = info.storage_percent_used
        stor_color = "#ef5350" if pct >= 90 else "#ffa726" if pct >= 75 else "#4fc3f7"
        storage_card: _BarCard = self._cards["storage"]  # type: ignore[assignment]
        storage_card.set_value(
            f"{info.used_storage_gb} / {info.total_storage_gb} GB  ({pct}%)",
            color="#ef5350" if pct >= 90 else "#ffa726" if pct >= 75 else None,
        )
        storage_card.set_bar(pct, stor_color)

        # Battery bar
        bat_card: _BarCard = self._cards["battery"]  # type: ignore[assignment]
        if info.battery_charging:
            bat_color, bat_text = "#4fc3f7", f"{info.battery_level}%  (Charging)"
        elif info.battery_level < 20:
            bat_color, bat_text = "#ef5350", f"{info.battery_level}%"
        elif info.battery_level < 30:
            bat_color, bat_text = "#ffa726", f"{info.battery_level}%"
        else:
            bat_color, bat_text = "#66bb6a", f"{info.battery_level}%"
        bat_card.set_value(bat_text, color=bat_color)
        bat_card.set_bar(info.battery_level, bat_color)
