"""
iPhone Storage Explorer — Desktop GUI entry point.

Usage:
    python desktop.py

The original terminal app remains fully intact:
    python main.py
"""
import os
import sys
import pathlib
import ctypes

# Force UTF-8 on Windows terminals
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "iphone.experiments.desktop"
        )
    except Exception:
        pass

# Inject bundled libimobiledevice tools directory into PATH (same as main.py)
_TOOLS_DIR = str(pathlib.Path.home() / "libimobiledevice")
if _TOOLS_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _TOOLS_DIR + os.pathsep + os.environ.get("PATH", "")

from src.gui.app import create_app
from src.gui.main_window import MainWindow


def main() -> None:
    app = create_app(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
