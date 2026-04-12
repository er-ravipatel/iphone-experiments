"""
Parse device information from ideviceinfo output.
"""
from __future__ import annotations

import base64
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
    # ── Core identity ──────────────────────────────────────────────────────
    udid: str = ""
    name: str = "Unknown"
    model: str = "Unknown"           # friendly name, e.g. "iPhone 12 Pro"
    product_type: str = ""           # e.g. "iPhone13,3"
    ios_version: str = "Unknown"
    build_version: str = ""
    serial: str = "Unknown"
    color: str = ""

    # ── Extended identity ──────────────────────────────────────────────────
    model_number: str = ""           # e.g. "MGMN3" (SKU / part number)
    hardware_model: str = ""         # e.g. "D53pAP" (internal board name)
    hardware_platform: str = ""      # e.g. "t8101"
    imei: str = ""
    imei2: str = ""
    meid: str = ""
    iccid: str = ""                  # SIM card ID
    phone_number: str = ""
    region_info: str = ""            # e.g. "LL/A"

    # ── Hardware ───────────────────────────────────────────────────────────
    cpu_architecture: str = ""
    board_id: str = ""               # e.g. "14"
    chip_id: str = ""                # e.g. "0x8101"
    die_id: str = ""
    baseband_version: str = ""
    firmware_version: str = ""
    mlb_serial: str = ""             # motherboard serial

    # ── Connectivity ───────────────────────────────────────────────────────
    wifi_address: str = ""
    bluetooth_address: str = ""
    ethernet_address: str = ""

    # ── Storage ───────────────────────────────────────────────────────────
    total_storage_bytes: int = 0
    free_storage_bytes: int = 0

    # ── Battery ───────────────────────────────────────────────────────────
    battery_level: int = 0
    battery_charging: bool = False
    battery_external_connected: bool = False
    battery_fully_charged: bool = False

    # ── Status ────────────────────────────────────────────────────────────
    device_class: str = ""
    activation_state: str = ""
    password_protected: bool = False
    find_my_locked: bool = False     # decoded from NonVolatileRAM fm-activation-locked
    developer_mode: bool = False     # com.apple.security.mac.amfi
    paired: bool = True
    raw: dict = field(default_factory=dict)

    # ── Computed properties ────────────────────────────────────────────────

    @property
    def total_storage_gb(self) -> float:
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

    @property
    def icloud_locked(self) -> bool:
        """True if iCloud Activation Lock is active (device not yours or erased)."""
        # If activation state is not "Activated", the device is iCloud locked
        return self.activation_state not in ("Activated", "")

    @property
    def chip_id_hex(self) -> str:
        """Chip ID as hex string for display, e.g. '0x8101'."""
        try:
            return f"0x{int(self.chip_id):04X}" if self.chip_id else ""
        except (ValueError, TypeError):
            return self.chip_id


# ── Parsing helpers ────────────────────────────────────────────────────────────

