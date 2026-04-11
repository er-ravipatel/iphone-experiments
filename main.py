"""
iPhone Storage Explorer — Cross-platform terminal tool
Entry point: auto-detects connected iPhones and presents an interactive menu.

Usage:
    python main.py
"""
import os
import time
import sys
import pathlib

# Force UTF-8 output on Windows terminals to avoid encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Inject bundled tools directory into PATH for this session
# so the app works immediately without requiring a new terminal.
_TOOLS_DIR = str(pathlib.Path.home() / "libimobiledevice")
if _TOOLS_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _TOOLS_DIR + os.pathsep + os.environ.get("PATH", "")

from rich.console import Console

from src.utils.platform import check_tools, install_instructions
from src.device.detector import list_devices
from src.device.info import get_device_info, DeviceInfo
from src.ui.dashboard import render_device_dashboard, render_no_device, render_tools_missing
from src.ui.menu import (
    render_main_menu, prompt_choice, prompt_choice_watching,
    print_error, print_info, print_success, console
)
from src.features.diagnostics import diagnostics_menu
from src.features.apps import apps_menu
from src.features.backup import backup_menu
from src.features.media import media_menu
from src.features.files import files_menu
from src.features.screenshot import take_screenshot
from src.features.rename import rename_device
from src.features.mirror import open_mirror_window

POLL_INTERVAL = 2  # seconds between device polls when no device is connected


def check_setup() -> bool:
    """
    Verify that required libimobiledevice tools are available.
    Returns True if all critical tools are present.
    """
    tools = check_tools()
    missing = [name for name, path in tools.items() if path is None]

    # Only idevice_id and ideviceinfo are strictly required to start
    critical = {"idevice_id", "ideviceinfo"}
    missing_critical = [t for t in missing if t in critical]

    if missing_critical:
        render_tools_missing(missing_critical, install_instructions())
        return False
    return True


def wait_for_device() -> list[str]:
    """
    Poll until at least one device is connected.
    Returns the list of UDIDs.
    """
    render_no_device()
    while True:
        udids = list_devices()
        if udids:
            return udids
        time.sleep(POLL_INTERVAL)


def run_main_loop(info: DeviceInfo) -> str:
    """
    Show dashboard + menu for a connected device.
    Returns 'quit', 'refresh', or 'disconnected'.
    """
    render_device_dashboard(info)
    render_main_menu()

    def is_connected() -> bool:
        return info.udid in list_devices()

    choice = prompt_choice_watching(
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "R", "Q"],
        device_check_fn=is_connected,
    )

    if choice is None:
        return "disconnected"

    if choice == "1":
        files_menu(info.udid)
    elif choice == "2":
        apps_menu(info.udid)
    elif choice == "3":
        media_menu(info.udid)
    elif choice == "4":
        backup_menu(info)
    elif choice == "5":
        backup_menu(info)   # restore is inside backup_menu
    elif choice == "6":
        diagnostics_menu(info)
    elif choice == "7":
        take_screenshot(info.udid)
    elif choice == "8":
        rename_device(info.udid, info.name)
    elif choice == "9":
        open_mirror_window(info)
    elif choice == "R":
        return "refresh"
    elif choice == "Q":
        return "quit"

    return "continue"


def main() -> None:
    console.print()

    # ── 1. Check tools ──────────────────────────────────────────────────────
    if not check_setup():
        console.print("\n[dim]Press Ctrl+C to exit.[/dim]")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
        sys.exit(1)

    # ── 2. Main loop ────────────────────────────────────────────────────────
    try:
        while True:
            # Wait for a device
            udids = list_devices()
            if not udids:
                udids = wait_for_device()

            udid = udids[0]  # Use the first connected device

            # Fetch device info
            info = get_device_info(udid)
            if not info:
                print_error(
                    "Device found but could not read info.\n"
                    "  • Unlock your iPhone\n"
                    "  • Tap 'Trust' on the 'Trust This Computer?' prompt\n"
                    "  • Try reconnecting the cable"
                )
                time.sleep(3)
                continue

            # Run the interactive menu
            while True:
                action = run_main_loop(info)

                if action == "quit":
                    console.print("\n[dim]Goodbye![/dim]")
                    sys.exit(0)
                elif action == "disconnected":
                    render_no_device()
                    break
                elif action == "refresh":
                    info = get_device_info(udid) or info
                # "continue" loops back to the same menu

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted. Goodbye![/dim]")
        sys.exit(0)


if __name__ == "__main__":
    main()
