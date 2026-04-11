"""
DiagnosticsPage — full read-only device info table.

Reboot / shutdown actions are intentionally absent in Milestone 1.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from ...device.info import DeviceInfo


class DiagnosticsPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.show_no_device()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Diagnostics")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        self._status = QLabel()
        self._status.setObjectName("StatusLabel")
        layout.addWidget(self._status)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Field", "Value"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        layout.addWidget(self._table)

    # ── State setters ──────────────────────────────────────────────────────

    def abort_all(self) -> None:
        """No background workers on this page — satisfies the common interface."""
        pass

    def show_no_device(self) -> None:
        self._status.setText("No device connected.")
        self._table.setRowCount(0)

    def show_connecting(self) -> None:
        self._status.setText("Connecting…")
        self._table.setRowCount(0)

    def show_device(self, info: DeviceInfo) -> None:
        self._status.setText(f"Connected: {info.name}")

        rows: list[tuple[str, str]] = [
            ("Device Name",       info.name),
            ("Model",             info.model),
            ("Product Type",      info.product_type),
            ("iOS Version",       info.ios_version),
            ("Build Version",     info.build_version),
            ("Serial Number",     info.serial),
            ("UDID",              info.udid),
            ("CPU Architecture",  info.cpu_architecture),
            ("Device Color",      info.color),
            ("Wi-Fi Address",     info.wifi_address),
            ("Bluetooth Address", info.bluetooth_address),
            ("Battery Level",     f"{info.battery_level}%"),
            ("Charging",          "Yes" if info.battery_charging else "No"),
            ("Total Storage",     f"{info.total_storage_gb} GB"),
            ("Used Storage",      f"{info.used_storage_gb} GB  ({info.storage_percent_used}%)"),
            ("Free Storage",      f"{info.free_storage_gb} GB"),
            ("Device Class",      info.device_class),
            ("Activation State",  info.activation_state),
        ]

        self._table.setRowCount(len(rows))
        for i, (field, value) in enumerate(rows):
            field_item = QTableWidgetItem(field)
            field_item.setForeground(QColor("#9e9e9e"))

            value_item = QTableWidgetItem(value or "—")
            value_item.setForeground(QColor("#e0e0e0"))

            self._table.setItem(i, 0, field_item)
            self._table.setItem(i, 1, value_item)

        self._table.resizeRowsToContents()
