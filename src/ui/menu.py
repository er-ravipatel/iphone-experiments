"""
Interactive terminal menu system using Rich.
"""
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.prompt import Prompt

console = Console()


MAIN_MENU_ITEMS = [
    ("1", "Browse Files",          "Browse and transfer files on the device"),
    ("2", "Manage Apps",           "List, install, or uninstall apps"),
    ("3", "Photos & Videos",       "Import or export photos and videos"),
    ("4", "Backup Device",         "Create a full device backup"),
    ("5", "Restore Backup",        "Restore from a previous backup"),
    ("6", "Diagnostics",           "Battery, storage, and device details"),
    ("7", "Screenshot",            "Capture a screenshot from the device"),
    ("8", "Rename Device",         "Change the device name"),
    ("9", "Screen Mirror",         "Open a live mirror viewer window"),
    ("R", "Refresh",               "Refresh device info"),
    ("Q", "Quit",                  "Exit the application"),
]


def render_main_menu() -> None:
    """Print the main action menu."""
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Key",    style="bold yellow",  width=4)
    table.add_column("Action", style="bold white",   width=22)
    table.add_column("Description", style="dim white")

    for key, action, desc in MAIN_MENU_ITEMS:
        table.add_row(f"[{key}]", action, desc)

    console.print(Panel(table, title="[bold cyan]What would you like to do?[/bold cyan]", border_style="cyan"))


def prompt_choice(valid_keys: list[str] | None = None) -> str:
    """Prompt for a menu choice and return it uppercased."""
    if valid_keys is None:
        valid_keys = [k for k, _, _ in MAIN_MENU_ITEMS]
    valid_upper = [k.upper() for k in valid_keys]
    while True:
        choice = Prompt.ask("[bold cyan]>[/bold cyan]").strip().upper()
        if choice in valid_upper:
            return choice
        console.print(f"[red]Invalid choice '{choice}'. Options: {', '.join(valid_upper)}[/red]")


def prompt_choice_watching(
    valid_keys: list[str],
    device_check_fn,
    poll_interval: float = 1.5,
) -> str | None:
    """
    Non-blocking menu prompt on Windows (uses msvcrt).
    Polls device_check_fn() every poll_interval seconds.
    Returns the chosen key (uppercased), or None if the device disconnected.
    """
    valid_upper = [k.upper() for k in valid_keys]

    if sys.platform == "win32":
        import msvcrt
        console.print("[bold cyan]>:[/bold cyan] ", end="", highlight=False)
        buf = ""
        last_check = time.time()
        while True:
            # Check for keypress without blocking
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\r", "\n"):
                    # Enter pressed — validate buffer
                    key = buf.strip().upper()
                    buf = ""
                    console.print()   # newline after input
                    if key in valid_upper:
                        return key
                    console.print(f"[red]Invalid: '{key}'. Options: {', '.join(valid_upper)}[/red]")
                    console.print("[bold cyan]>:[/bold cyan] ", end="", highlight=False)
                elif ch == "\x08":  # backspace
                    if buf:
                        buf = buf[:-1]
                        console.print("\b \b", end="", highlight=False)
                else:
                    buf += ch
                    console.print(ch, end="", highlight=False)
            else:
                time.sleep(0.05)

            # Periodic device check
            if time.time() - last_check >= poll_interval:
                last_check = time.time()
                if not device_check_fn():
                    console.print()  # newline before disconnect message
                    return None
    else:
        # Non-Windows fallback: use blocking prompt, device check only between inputs
        while True:
            if not device_check_fn():
                return None
            choice = Prompt.ask("[bold cyan]>[/bold cyan]").strip().upper()
            if choice in valid_upper:
                return choice
            console.print(f"[red]Invalid: '{choice}'. Options: {', '.join(valid_upper)}[/red]")


def confirm(message: str) -> bool:
    """Ask yes/no and return True for yes."""
    reply = Prompt.ask(f"[yellow]{message}[/yellow] [dim](y/n)[/dim]").strip().lower()
    return reply in ("y", "yes")


def format_size(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "Unknown"
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024**3):.1f} GB"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024**2):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def estimate_duration(
    size_bytes: int | None = None,
    rate_mb_per_sec: float = 25.0,
    minimum_seconds: int = 2,
    fallback: str = "Depends on device and cable speed",
) -> str:
    if not size_bytes or size_bytes <= 0:
        return fallback

    seconds = max(minimum_seconds, int(size_bytes / (rate_mb_per_sec * 1024 * 1024)))
    if seconds < 60:
        return f"About {seconds} sec"

    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        if rem:
            return f"About {minutes} min {rem} sec"
        return f"About {minutes} min"

    hours, rem_minutes = divmod(minutes, 60)
    if rem_minutes:
        return f"About {hours} hr {rem_minutes} min"
    return f"About {hours} hr"


def confirm_action(
    title: str,
    details: list[tuple[str, str]],
    warning: str | None = None,
    prompt: str = "Continue with this action?",
) -> bool:
    lines = []
    for label, value in details:
        lines.append(f"[bold cyan]{label}:[/bold cyan] {value}")
    if warning:
        lines.append("")
        lines.append(f"[yellow]{warning}[/yellow]")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
        )
    )
    return confirm(prompt)


def prompt_path(message: str, default: str = "") -> str:
    """Ask for a file or directory path."""
    return Prompt.ask(f"[cyan]{message}[/cyan]", default=default).strip()


def print_section(title: str) -> None:
    console.rule(f"[bold cyan]{title}[/bold cyan]")


def print_success(msg: str) -> None:
    console.print(f"[bold green]✓[/bold green] {msg}")


def print_error(msg: str) -> None:
    console.print(f"[bold red]✗[/bold red] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[cyan]ℹ[/cyan] {msg}")


def pause() -> None:
    Prompt.ask("\n[dim]Press Enter to return to the main menu…[/dim]", default="")
