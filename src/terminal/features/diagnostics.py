"""
Device diagnostics: extended info, battery, reboot, shutdown.
"""
from rich.table import Table
from rich.panel import Panel
from rich import box

from ...device.info import DeviceInfo
from ...utils.runner import run
from ..ui.menu import console, print_success, print_error, print_info, confirm_action, pause


def show_full_diagnostics(info: DeviceInfo) -> None:
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=30)
    table.add_column("Value", style="white")

    fields = [
        ("Device Name",        info.name),
        ("Model",              info.model),
        ("Product Type",       info.product_type),
        ("iOS Version",        info.ios_version),
        ("Build Version",      info.build_version),
        ("Serial Number",      info.serial),
        ("UDID",               info.udid),
        ("CPU Architecture",   info.cpu_architecture),
        ("Device Color",       info.color),
        ("Wi-Fi Address",      info.wifi_address),
        ("Bluetooth Address",  info.bluetooth_address),
        ("Battery Level",      f"{info.battery_level}%"),
        ("Charging",           "Yes" if info.battery_charging else "No"),
        ("Total Storage",      f"{info.total_storage_gb} GB"),
        ("Used Storage",       f"{info.used_storage_gb} GB ({info.storage_percent_used}%)"),
        ("Free Storage",       f"{info.free_storage_gb} GB"),
        ("Activation State",   info.activation_state),
    ]

    for k, v in fields:
        table.add_row(k, v or "—")

    console.print(Panel(table, title="[bold cyan]Full Device Diagnostics[/bold cyan]", border_style="cyan"))
    pause()


def reboot_device(udid: str) -> None:
    if not confirm_action(
        "Reboot Device",
        [
            ("Action", "Restart the connected device"),
            ("Estimated Time", "About 1-2 min"),
            ("Availability", "The device will disconnect briefly during reboot"),
        ],
        warning="Any unsaved work on the device may be interrupted.",
    ):
        return
    result = run("idevicediagnostics", "restart", udid=udid)
    if result.success:
        print_success("Reboot command sent.")
    else:
        print_error(f"Failed: {result.stderr}")
    pause()


def shutdown_device(udid: str) -> None:
    if not confirm_action(
        "Shut Down Device",
        [
            ("Action", "Power off the connected device"),
            ("Estimated Time", "About 10-30 sec"),
            ("Availability", "The device will disconnect until powered on again"),
        ],
        warning="You will need to turn the device back on manually.",
    ):
        return
    result = run("idevicediagnostics", "shutdown", udid=udid)
    if result.success:
        print_success("Shutdown command sent.")
    else:
        print_error(f"Failed: {result.stderr}")
    pause()


def diagnostics_menu(info: DeviceInfo) -> None:
    from ..ui.menu import print_section, prompt_choice

    while True:
        print_section("Diagnostics")
        console.print("  [1] Full Device Info")
        console.print("  [2] Reboot Device")
        console.print("  [3] Shutdown Device")
        console.print("  [B] Back")
        console.print()

        choice = prompt_choice(["1", "2", "3", "B"])
        if choice == "1":
            show_full_diagnostics(info)
        elif choice == "2":
            reboot_device(info.udid)
        elif choice == "3":
            shutdown_device(info.udid)
        elif choice == "B":
            break
