"""
AppSettings — typed, persistent configuration via QSettings.

All functions construct QSettings() at call time (not import time), so
this module is safe to import before QApplication is created — just don't
*call* any function until create_app() has run.

Storage location (set by create_app via setOrganizationName/setApplicationName):
  Windows : HKCU\\Software\\iphone-experiments\\iPhone Storage Explorer
  macOS   : ~/Library/Preferences/com.iphone-experiments.iPhone Storage Explorer
  Linux   : ~/.config/iphone-experiments/iPhone Storage Explorer.conf
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

# ── Storage keys ───────────────────────────────────────────────────────────────
_KEY_BACKUP_DIR    = "backup/directory"
_KEY_SCREENSHOT_MS = "diagnostics/screenshot_interval_ms"
_KEY_TOOLS_PATH    = "tools/libimobiledevice_path"

# ── Defaults (mirrors previous hardcoded values) ───────────────────────────────
_DEFAULT_BACKUP_DIR    = str(Path.home() / "iphone_backups")
_DEFAULT_SCREENSHOT_MS = 4000   # 4 s
_DEFAULT_TOOLS_PATH    = ""     # blank = auto-detect from PATH / vendor/


# ── Backup directory ───────────────────────────────────────────────────────────

def backup_dir() -> str:
    """Return the configured backup directory (default: ~/iphone_backups)."""
    return QSettings().value(_KEY_BACKUP_DIR, _DEFAULT_BACKUP_DIR, type=str)


def set_backup_dir(path: str) -> None:
    QSettings().setValue(_KEY_BACKUP_DIR, path or _DEFAULT_BACKUP_DIR)


# ── Diagnostics screenshot interval ───────────────────────────────────────────

def screenshot_interval_ms() -> int:
    """
    Return auto-screenshot interval in ms.  0 means 'Disabled'.
    The type=int kwarg is mandatory on Windows where the registry stores
    everything as str — without it start("4000") silently fails.
    """
    return int(QSettings().value(_KEY_SCREENSHOT_MS, _DEFAULT_SCREENSHOT_MS, type=int))


def set_screenshot_interval_ms(ms: int) -> None:
    QSettings().setValue(_KEY_SCREENSHOT_MS, ms)


# ── libimobiledevice tools directory ──────────────────────────────────────────

def tools_path() -> str:
    """
    Return user-configured libimobiledevice directory, or "" for auto-detect.
    find_tool() in utils/platform.py checks this before PATH / vendor/.
    """
    return QSettings().value(_KEY_TOOLS_PATH, _DEFAULT_TOOLS_PATH, type=str)


def set_tools_path(path: str) -> None:
    QSettings().setValue(_KEY_TOOLS_PATH, path)
