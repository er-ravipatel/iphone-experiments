"""
ScreenshotPage — capture a screenshot from the connected device.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap

from ...device.info import DeviceInfo
from ...utils.runner import run


# ── Background worker ──────────────────────────────────────────────────────────

class _ScreenshotWorker(QThread):
    """Runs idevicescreenshot off the main thread."""
    finished = Signal(bool, str, str)   # success, out_path, error_detail

    def __init__(self, udid: str, out_path: str) -> None:
        super().__init__()
        self._udid = udid
        self._out_path = out_path

    def run(self) -> None:
        result = run("idevicescreenshot", self._out_path, udid=self._udid, timeout=20)
        if result.success or Path(self._out_path).exists():
            self.finished.emit(True, self._out_path, "")
        else:
            detail = result.stderr or result.stdout or ""
            self.finished.emit(False, self._out_path, detail)


# ── Page ───────────────────────────────────────────────────────────────────────

class ScreenshotPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._worker: _ScreenshotWorker | None = None
        self._build_ui()
        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        # Title
        title = QLabel("Screenshot")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        # Status label
        self._status = QLabel()
        self._status.setObjectName("StatusLabel")
        outer.addWidget(self._status)

        # Preview area
        preview_frame = QFrame()
        preview_frame.setObjectName("Card")
        preview_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self._preview = QLabel()
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._preview.setMinimumHeight(300)
        preview_layout.addWidget(self._preview)

        outer.addWidget(preview_frame, stretch=1)

        # ── Bottom control bar ─────────────────────────────────────────────
        bar = QWidget()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(10)

        # Save path display
        self._path_label = QLabel()
        self._path_label.setObjectName("StatusLabel")
        self._path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._path_label.setWordWrap(False)
        bar_layout.addWidget(self._path_label, stretch=1)

        self._browse_btn = QPushButton("Change Path")
        self._browse_btn.setFixedWidth(110)
        self._browse_btn.clicked.connect(self._on_browse)
        bar_layout.addWidget(self._browse_btn)

        self._capture_btn = QPushButton("Capture Screenshot")
        self._capture_btn.setFixedWidth(160)
        self._capture_btn.clicked.connect(self._on_capture)
        bar_layout.addWidget(self._capture_btn)

        outer.addWidget(bar)

        # Result message
        self._result_label = QLabel()
        self._result_label.setObjectName("StatusLabel")
        self._result_label.setWordWrap(True)
        outer.addWidget(self._result_label)

        # Set default save path
        self._out_path = self._default_path()
        self._path_label.setText(f"Save to:  {self._out_path}")

    # ── Helpers ────────────────────────────────────────────────────────────

    def _default_path(self) -> str:
        ts = int(time.time())
        return str(Path.home() / f"iphone_screenshot_{ts}.png")

    def _set_placeholder(self, text: str) -> None:
        self._preview.setPixmap(QPixmap())
        self._preview.setText(text)
        self._preview.setStyleSheet("color: #383838; font-size: 13px;")

    def _show_pixmap(self, path: str) -> None:
        px = QPixmap(path)
        if px.isNull():
            self._set_placeholder("Could not load image preview.")
            return
        scaled = px.scaled(
            self._preview.width() - 16,
            self._preview.height() - 16,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._preview.setPixmap(scaled)
        self._preview.setText("")

    def _set_result(self, text: str, color: str = "#9e9e9e") -> None:
        self._result_label.setText(text)
        self._result_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _set_busy(self, busy: bool) -> None:
        self._capture_btn.setEnabled(not busy)
        self._browse_btn.setEnabled(not busy)
        if busy:
            self._capture_btn.setText("Capturing…")
        else:
            self._capture_btn.setText("Capture Screenshot")

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Screenshot As",
            self._out_path,
            "PNG Images (*.png);;All Files (*)",
        )
        if path:
            self._out_path = path
            self._path_label.setText(f"Save to:  {self._out_path}")

    def _on_capture(self) -> None:
        if not self._udid or self._worker and self._worker.isRunning():
            return

        self._out_path = self._out_path  # keep current path
        self._set_busy(True)
        self._set_result("Capturing…")
        self._set_placeholder("Capturing screenshot…")

        self._worker = _ScreenshotWorker(self._udid, self._out_path)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_done(self, success: bool, out_path: str, detail: str) -> None:
        self._set_busy(False)
        # Refresh default path for next capture
        self._out_path = self._default_path()
        self._path_label.setText(f"Save to:  {self._out_path}")

        if success:
            self._show_pixmap(out_path)
            self._set_result(f"Saved to: {out_path}", color="#66bb6a")
        else:
            self._set_placeholder("Screenshot failed.")
            detail_lower = detail.lower()
            if "invalid service" in detail_lower or "developer disk image" in detail_lower:
                msg = (
                    "Developer services are not available on this device.\n"
                    "Mount the Developer Disk Image first (use Screen Mirror → Auto Prepare), then try again."
                )
            else:
                msg = (
                    "Capture failed — make sure the iPhone is unlocked and trusted.\n"
                    + (detail if detail else "")
                )
            self._set_result(msg, color="#ef5350")

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_all(self) -> None:
        """Signal the screenshot worker to stop — called by MainWindow on page switch."""
        if self._worker and self._worker.isRunning():
            self._worker.quit()   # idevicescreenshot is a subprocess; quit() is safe here

    # ── State setters ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        self._udid = None
        self._status.setText("No device connected.")
        self._set_placeholder("Connect an iPhone to capture a screenshot.")
        self._capture_btn.setEnabled(False)
        self._browse_btn.setEnabled(False)
        self._set_result("")

    def show_connecting(self) -> None:
        self._udid = None
        self._status.setText("Connecting…")
        self._set_placeholder("Reading device information…")
        self._capture_btn.setEnabled(False)
        self._browse_btn.setEnabled(False)

    def show_device(self, info: DeviceInfo) -> None:
        self._udid = info.udid
        self._status.setText(f"Connected: {info.name}   {info.model}   iOS {info.ios_version}")
        self._set_placeholder("Press Capture Screenshot to take a snapshot.")
        self._capture_btn.setEnabled(True)
        self._browse_btn.setEnabled(True)
        self._set_result("")
