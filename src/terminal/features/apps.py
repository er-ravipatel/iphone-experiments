"""
App management via pymobiledevice3 InstallationProxy — no ideviceinstaller needed.
"""
import asyncio
from pathlib import Path

from rich.table import Table
from rich import box

from ..ui.menu import (
    console, print_section, print_success, print_error, print_info,
    prompt_path, prompt_choice, confirm_action,
    format_size, estimate_duration, pause
)
from ..ui.progress import spinner


async def _list_apps(udid: str, app_type: str = "User") -> list[dict]:
    """
    app_type: 'User', 'System', or 'Any'
    Returns list of dicts with name, bundle_id, version, size.
    """
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    lockdown = await create_using_usbmux(serial=udid)
    async with InstallationProxyService(lockdown) as svc:
        apps = await svc.get_apps(application_type=app_type)

    result = []
    for bundle_id, info in apps.items():
        result.append({
            "bundle_id": bundle_id,
            "name": info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle_id,
            "version": info.get("CFBundleShortVersionString", ""),
            "size": info.get("StaticDiskUsage", 0),
        })

    return sorted(result, key=lambda x: x["name"].lower())


async def _uninstall_app(udid: str, bundle_id: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    lockdown = await create_using_usbmux(serial=udid)
    async with InstallationProxyService(lockdown) as svc:
        await svc.uninstall(bundle_id)


async def _install_app(udid: str, ipa_path: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    lockdown = await create_using_usbmux(serial=udid)
    async with InstallationProxyService(lockdown) as svc:
        await svc.install_from_local(ipa_path)


def _fmt_size(size: int) -> str:
    return format_size(size) if size else ""


def list_apps(udid: str) -> None:
    app_type = "User"
    page = 0
    PAGE_SIZE = 20

    while True:
        print_section(f"Installed Apps  ({app_type})")

        try:
            with spinner(f"Fetching {app_type.lower()} apps..."):
                apps = asyncio.run(_list_apps(udid, app_type))
        except Exception as e:
            print_error(f"Could not fetch apps: {e}")
            pause()
            return

        if not apps:
            print_info(f"No {app_type.lower()} apps found.")
            pause()
            return

        total_pages = max(1, (len(apps) + PAGE_SIZE - 1) // PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        start = page * PAGE_SIZE
        chunk = apps[start: start + PAGE_SIZE]

        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        table.add_column("#",          style="dim",        width=5)
        table.add_column("App Name",   style="bold white", width=30)
        table.add_column("Version",    style="yellow",     width=10)
        table.add_column("Size",       style="cyan",       width=10)
        table.add_column("Bundle ID",  style="dim white",  width=36)

        for i, app in enumerate(chunk, start + 1):
            table.add_row(
                str(i),
                app["name"],
                app["version"],
                _fmt_size(app["size"]),
                app["bundle_id"],
            )

        console.print(table)
        console.print(f"  [dim]{len(apps)} apps total[/dim]")
        if total_pages > 1:
            console.print(f"  [dim]Page {page + 1}/{total_pages}[/dim]")

        console.print()
        if total_pages > 1:
            console.print("  [N] Next page    [V] Previous page")
        console.print("  [T] Toggle User / System apps")
        console.print("  [B] Back")
        console.print()

        extra = ["T", "B"] + (["N", "V"] if total_pages > 1 else [])
        choice = prompt_choice(extra)

        if choice == "B":
            break
        elif choice == "N":
            page = min(page + 1, total_pages - 1)
        elif choice == "V":
            page = max(page - 1, 0)
        elif choice == "T":
            app_type = "System" if app_type == "User" else "User"
            page = 0


def uninstall_app(udid: str) -> None:
    print_info("Fetching user apps...")
    try:
        apps = asyncio.run(_list_apps(udid, "User"))
    except Exception as e:
        print_error(f"Could not fetch apps: {e}")
        pause()
        return

    if not apps:
        print_info("No user apps found.")
        pause()
        return

    # Show compact list
    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("#",         style="dim",        width=5)
    table.add_column("App Name",  style="bold white", width=32)
    table.add_column("Version",   style="yellow",     width=10)
    table.add_column("Bundle ID", style="dim white",  width=36)
    for i, app in enumerate(apps, 1):
        table.add_row(str(i), app["name"], app["version"], app["bundle_id"])
    console.print(table)

    sel = prompt_path("Enter # of app to uninstall (or B to cancel)").strip().upper()
    if sel == "B":
        return
    try:
        app = apps[int(sel) - 1]
    except (ValueError, IndexError):
        print_error("Invalid selection.")
        pause()
        return

    if not confirm_action(
        "Uninstall App",
        [
            ("App", app["name"]),
            ("Bundle ID", app["bundle_id"]),
            ("Version", app["version"] or "Unknown"),
            ("App Size", _fmt_size(app["size"]) or "Unknown"),
            ("Estimated Time", estimate_duration(app["size"], rate_mb_per_sec=12.0, fallback="Usually under 1 min")),
        ],
        warning="This cannot be undone.",
    ):
        return

    with spinner(f"Uninstalling {app['name']}..."):
        try:
            asyncio.run(_uninstall_app(udid, app["bundle_id"]))
            print_success(f"'{app['name']}' uninstalled.")
        except Exception as e:
            print_error(f"Failed: {e}")
    pause()


def install_app(udid: str) -> None:
    ipa_path = prompt_path("Path to .ipa file")
    if not ipa_path or not Path(ipa_path).exists():
        print_error(f"File not found: {ipa_path}")
        pause()
        return

    ipa_size = Path(ipa_path).stat().st_size
    if not confirm_action(
        "Install App",
        [
            ("Package", Path(ipa_path).name),
            ("Source", ipa_path),
            ("Package Size", format_size(ipa_size)),
            ("Estimated Time", estimate_duration(ipa_size, rate_mb_per_sec=12.0, fallback="About 1-3 min")),
        ],
        warning="The app will be installed on the connected device.",
    ):
        return

    with spinner(f"Installing {Path(ipa_path).name}..."):
        try:
            asyncio.run(_install_app(udid, ipa_path))
            print_success("App installed successfully.")
        except Exception as e:
            print_error(f"Installation failed: {e}")
    pause()


def apps_menu(udid: str) -> None:
    while True:
        print_section("App Manager")
        console.print("  [1] List Installed Apps")
        console.print("  [2] Install App (.ipa)")
        console.print("  [3] Uninstall App")
        console.print("  [B] Back")
        console.print()

        choice = prompt_choice(["1", "2", "3", "B"])
        if choice == "1":
            list_apps(udid)
        elif choice == "2":
            install_app(udid)
        elif choice == "3":
            uninstall_app(udid)
        elif choice == "B":
            break
