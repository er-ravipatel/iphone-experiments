"""
Device dashboard: renders the device info panel using Rich.
"""
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.text import Text
from rich import box

from ...device.info import DeviceInfo

console = Console()


def _battery_bar(level: int, charging: bool) -> Text:
    filled = level // 10
    bar = "█" * filled + "░" * (10 - filled)
    color = "green" if level > 40 else ("yellow" if level > 20 else "red")
    icon = "+" if charging else " "
    t = Text()
    t.append(f"{icon} [", style="white")
    t.append(bar, style=color)
    t.append(f"] {level}%", style="white")
    return t


def _storage_bar(used_gb: float, total_gb: float, pct: int) -> Text:
    filled = pct // 10
    bar = "█" * filled + "░" * (10 - filled)
    color = "green" if pct < 70 else ("yellow" if pct < 90 else "red")
    t = Text()
    t.append("  [", style="white")
    t.append(bar, style=color)
    t.append(f"] {used_gb} / {total_gb} GB", style="white")
    return t


def render_device_dashboard(info: DeviceInfo) -> None:
    """Print a rich device info panel to the terminal."""
    console.clear()

    # ── Header ──────────────────────────────────────────────────────────────
    header = Text(justify="center")
    header.append("  iPhone Storage Explorer  ", style="bold white on blue")
    console.print(header)
    console.print()

    # ── Device info table ───────────────────────────────────────────────────
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Key", style="bold cyan", width=22)
    table.add_column("Value", style="white")

    table.add_row("Device Name", info.name)
    table.add_row("Model", info.model or info.product_type)
    table.add_row("iOS Version", f"{info.ios_version}  ({info.build_version})")
    table.add_row("Serial Number", info.serial)
    table.add_row("CPU", info.cpu_architecture)
    table.add_row("Wi-Fi", info.wifi_address)
    table.add_row("Bluetooth", info.bluetooth_address)
    table.add_row("UDID", info.udid[:20] + "…")

    # Battery row
    table.add_row("Battery", _battery_bar(info.battery_level, info.battery_charging))

    # Storage row
    if info.total_storage_bytes > 0:
        table.add_row(
            "Storage",
            _storage_bar(info.used_storage_gb, info.total_storage_gb, info.storage_percent_used),
        )
    else:
        table.add_row("Storage", "Unknown")

    panel = Panel(
        table,
        title=f"[bold green]{info.device_class} Connected[/bold green]",
        border_style="green",
        padding=(0, 1),
    )
    console.print(panel)


def render_no_device() -> None:
    """Print a waiting-for-device panel."""
    console.clear()
    header = Text(justify="center")
    header.append("  iPhone Storage Explorer  ", style="bold white on blue")
    console.print(header)
    console.print()
    console.print(
        Panel(
            "[yellow]No iPhone detected.[/yellow]\n\n"
            "  - Connect your iPhone via USB\n"
            "  - Unlock the screen\n"
            "  - Tap [bold]Trust[/bold] on the 'Trust This Computer?' prompt\n\n"
            "[dim]Waiting for device...[/dim]",
            title="[bold red]No Device[/bold red]",
            border_style="red",
        )
    )


def render_tools_missing(missing: list[str], instructions: str) -> None:
    """Print a setup instructions panel when libimobiledevice is not installed."""
    console.clear()
    header = Text(justify="center")
    header.append("  iPhone Storage Explorer  ", style="bold white on blue")
    console.print(header)
    console.print()
    msg = "[red]Required tools not found:[/red]\n"
    for t in missing:
        msg += f"  • [bold]{t}[/bold]\n"
    msg += f"\n[yellow]{instructions}[/yellow]"
    console.print(Panel(msg, title="[bold red]Setup Required[/bold red]", border_style="red"))
