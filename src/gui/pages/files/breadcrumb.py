"""
BreadcrumbBar — clickable path navigation widget.

Reusable in any page that deals with hierarchical paths.

Signals
-------
path_selected(str)  — emitted when the user clicks any segment.
"""
from __future__ import annotations

import logging
from pathlib import PurePosixPath

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal

log = logging.getLogger(__name__)


class BreadcrumbBar(QWidget):
    """
    Horizontal breadcrumb navigator.

    Usage
    -----
    bar = BreadcrumbBar()
    bar.path_selected.connect(my_handler)
    bar.set_path("/DCIM/100APPLE")
    """

    path_selected: Signal = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_path = "/"
        self._root_label = "📱 iPhone"   # overridden via set_root_label()
        self._build_ui()

    # ── Public API ─────────────────────────────────────────────────────────

    def set_path(self, path: str) -> None:
        """Render breadcrumb for *path* (POSIX-style, e.g. '/DCIM/100APPLE')."""
        self._current_path = path
        self._render(path)

    def set_root_label(self, label: str) -> None:
        """Override the text shown for the root ('/') segment. Call with device name on connect."""
        self._root_label = label
        self._render(self._current_path)

    @property
    def current_path(self) -> str:
        return self._current_path

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(0)

        path_lbl = QLabel("PATH")
        path_lbl.setStyleSheet(
            "color: #555; font-size: 9px; letter-spacing: 1px; padding-right: 8px;"
        )
        outer.addWidget(path_lbl)

        # Scrollable segment row (handles very long paths)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setFixedHeight(28)
        self._scroll.setStyleSheet("background: transparent;")

        self._inner = QWidget()
        self._inner.setStyleSheet("background: transparent;")
        self._seg_layout = QHBoxLayout(self._inner)
        self._seg_layout.setContentsMargins(0, 0, 0, 0)
        self._seg_layout.setSpacing(0)
        self._seg_layout.addStretch()
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, stretch=1)

        self.setObjectName("CrumbBar")
        self.setStyleSheet(
            "QWidget#CrumbBar { background: #1a1a1a; border-radius: 6px; }"
        )

    def _render(self, path: str) -> None:
        # Remove existing segment widgets (leave the trailing stretch)
        while self._seg_layout.count() > 1:
            item = self._seg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        parts = [p for p in path.split("/") if p]
        segments = [(self._root_label, "/")] + self._build_segments(parts)

        for i, (label, target) in enumerate(segments):
            btn = QPushButton(label)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { color: #4fc3f7; font-size: 12px; padding: 0 2px; "
                "background: transparent; border: none; }"
                "QPushButton:hover { color: #81d4fa; text-decoration: underline; }"
            )
            _target = target
            btn.clicked.connect(lambda _c, t=_target: self._on_segment_clicked(t))
            self._seg_layout.insertWidget(self._seg_layout.count() - 1, btn)

            if i < len(segments) - 1:
                sep = QLabel("›")
                sep.setStyleSheet("color: #444; font-size: 12px; padding: 0 2px;")
                self._seg_layout.insertWidget(self._seg_layout.count() - 1, sep)

    @staticmethod
    def _build_segments(parts: list[str]) -> list[tuple[str, str]]:
        """Return (label, full_path) tuples for each path component."""
        result = []
        built = "/"
        for part in parts:
            built = str(PurePosixPath(built) / part)
            result.append((part, built))
        return result

    def _on_segment_clicked(self, path: str) -> None:
        log.debug("BreadcrumbBar: selected %s", path)
        self.path_selected.emit(path)
