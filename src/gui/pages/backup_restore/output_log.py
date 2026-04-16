"""
OutputLog — right-panel streaming output widget.

Displays idevicebackup2 output lines in real time with a determinate
progress bar below. Completely passive — the page drives it via the
public API; no signals emitted.
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPlainTextEdit, QProgressBar,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextOption

log = logging.getLogger(__name__)


class OutputLog(QWidget):
    """
    Streaming output panel: monospace log + determinate progress bar.

    Usage
    -----
    log_widget.append_line("Backup progress: 45% (...)") → adds line, auto-scrolls
    log_widget.set_progress(45)                           → shows/updates bar
    log_widget.clear()                                    → clears log + hides bar
    log_widget.hide_progress()                            → hides bar, resets to 0
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def append_line(self, line: str) -> None:
        """Append one output line and scroll to the bottom."""
        self._text.appendPlainText(line)
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_progress(self, percent: int) -> None:
        """Show the progress bar (if hidden) and set its value (0–100)."""
        if not self._progress.isVisible():
            self._progress.show()
        self._progress.setValue(max(0, min(100, percent)))

    def clear(self) -> None:
        """Clear the log text and hide + reset the progress bar."""
        self._text.clear()
        self.hide_progress()

    def hide_progress(self) -> None:
        """Hide the progress bar and reset its value to 0."""
        self._progress.hide()
        self._progress.reset()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel("OUTPUT")
        lbl.setObjectName("SectionLabel")
        layout.addWidget(lbl)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        self._text.setWordWrapMode(QTextOption.NoWrap)
        self._text.setStyleSheet(
            "QPlainTextEdit { background: #0d0d0d; color: #c8c8c8; "
            "border: 1px solid #222; border-radius: 6px; padding: 6px; }"
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(10)
        self._text.setFont(mono)
        layout.addWidget(self._text, stretch=1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setFixedHeight(14)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        self._progress.setStyleSheet(
            "QProgressBar { background: #1a1a1a; border: 1px solid #333; "
            "border-radius: 4px; text-align: center; color: #aaa; font-size: 10px; }"
            "QProgressBar::chunk { background: #4fc3f7; border-radius: 3px; }"
        )
        self._progress.hide()
        layout.addWidget(self._progress)
