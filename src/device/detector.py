"""
Detect connected iPhone/iPad devices via idevice_id.
"""
from ..utils.runner import run


def list_devices() -> list[str]:
    """
    Return a list of UDIDs for currently connected devices.
    Returns an empty list if none are connected or tools are missing.
    """
    result = run("idevice_id", "-l")
    if not result.success or not result.stdout:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def is_device_connected() -> bool:
    return len(list_devices()) > 0
