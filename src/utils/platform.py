"""
Platform detection and libimobiledevice tool path resolution.
"""
import sys
import shutil
import platform
from pathlib import Path


def get_platform() -> str:
    """Returns 'windows', 'macos', or 'linux'."""
    s = sys.platform
    if s == "win32":
        return "windows"
    if s == "darwin":
        return "macos"
    return "linux"


def find_tool(name: str) -> str | None:
    """
    Locate a libimobiledevice CLI tool binary.
    Checks:
      1. PATH (works after brew install / apt install)
      2. vendor/ directory bundled alongside this project
    Returns the full path string, or None if not found.
    """
    # Check PATH first
    found = shutil.which(name)
    if found:
        return found

    # Check a local vendor/ directory (bundled binaries for Windows)
    plat = get_platform()
    vendor_dir = Path(__file__).resolve().parents[2] / "vendor" / plat
    candidates = [vendor_dir / name, vendor_dir / f"{name}.exe"]
    for c in candidates:
        if c.exists():
            return str(c)

    return None


REQUIRED_TOOLS = [
    "idevice_id",
    "ideviceinfo",
    "ideviceinstaller",
    "idevicebackup2",
    "idevicescreenshot",
    "idevicename",
    "idevicediagnostics",
]


def check_tools() -> dict[str, str | None]:
    """Return a dict mapping each required tool name to its path (or None)."""
    return {tool: find_tool(tool) for tool in REQUIRED_TOOLS}


def install_instructions() -> str:
    plat = get_platform()
    if plat == "macos":
        return (
            "Install libimobiledevice via Homebrew:\n"
            "  brew install libimobiledevice ideviceinstaller\n"
        )
    if plat == "linux":
        return (
            "Install libimobiledevice:\n"
            "  sudo apt install libimobiledevice-utils ideviceinstaller usbmuxd\n"
            "  sudo systemctl start usbmuxd\n"
        )
    # Windows
    return (
        "On Windows:\n"
        "  1. Install 'Apple Devices' from the Microsoft Store (free)\n"
        "     OR install iTunes from apple.com\n"
        "  2. Download libimobiledevice Windows binaries from:\n"
        "     https://github.com/libimobiledevice-win32/imobiledevice-net/releases\n"
        "  3. Add the folder containing the tools to your PATH\n"
    )


