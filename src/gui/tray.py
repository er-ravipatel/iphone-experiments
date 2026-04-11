"""
System tray integration for the desktop app.
"""
from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMainWindow, QMenu, QSystemTrayIcon


class AppTray(QObject):
    def __init__(self, window: QMainWindow, icon: QIcon) -> None:
        super().__init__(window)
        self._window = window
        self._tray = QSystemTrayIcon(icon, window)
        self._tray.setToolTip("iPhone Storage Explorer")
        self._tray.activated.connect(self._on_activated)

        menu = QMenu()

        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)

        hide_action = QAction("Hide Window", self)
        hide_action.triggered.connect(self.hide_window)
        menu.addAction(hide_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(window.close)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.show()

    def set_tooltip(self, text: str) -> None:
        self._tray.setToolTip(text)

    def show_message(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.Information,
        timeout_ms: int = 8000,
    ) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.showMessage(title, message, icon, timeout_ms)

    def show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def hide_window(self) -> None:
        self._window.hide()

    def close(self) -> None:
        self._tray.hide()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.MiddleClick,
        ):
            if self._window.isVisible():
                self.hide_window()
            else:
                self.show_window()
