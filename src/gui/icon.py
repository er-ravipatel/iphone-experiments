"""
Application icon generation for window, taskbar, and tray use.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


def _draw_phone_mark(painter: QPainter, size: int) -> None:
    phone = QRectF(size * 0.30, size * 0.14, size * 0.40, size * 0.72)
    phone_path = QPainterPath()
    phone_path.addRoundedRect(phone, size * 0.08, size * 0.08)

    painter.setPen(QPen(QColor("#eff8ff"), max(1, size // 24)))
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(phone_path)

    notch = QRectF(size * 0.43, size * 0.18, size * 0.14, size * 0.03)
    painter.fillRect(notch, QColor("#eff8ff"))

    screen = QRectF(size * 0.36, size * 0.24, size * 0.28, size * 0.43)
    screen_fill = QLinearGradient(screen.topLeft(), screen.bottomRight())
    screen_fill.setColorAt(0.0, QColor("#10385a"))
    screen_fill.setColorAt(1.0, QColor("#1e6ca1"))
    painter.fillRect(screen, screen_fill)

    storage = QRectF(size * 0.38, size * 0.60, size * 0.24, size * 0.055)
    painter.fillRect(storage, QColor("#2de0cc"))
    warn = QRectF(storage.left() + storage.width() * 0.70, storage.top(), storage.width() * 0.30, storage.height())
    painter.fillRect(warn, QColor("#ffca57"))

    lens = QRectF(size * 0.58, size * 0.15, size * 0.14, size * 0.14)
    lens_fill = QLinearGradient(lens.topLeft(), lens.bottomRight())
    lens_fill.setColorAt(0.0, QColor("#8af7e8"))
    lens_fill.setColorAt(1.0, QColor("#1aa7ff"))
    painter.setPen(Qt.NoPen)
    painter.setBrush(lens_fill)
    painter.drawEllipse(lens)


def _render_icon(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    outer = QRectF(size * 0.05, size * 0.05, size * 0.90, size * 0.90)
    radius = size * 0.22

    bg = QLinearGradient(outer.topLeft(), outer.bottomRight())
    bg.setColorAt(0.0, QColor("#34115b"))
    bg.setColorAt(0.50, QColor("#7a2ee6"))
    bg.setColorAt(1.0, QColor("#ff4fa3"))

    panel = QPainterPath()
    panel.addRoundedRect(outer, radius, radius)
    painter.fillPath(panel, bg)

    gloss = QLinearGradient(outer.topLeft(), QPointF(outer.left(), outer.bottom()))
    gloss.setColorAt(0.0, QColor(255, 255, 255, 56))
    gloss.setColorAt(0.4, QColor(255, 255, 255, 10))
    gloss.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(panel, gloss)

    painter.setPen(QPen(QColor(255, 255, 255, 52), max(1, size // 48)))
    painter.drawPath(panel)

    _draw_phone_mark(painter, size)

    painter.end()
    return pixmap


def create_app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
        icon.addPixmap(_render_icon(size))
    return icon


def write_icon_files(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    icon = create_app_icon()
    png_path = root / "app-icon.png"
    ico_path = root / "app-icon.ico"
    icon.pixmap(256, 256).save(str(png_path), "PNG")
    icon.pixmap(256, 256).save(str(ico_path), "ICO")
