"""
Parse device information from ideviceinfo output.
"""
from dataclasses import dataclass, field
from ..utils.runner import run

# Friendly model name lookup table (ProductType -> display name)
MODEL_NAMES: dict[str, str] = {
    # iPhone 16 series
    "iPhone17,1": "iPhone 16 Pro Max", "iPhone17,2": "iPhone 16 Pro",
    "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus",
    # iPhone 15 series
    "iPhone16,1": "iPhone 15", "iPhone16,2": "iPhone 15 Plus",
    "iPhone16,3": "iPhone 15 Pro", "iPhone16,4": "iPhone 15 Pro Max",
    # iPhone 14 series
    "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 14", "iPhone15,5": "iPhone 14 Plus",
    # iPhone 13 series
    "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13",
    "iPhone14,2": "iPhone 13 Pro", "iPhone14,3": "iPhone 13 Pro Max",
    # iPhone 12 series
    "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12",
    "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    # iPhone 11 series
    "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max", "iPhone12,8": "iPhone SE (2nd gen)",
    # iPhone XS/XR
    "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max",
    "iPhone11,6": "iPhone XS Max", "iPhone11,8": "iPhone XR",
    # iPhone X/8/7
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8",
    "iPhone10,2": "iPhone 8 Plus", "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X",
    "iPhone9,1": "iPhone 7", "iPhone9,3": "iPhone 7",
    "iPhone9,2": "iPhone 7 Plus", "iPhone9,4": "iPhone 7 Plus",
    # iPad (common)
    "iPad13,18": "iPad (10th gen)", "iPad13,19": "iPad (10th gen)",
    "iPad12,1": "iPad (9th gen)", "iPad12,2": "iPad (9th gen)",
    "iPad14,3": "iPad Pro 11\" (4th gen)", "iPad14,4": "iPad Pro 11\" (4th gen)",
    "iPad14,5": "iPad Pro 12.9\" (6th gen)", "iPad14,6": "iPad Pro 12.9\" (6th gen)",
    "iPad13,4": "iPad Pro 11\" (3rd gen)", "iPad13,8": "iPad Pro 12.9\" (5th gen)",
    "iPad13,1": "iPad Air (4th gen)", "iPad13,2": "iPad Air (4th gen)",
    "iPad13,16": "iPad Air (5th gen)", "iPad13,17": "iPad Air (5th gen)",
    "iPad11,1": "iPad mini (5th gen)", "iPad11,2": "iPad mini (5th gen)",
    "iPad14,1": "iPad mini (6th gen)", "iPad14,2": "iPad mini (6th gen)",
}


@dataclass
class DeviceInfo:
    udid: str = ""
    name: str = "Unknown"
    model: str = "Unknown"
    product_type: str = ""
    ios_version: str = "Unknown"
    build_version: str = ""
    serial: str = "Unknown"
    color: str = ""
    total_storage_bytes: int = 0
    free_storage_bytes: int = 0
    battery_level: int = 0
    battery_charging: bool = False
    cpu_architecture: str = ""
    wifi_address: str = ""
    bluetooth_address: str = ""
    device_class: str = ""
    activation_state: str = ""
    paired: bool = True
    raw: dict = field(default_factory=dict)

    @property
    def total_storage_gb(self) -> float:
        # Apple presents device capacity in decimal GB, not binary GiB.
        return round(self.total_storage_bytes / (1000 ** 3), 1)

    @property
    def free_storage_gb(self) -> float:
        return round(self.free_storage_bytes / (1000 ** 3), 1)

    @property
    def used_storage_gb(self) -> float:
        return round(self.total_storage_gb - self.free_storage_gb, 1)

    @property
    def storage_percent_used(self) -> int:
        if self.total_storage_bytes == 0:
            return 0
        return int((self.total_storage_bytes - self.free_storage_bytes) / self.total_storage_bytes * 100)


def _parse_ideviceinfo_output(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _get_storage_via_pymobiledevice(udid: str) -> tuple[int, int]:
    """Returns (total_bytes, free_bytes) using pymobiledevice3."""
    try:
        import asyncio
        from pymobiledevice3.lockdown import create_using_usbmux

        async def _fetch():
            lockdown = await create_using_usbmux(serial=udid)
            disk = await lockdown.get_value("com.apple.disk_usage")
            total = int(disk.get("TotalDiskCapacity", 0))
            # AmountDataAvailable matches the free space reported on-device.
            free = int(disk.get("AmountDataAvailable", 0))
            return total, free

        return asyncio.run(_fetch())
    except Exception:
        return 0, 0


def get_device_info(udid: str) -> "DeviceInfo | None":
    result = run("ideviceinfo", udid=udid)
    if not result.success:
        return None

    raw = _parse_ideviceinfo_output(result.stdout)

    # Battery info
    bat_result = run("ideviceinfo", "-q", "com.apple.mobile.battery", udid=udid)
    bat_raw = _parse_ideviceinfo_output(bat_result.stdout) if bat_result.success else {}

    # Storage via pymobiledevice3 (handles nested plist correctly)
    total, free = _get_storage_via_pymobiledevice(udid)

    try:
        battery = int(bat_raw.get("BatteryCurrentCapacity", raw.get("BatteryCurrentCapacity", 0)))
    except ValueError:
        battery = 0

    charging_val = bat_raw.get("BatteryIsCharging", raw.get("BatteryIsCharging", "false"))
    charging = charging_val.lower() in ("true", "1", "yes")

    product_type = raw.get("ProductType", "")
    friendly_model = MODEL_NAMES.get(product_type, product_type or raw.get("HardwareModel", "Unknown"))

    return DeviceInfo(
        udid=udid,
        name=raw.get("DeviceName", "Unknown"),
        model=friendly_model,
        product_type=product_type,
        ios_version=raw.get("ProductVersion", "Unknown"),
        build_version=raw.get("BuildVersion", ""),
        serial=raw.get("SerialNumber", "Unknown"),
        color=raw.get("DeviceColor", ""),
        total_storage_bytes=total,
        free_storage_bytes=free,
        battery_level=battery,
        battery_charging=charging,
        cpu_architecture=raw.get("CPUArchitecture", ""),
        wifi_address=raw.get("WiFiAddress", ""),
        bluetooth_address=raw.get("BluetoothAddress", ""),
        device_class=raw.get("DeviceClass", "iPhone"),
        activation_state=raw.get("ActivationState", ""),
        paired=True,
        raw=raw,
    )
