"""
iPhone Storage Explorer — Desktop GUI entry point.

Usage:
    python desktop.py

The original terminal app remains fully intact:
    python main.py
"""
import logging
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

# ── Logging setup ──────────────────────────────────────────────────────────────
_LOG_FILE = pathlib.Path(__file__).parent / "iphone_desktop.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
# Suppress noisy third-party loggers
for _noisy in ("asyncio", "pymobiledevice3", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

log = logging.getLogger("desktop")


def main() -> None:
    log.info("Desktop app starting — log file: %s", _LOG_FILE)
    try:
        app = create_app(sys.argv)
        window = MainWindow()
        window.show()
        exit_code = app.exec()
        log.info("Desktop app exiting with code %d", exit_code)
        sys.exit(exit_code)
    except Exception:
        log.exception("Unhandled exception in main()")
        raise


if __name__ == "__main__":
    main()
