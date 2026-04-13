"""
Standalone visual widgets used by the media page.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSplitter, QSplitterHandle,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap, QImage

from .workers import PhotoDecodeWorker
from ....terminal.features.media import VIDEO_EXTENSIONS

log = logging.getLogger(__name__)

# Extensions Qt can decode directly into QImage (no Pillow needed)
RENDERABLE = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}


# ── Grip splitter ──────────────────────────────────────────────────────────────

class GripSplitterHandle(QSplitterHandle):
    """Splitter handle that paints three grip dots as a drag affordance."""

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("#4fc3f7") if self.underMouse() else QColor("#5a5a5a")
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        cx = self.width() // 2
        cy = self.height() // 2
        r, gap = 2, 5
        for dy in (-gap, 0, gap):
            p.drawEllipse(cx - r, cy + dy - r, r * 2, r * 2)
        p.end()


class GripSplitter(QSplitter):
    """QSplitter that uses GripSplitterHandle for visual drag affordance."""

    def createHandle(self):  # noqa: N802
        return GripSplitterHandle(self.orientation(), self)


# ── Photo pop-out window ───────────────────────────────────────────────────────

class PhotoPopout(QWidget):
    """
    Floating full-resolution photo viewer with previous/next navigation.

    Args:
        local_path:  path to the initially displayed file (must exist)
        ext:         file extension of the initial file
        title:       window title suffix
        media_files: full list of media dicts from the grid (optional)
        cache:       cache directory Path (optional)
        current_row: index in media_files of the initially displayed file
    """

    def __init__(
        self,
        local_path: str,
        ext: str,
        title: str,
        media_files: list[dict] | None = None,
        cache: Path | None = None,
        current_row: int = 0,
    ) -> None:
        super().__init__(None, Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(960, 720)
        self.setFocusPolicy(Qt.StrongFocus)   # needed for keyPressEvent

        self._worker: PhotoDecodeWorker | None = None
        self._live_workers: set = set()   # keeps Python refs alive while threads run
        self._full_pixmap = QPixmap()
        self._fit_mode = True

        # Navigation state
        self._media_files: list[dict] = media_files or []
        self._cache: Path | None = cache
        self._current_row: int = current_row

        # Build UI
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # ── Toolbar ────────────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._prev_btn = QPushButton("‹ Prev")
        self._prev_btn.setFixedWidth(70)
        self._prev_btn.clicked.connect(self._go_prev)
        bar.addWidget(self._prev_btn)

        self._next_btn = QPushButton("Next ›")
        self._next_btn.setFixedWidth(70)
        self._next_btn.clicked.connect(self._go_next)
        bar.addWidget(self._next_btn)

        self._counter_lbl = QLabel()
        self._counter_lbl.setStyleSheet("color: #616161; font-size: 11px; padding: 0 6px;")
        bar.addWidget(self._counter_lbl)

        self._fit_btn = QPushButton("Fit to Window")
        self._fit_btn.setCheckable(True)
        self._fit_btn.setChecked(True)
        self._fit_btn.clicked.connect(self._toggle_fit)
        bar.addWidget(self._fit_btn)

        bar.addStretch()

        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color: #616161; font-size: 11px;")
        bar.addWidget(self._info_lbl)
        vbox.addLayout(bar)

        # ── Image area ─────────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { background: #0d0d0d; border: none; }")
        # Prevent scroll area and its viewport from stealing keyboard focus so
        # all key events are handled by this window's keyPressEvent directly.
        self._scroll.setFocusPolicy(Qt.NoFocus)
        self._img_lbl = QLabel("Loading…")
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent; color: #555;")
        self._img_lbl.setFocusPolicy(Qt.NoFocus)
        self._scroll.setWidget(self._img_lbl)
        self._scroll.setWidgetResizable(True)
        vbox.addWidget(self._scroll, stretch=1)

        # Prevent nav buttons from stealing keyboard focus
        for btn in (self._prev_btn, self._next_btn, self._fit_btn):
            btn.setFocusPolicy(Qt.NoFocus)

        # Load initial file then ensure this window owns keyboard focus
        self._load_file(local_path, ext, title)
        self.show()
        self.setFocus()

    # ── Navigation ─────────────────────────────────────────────────────────

    def _photo_indices(self) -> list[int]:
        """Indices in _media_files that are photos (not videos)."""
        return [
            i for i, f in enumerate(self._media_files)
            if Path(f["name"]).suffix.lower() not in VIDEO_EXTENSIONS
        ]

    def _go_prev(self) -> None:
        photos = self._photo_indices()
        if not photos:
            return
        try:
            pos = photos.index(self._current_row)
        except ValueError:
            pos = 0
        if pos > 0:
            self._navigate_to(photos[pos - 1])

    def _go_next(self) -> None:
        photos = self._photo_indices()
        if not photos:
            return
        try:
            pos = photos.index(self._current_row)
        except ValueError:
            pos = 0
        if pos < len(photos) - 1:
            self._navigate_to(photos[pos + 1])

    def _navigate_to(self, row: int) -> None:
        if not self._cache or row >= len(self._media_files):
            return
        f = self._media_files[row]
        local = str(self._cache / f["name"])
        ext   = Path(f["name"]).suffix.lower()
        self._current_row = row
        if Path(local).exists():
            self._load_file(local, ext, f["name"])
        else:
            self._img_lbl.setPixmap(QPixmap())
            self._img_lbl.setText(f"Not downloaded yet\n{f['name']}\n\nSelect it in the grid first.")
            self._info_lbl.setText("")
            self.setWindowTitle(f"Preview — {f['name']}")
            self._update_nav_state()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Left, Qt.Key_Up):
            self._go_prev()
        elif event.key() in (Qt.Key_Right, Qt.Key_Down):
            self._go_next()
        else:
            super().keyPressEvent(event)

    # ── File loading ────────────────────────────────────────────────────────

    def _load_file(self, local_path: str, ext: str, title: str) -> None:
        """Cancel any running decode, reset state, load the given file."""
        log.debug("PhotoPopout._load_file: %s (ext=%s)", local_path, ext)
        if self._worker is not None:
            # Disconnect so stale results are dropped, but keep the Python object
            # alive in _live_workers until the OS thread finishes — destroying a
            # running QThread crashes the process.
            try:
                self._worker.ready.disconnect()
            except RuntimeError:
                pass
            if self._worker.isRunning():
                log.debug("PhotoPopout: parking old worker in _live_workers")
                old = self._worker
                self._live_workers.add(old)
                old.finished.connect(lambda w=old: self._live_workers.discard(w))
        self._worker = None
        self._full_pixmap = QPixmap()
        self._img_lbl.setPixmap(QPixmap())
        self._img_lbl.setText("Loading…")
        self._info_lbl.setText("")
        self.setWindowTitle(f"Preview — {title}")
        self._update_nav_state()

        if ext in RENDERABLE:
            img = QImage(local_path)
            if not img.isNull():
                self._full_pixmap = QPixmap.fromImage(img)
                self._apply_pixmap()
            else:
                log.warning("PhotoPopout: QImage null for %s", local_path)
                self._img_lbl.setText("Cannot render image")
        else:
            log.debug("PhotoPopout: launching PhotoDecodeWorker for %s", local_path)
            self._worker = PhotoDecodeWorker(local_path, ext, 8000)
            self._worker.ready.connect(self._on_decoded)
            self._live_workers.add(self._worker)
            self._worker.finished.connect(
                lambda w=self._worker: self._live_workers.discard(w)
            )
            self._worker.start()

    def _update_nav_state(self) -> None:
        """Refresh Prev/Next enabled state and counter label."""
        photos = self._photo_indices()
        if not photos or len(photos) < 2:
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            self._counter_lbl.setText("")
            return
        try:
            pos = photos.index(self._current_row)
        except ValueError:
            pos = 0
        self._prev_btn.setEnabled(pos > 0)
        self._next_btn.setEnabled(pos < len(photos) - 1)
        self._counter_lbl.setText(f"{pos + 1} / {len(photos)}")

    # ── Rendering ───────────────────────────────────────────────────────────

    def _on_decoded(self, px: QPixmap) -> None:
        self._full_pixmap = px
        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        if self._full_pixmap.isNull():
            self._img_lbl.setText("Cannot render image")
            return
        w, h = self._full_pixmap.width(), self._full_pixmap.height()
        self._info_lbl.setText(f"{w} × {h} px")
        self._img_lbl.setText("")
        self._render()

    def _render(self) -> None:
        if self._full_pixmap.isNull():
            return
        if self._fit_mode:
            avail = self._scroll.viewport().size()
            px = self._full_pixmap.scaled(avail, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            px = self._full_pixmap
        self._img_lbl.setPixmap(px)

    def _toggle_fit(self, checked: bool) -> None:
        self._fit_mode = checked
        self._fit_btn.setText("Fit to Window" if checked else "Full Size")
        self._scroll.setWidgetResizable(checked)
        self._render()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit_mode:
            self._render()
