"""
Capture a screenshot from the connected device.
"""
import time
from pathlib import Path

from ..utils.runner import run
from ..ui.menu import console, print_success, print_error, print_info, prompt_path, pause
from ..ui.progress import spinner


def take_screenshot(udid: str) -> None:
    default_path = str(Path.home() / f"iphone_screenshot_{int(time.time())}.png")
    out_path = prompt_path("Save screenshot to", default=default_path)

    with spinner("Capturing screenshot…"):
        result = run("idevicescreenshot", out_path, udid=udid)

    if result.success or Path(out_path).exists():
        print_success(f"Screenshot saved to: {out_path}")
    else:
        print_error("Failed to capture screenshot.")
        detail = result.stderr or result.stdout
        if detail:
            console.print(f"[dim]{detail}[/dim]")

        detail_lower = detail.lower() if detail else ""
        if "invalid service" in detail_lower or "developer disk image" in detail_lower:
            print_info(
                "This device is not exposing the screenshot service right now.\n"
                "A matching Developer Disk Image usually needs to be mounted first.\n"
                "You can do that with ideviceimagemounter if you have the correct files\n"
                "for this iOS version, then try the screenshot again."
            )
        else:
            print_info(
                "Screenshot capture failed. Check that the phone is unlocked, trusted,\n"
                "and still connected, then try again."
            )
    pause()
