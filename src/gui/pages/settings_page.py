"""
SettingsPage — persistent app configuration.

Settings are device-independent, so all four lifecycle methods
(show_no_device / show_connecting / show_device / abort_all) are no-ops.
Values are read from QSettings on construction and written back only when
the user clicks Apply — edits in progress are never auto-discarded.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QFrame, QFileDialog,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

from ...device.info import DeviceInfo
from .. import settings

# ── Screenshot-interval options ────────────────────────────────────────────────
_INTERVAL_OPTIONS: list[tuple[str, int]] = [
    ("Every 2 seconds",  2000),
    ("Every 4 seconds",  4000),
    ("Every 10 seconds", 10000),
    ("Disabled",         0),
]


class SettingsPage(QWidget):
    """
    Settings page — three sections: Backup, Diagnostics, Tools.

    All controls write to QSettings via settings.set_*() on Apply.
    Other pages re-read settings at their next relevant entry point
    (show_device, worker creation) so changes take effect without restart.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._load_from_settings()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        # Title
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        # ── BACKUP card ────────────────────────────────────────────────────
        outer.addWidget(self._make_card("BACKUP", self._build_backup_section()))

        # ── DIAGNOSTICS card ───────────────────────────────────────────────
        outer.addWidget(self._make_card("DIAGNOSTICS", self._build_diagnostics_section()))

        # ── TOOLS card ─────────────────────────────────────────────────────
        outer.addWidget(self._make_card("TOOLS", self._build_tools_section()))

        outer.addStretch()

        # ── Bottom bar: saved label + Apply ───────────────────────────────
        bottom = QHBoxLayout()
        bottom.addStretch()

        self._saved_lbl = QLabel("✓  Settings saved.")
        self._saved_lbl.setStyleSheet("color: #4caf50; font-size: 12px;")
        self._saved_lbl.setVisible(False)
        bottom.addWidget(self._saved_lbl)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedWidth(100)
        apply_btn.clicked.connect(self._on_apply)
        bottom.addWidget(apply_btn)

        outer.addLayout(bottom)

    # ── Section builders ───────────────────────────────────────────────────

    def _build_backup_section(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        vbox.addWidget(QLabel("Backup folder"))

        row = QHBoxLayout()
        self._backup_dir_edit = QLineEdit()
        self._backup_dir_edit.setPlaceholderText(str(Path.home() / "iphone_backups"))
        row.addWidget(self._backup_dir_edit, stretch=1)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_backup_dir)
        row.addWidget(browse_btn)
        vbox.addLayout(row)
        return w

    def _build_diagnostics_section(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        vbox.addWidget(QLabel("Auto-screenshot interval"))

        self._interval_combo = QComboBox()
        for label, ms in _INTERVAL_OPTIONS:
            self._interval_combo.addItem(label, userData=ms)
        self._interval_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._interval_combo.setMinimumWidth(180)
        vbox.addWidget(self._interval_combo)
        return w

    def _build_tools_section(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        vbox.addWidget(QLabel("libimobiledevice directory"))

        hint = QLabel("Leave blank to auto-detect from PATH and vendor/")
        hint.setStyleSheet("color: #555; font-size: 11px;")
        vbox.addWidget(hint)

        row = QHBoxLayout()
        self._tools_path_edit = QLineEdit()
        self._tools_path_edit.setPlaceholderText("auto-detect")
        row.addWidget(self._tools_path_edit, stretch=1)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_tools_dir)
        row.addWidget(browse_btn)
        vbox.addLayout(row)
        return w

    @staticmethod
    def _make_card(section_label: str, content: QWidget) -> QFrame:
        """Wrap content in a Card frame with a SectionLabel header."""
        card = QFrame()
        card.setObjectName("Card")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(14, 10, 14, 14)
        vbox.setSpacing(8)

        lbl = QLabel(section_label)
        lbl.setObjectName("SectionLabel")
        vbox.addWidget(lbl)
        vbox.addWidget(content)
        return card

    # ── Settings I/O ───────────────────────────────────────────────────────

    def _load_from_settings(self) -> None:
        """Populate all widgets from persisted QSettings values."""
        self._backup_dir_edit.setText(settings.backup_dir())

        ms = settings.screenshot_interval_ms()
        for i, (_label, val) in enumerate(_INTERVAL_OPTIONS):
            if val == ms:
                self._interval_combo.setCurrentIndex(i)
                break

        self._tools_path_edit.setText(settings.tools_path())
        self._saved_lbl.setVisible(False)

    def _on_apply(self) -> None:
        """Write all field values to QSettings and flash the confirmation label."""
        settings.set_backup_dir(self._backup_dir_edit.text().strip())
        settings.set_screenshot_interval_ms(self._interval_combo.currentData())
        settings.set_tools_path(self._tools_path_edit.text().strip())

        self._saved_lbl.setVisible(True)
        QTimer.singleShot(3000, lambda: self._saved_lbl.setVisible(False))

    # ── Browse handlers ────────────────────────────────────────────────────

    def _browse_backup_dir(self) -> None:
        current = self._backup_dir_edit.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Select Backup Folder", current)
        if d:
            self._backup_dir_edit.setText(d)

    def _browse_tools_dir(self) -> None:
        current = self._tools_path_edit.text() or str(Path.home())
        d = QFileDialog.getExistingDirectory(
            self, "Select libimobiledevice Directory", current
        )
        if d:
            self._tools_path_edit.setText(d)

    # ── Page contract (all no-ops — settings are device-independent) ───────

    def show_no_device(self) -> None:
        pass

    def show_connecting(self) -> None:
        pass

    def show_device(self, info: DeviceInfo) -> None:  # noqa: ARG002
        pass

    def abort_all(self) -> None:
        pass
