"""
Shared constants and utility functions for the media package.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QListWidgetItem
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QFont

from ....terminal.features.media import VIDEO_EXTENSIONS

# ── Grid constants ─────────────────────────────────────────────────────────────

THUMB_SIZE  = 155   # icon canvas (px)
ITEM_SIZE   = 162   # grid cell width (7px padding around thumb)
LABEL_CHARS = 14    # max chars shown under each thumbnail

# ── File utilities ─────────────────────────────────────────────────────────────

def cache_dir(udid: str) -> Path:
    base = Path(tempfile.gettempdir()) / "iphone_explorer" / udid[:8]
    base.mkdir(parents=True, exist_ok=True)
    return base


def open_system(path: str) -> None:
    """Open a local file with the OS default application."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def fmt_size(size: int) -> str:
    if not size:
        return ""
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size / 1_000:.0f} KB"
    return f"{size} B"

# ── Thumbnail placeholder icons ────────────────────────────────────────────────

def make_placeholder(label: str, bg: str, fg: str) -> QIcon:
    px = QPixmap(THUMB_SIZE, THUMB_SIZE)
    px.fill(QColor(bg))
    p = QPainter(px)
    p.setPen(QColor(fg).darker(120))
    p.drawRect(px.rect().adjusted(0, 0, -1, -1))
    p.setPen(QColor(fg))
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.drawText(px.rect(), 0x0084, label)   # Qt.AlignCenter = 0x0084
    p.end()
    return QIcon(px)


def ext_placeholder(ext: str) -> QIcon:
    """Per-extension placeholder icon — shows the actual format (HEIC, MOV, etc.)."""
    ext_upper = ext.lstrip(".").upper() or "FILE"
    if ext_upper in ("HEIC", "HEIF"):
        return make_placeholder(ext_upper, "#1c1a14", "#ffa726")
    if ext.lower() in VIDEO_EXTENSIONS:
        return make_placeholder(ext_upper, "#14141f", "#4fc3f7")
    return make_placeholder(ext_upper, "#1a1a1a", "#9e9e9e")
