"""
DeviceService — wraps src/device/ with structured ServiceResult responses.

Both the terminal app and the GUI call this; neither needs to know the
underlying tool names or asyncio details.
"""
from __future__ import annotations

from ..core.results import ServiceResult
from ..device.detector import list_devices, is_device_connected
from ..device.info import get_device_info, DeviceInfo
from ..utils.platform import check_tools


class DeviceService:
    """Thin wrapper over the existing device layer."""

    # ── Detection ──────────────────────────────────────────────────────────

    def list_devices(self) -> list[str]:
        """Return UDIDs of all currently connected devices."""
        return list_devices()

    def is_connected(self) -> bool:
        return is_device_connected()

    # ── Device info ────────────────────────────────────────────────────────

    def get_device_info(self, udid: str) -> ServiceResult[DeviceInfo]:
        info = get_device_info(udid)
        if info is None:
            return ServiceResult(
                success=False,
                error=(
                    "Could not read device info. "
                    "Unlock your iPhone and tap 'Trust' if prompted."
                ),
            )
        return ServiceResult(success=True, data=info)

    def get_first_device_info(self) -> ServiceResult[DeviceInfo]:
        """Convenience: detect + fetch info for the first connected device."""
        udids = list_devices()
        if not udids:
            return ServiceResult(success=False, error="No device connected.")
        return self.get_device_info(udids[0])

    # ── Tool availability ──────────────────────────────────────────────────

    def check_tools(self) -> ServiceResult[dict[str, str | None]]:
        """
        Returns success=True if the two critical tools are present.
        warnings lists any non-critical missing tools.
        """
        tools = check_tools()
        missing = [name for name, path in tools.items() if path is None]
        critical = {"idevice_id", "ideviceinfo"}
        missing_critical = [t for t in missing if t in critical]

        return ServiceResult(
            success=len(missing_critical) == 0,
            data=tools,
            warnings=[f"Missing: {t}" for t in missing if t not in critical],
            error=(
                f"Missing critical tools: {', '.join(missing_critical)}"
                if missing_critical else ""
            ),
        )
