"""
QApplication factory with dark theme stylesheet.
Import create_app() in desktop.py before any other Qt imports.
"""
from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont


# ── Stylesheet ─────────────────────────────────────────────────────────────────
# Dark palette consistent with the existing mirror.py Tkinter window.

STYLESHEET = """
/* ── Base ─────────────────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #141414;
    color: #e0e0e0;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* ── Sidebar ──────────────────────────────────────────────────── */
#Sidebar {
    background-color: #0d0d0d;
    border-right: 1px solid #252525;
}

#NavButton {
    background-color: transparent;
    color: #757575;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0px;
    text-align: left;
    padding: 10px 18px;
    font-size: 13px;
}
#NavButton:hover:enabled {
    background-color: #1a1a1a;
    color: #bdbdbd;
}
#NavButton:checked {
    background-color: #0d2233;
    color: #4fc3f7;
    border-left: 3px solid #4fc3f7;
    font-weight: bold;
}
#NavButton:disabled {
    color: #333333;
}

/* ── Device header ────────────────────────────────────────────── */
#DeviceHeader {
    background-color: #161616;
    border-bottom: 1px solid #252525;
}

/* ── Info cards ───────────────────────────────────────────────── */
#Card {
    background-color: #1c1c1c;
    border: 1px solid #272727;
    border-radius: 6px;
}
#CardTitle {
    color: #616161;
    font-size: 11px;
    letter-spacing: 0.5px;
}
#CardValue {
    color: #e0e0e0;
    font-size: 15px;
    font-weight: bold;
}

/* ── Tables ───────────────────────────────────────────────────── */
QTableWidget {
    background-color: #181818;
    border: 1px solid #272727;
    border-radius: 4px;
    gridline-color: #222222;
    color: #e0e0e0;
    selection-background-color: #0d2233;
    selection-color: #4fc3f7;
}
QTableWidget::item {
    padding: 6px 10px;
    border: none;
}
QTableWidget::item:alternate {
    background-color: #1c1c1c;
}
QHeaderView::section {
    background-color: #141414;
    color: #757575;
    border: none;
    border-bottom: 1px solid #272727;
    padding: 6px 10px;
    font-size: 11px;
    letter-spacing: 0.5px;
}

/* ── Scrollbars ───────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #141414;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #333333;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #4a4a4a;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: #141414;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #333333;
    border-radius: 4px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ── Buttons ──────────────────────────────────────────────────── */
QPushButton {
    background-color: #242424;
    color: #bdbdbd;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover {
    background-color: #2e2e2e;
    border-color: #444444;
    color: #e0e0e0;
}
QPushButton:pressed {
    background-color: #0d2233;
    border-color: #4fc3f7;
    color: #4fc3f7;
}
QPushButton:disabled {
    color: #333333;
    border-color: #222222;
    background-color: #1a1a1a;
}

/* ── Activity log ─────────────────────────────────────────────── */
#ActivityLog {
    background-color: #0d0d0d;
    border-top: 1px solid #252525;
}
#ActivityLogText {
    background-color: transparent;
    border: none;
    color: #555555;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
}

/* ── Labels ───────────────────────────────────────────────────── */
#PageTitle {
    color: #e0e0e0;
    font-size: 20px;
    font-weight: bold;
}
#StatusLabel {
    color: #616161;
    font-size: 12px;
}
#SectionLabel {
    color: #4fc3f7;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.8px;
}

/* ── Tooltips ─────────────────────────────────────────────────── */
QToolTip {
    background-color: #1c1c1c;
    color: #e0e0e0;
    border: 1px solid #333333;
    padding: 4px 8px;
}
"""


def create_app(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName("iPhone Storage Explorer")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("iphone-experiments")
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)
    return app