def _parse_ideviceinfo_output(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _parse_nvram(raw: dict[str, str]) -> dict[str, str]:
    """Extract key=value pairs from the NonVolatileRAM multiline block."""
    nvram: dict[str, str] = {}
    in_nvram = False
    for line in raw.get("__raw_text__", "").splitlines():
        if line.startswith("NonVolatileRAM:"):
            in_nvram = True
            continue
        if in_nvram:
            if line.startswith(" "):
                stripped = line.strip()
                if ":" in stripped:
                    k, _, v = stripped.partition(":")
                    nvram[k.strip()] = v.strip()
            else:
                in_nvram = False
    return nvram


def _decode_b64_bool(value: str) -> bool:
    """Decode a base64-encoded string and return True if it decodes to 'YES'."""
    try:
        return base64.b64decode(value).decode("utf-8", errors="ignore").upper().strip() == "YES"
    except Exception:
        return False


def _get_storage_via_pymobiledevice(udid: str) -> tuple[int, int]:
    """Returns (total_bytes, free_bytes) using pymobiledevice3."""
    try:
        import asyncio
        from pymobiledevice3.lockdown import create_using_usbmux

        async def _fetch() -> tuple[int, int]:
            lockdown = await create_using_usbmux(serial=udid)
            disk = await lockdown.get_value("com.apple.disk_usage")
            total = int(disk.get("TotalDiskCapacity", 0))
            free  = int(disk.get("AmountDataAvailable", 0))
            return total, free

        return asyncio.run(_fetch())
    except Exception:
        return 0, 0


def _get_developer_mode(udid: str) -> bool:
    """Query developer mode status via pymobiledevice3."""
    try:
        import asyncio
        from pymobiledevice3.lockdown import create_using_usbmux

        async def _fetch() -> bool:
            lockdown = await create_using_usbmux(serial=udid)
            val = await lockdown.get_value("com.apple.security.mac.amfi",
                                           "DeveloperModeStatus")
            return bool(val)

        return asyncio.run(_fetch())
    except Exception:
        return False


# ── Public API ─────────────────────────────────────────────────────────────────

def get_device_info(udid: str) -> "DeviceInfo | None":
    result = run("ideviceinfo", udid=udid)
    if not result.success:
        return None

    # Keep raw text for NVRAM block parsing
    raw_text = result.stdout
    raw = _parse_ideviceinfo_output(raw_text)
    raw["__raw_text__"] = raw_text

    # Battery domain
    bat_result = run("ideviceinfo", "-q", "com.apple.mobile.battery", udid=udid)
    bat = _parse_ideviceinfo_output(bat_result.stdout) if bat_result.success else {}

    # Storage via pymobiledevice3
    total, free = _get_storage_via_pymobiledevice(udid)

    # Developer mode
    dev_mode = _get_developer_mode(udid)

    # NVRAM block (Find My lock)
    nvram = _parse_nvram(raw)
    find_my_locked = _decode_b64_bool(nvram.get("fm-activation-locked", ""))

    # Battery fields
    try:
        battery = int(bat.get("BatteryCurrentCapacity", raw.get("BatteryCurrentCapacity", 0)))
    except ValueError:
        battery = 0

    def _bool(d: dict, key: str) -> bool:
        return d.get(key, "false").lower() in ("true", "1", "yes")

    charging          = _bool(bat, "BatteryIsCharging")
    ext_connected     = _bool(bat, "ExternalConnected")
    fully_charged     = _bool(bat, "FullyCharged")
    password_prot     = _bool(raw, "PasswordProtected")

    # Chip ID as decimal string (convert to hex later in property)
    chip_id_raw = raw.get("ChipID", "")

    product_type  = raw.get("ProductType", "")
    friendly_model = MODEL_NAMES.get(product_type, product_type or raw.get("HardwareModel", "Unknown"))

    # MEID: prefer top-level key, fallback to CarrierBundleInfoArray parsing
    meid = raw.get("MobileEquipmentIdentifier", "")

    return DeviceInfo(
        # Core
        udid=udid,
        name=raw.get("DeviceName", "Unknown"),
        model=friendly_model,
        product_type=product_type,
        ios_version=raw.get("ProductVersion", "Unknown"),
        build_version=raw.get("BuildVersion", ""),
        serial=raw.get("SerialNumber", "Unknown"),
        color=raw.get("DeviceColor", ""),
        # Extended identity
        model_number=raw.get("ModelNumber", ""),
        hardware_model=raw.get("HardwareModel", ""),
        hardware_platform=raw.get("HardwarePlatform", ""),
        imei=raw.get("InternationalMobileEquipmentIdentity", ""),
        imei2=raw.get("InternationalMobileEquipmentIdentity2", ""),
        meid=meid,
        iccid=raw.get("IntegratedCircuitCardIdentity", ""),
        phone_number=raw.get("PhoneNumber", ""),
        region_info=raw.get("RegionInfo", ""),
        # Hardware
        cpu_architecture=raw.get("CPUArchitecture", ""),
        board_id=raw.get("BoardId", ""),
        chip_id=chip_id_raw,
        die_id=raw.get("DieID", ""),
        baseband_version=raw.get("BasebandVersion", ""),
        firmware_version=raw.get("FirmwareVersion", ""),
        mlb_serial=raw.get("MLBSerialNumber", ""),
        # Connectivity
        wifi_address=raw.get("WiFiAddress", ""),
        bluetooth_address=raw.get("BluetoothAddress", ""),
        ethernet_address=raw.get("EthernetAddress", ""),
        # Storage
        total_storage_bytes=total,
        free_storage_bytes=free,
        # Battery
        battery_level=battery,
        battery_charging=charging,
        battery_external_connected=ext_connected,
        battery_fully_charged=fully_charged,
        # Status
        device_class=raw.get("DeviceClass", "iPhone"),
        activation_state=raw.get("ActivationState", ""),
        password_protected=password_prot,
        find_my_locked=find_my_locked,
        developer_mode=dev_mode,
        paired=True,
        raw=raw,
    )
