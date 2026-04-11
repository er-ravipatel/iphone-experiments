"""
File browser using pymobiledevice3 AFC — works on all platforms including Windows.
"""
import asyncio
from pathlib import Path, PurePosixPath

from rich.table import Table
from rich import box

from ..ui.menu import (
    console, print_section, print_success, print_error, print_info,
    prompt_path, prompt_choice, confirm_action,
    format_size, estimate_duration, pause
)
from ..ui.progress import spinner


async def _list_dir(udid: str, path: str) -> list[dict]:
    """Return entries in path as list of dicts with name, is_dir, size."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        names = await afc.listdir(path)
        entries = []
        for name in sorted(names):
            full = str(PurePosixPath(path) / name)
            try:
                info = await afc.stat(full)
                is_dir = info.get("st_ifmt") == "S_IFDIR"
                size = int(info.get("st_size", 0))
            except Exception:
                is_dir = False
                size = 0
            entries.append({"name": name, "is_dir": is_dir, "size": size})
        return entries


async def _download_file(udid: str, remote_path: str, local_path: str) -> int:
    """Download a file from AFC to local disk. Returns bytes written."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        data = await afc.get_file_contents(remote_path)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(data)
        return len(data)


async def _upload_file(udid: str, local_path: str, remote_path: str) -> int:
    """Upload a local file to AFC. Returns bytes written."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    data = Path(local_path).read_bytes()
    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        await afc.set_file_contents(remote_path, data)
        return len(data)


async def _delete_path(udid: str, remote_path: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        await afc.rm(remote_path, recursive=True)


def _fmt_size(size: int) -> str:
    return format_size(size)


def browse_files(udid: str) -> None:
    current = "/"

    while True:
        print_section(f"Files: {current}")

        try:
            entries = asyncio.run(_list_dir(udid, current))
        except Exception as e:
            print_error(f"Could not read directory: {e}")
            pause()
            return

        if not entries:
            print_info("(empty folder)")

        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        table.add_column("#",    style="dim",    width=4)
        table.add_column("Name", style="white",  width=38)
        table.add_column("Type", style="cyan",   width=6)
        table.add_column("Size", style="yellow", width=12)

        for i, e in enumerate(entries, 1):
            if e["is_dir"]:
                table.add_row(str(i), e["name"] + "/", "DIR", "")
            else:
                table.add_row(str(i), e["name"], "FILE", _fmt_size(e["size"]))

        console.print(table)
        console.print()
        console.print("  [#]  Enter folder / select file")
        console.print("  [D]  Download file to computer")
        console.print("  [P]  Upload (Put) file to this folder")
        console.print("  [X]  Delete file or folder")
        if current != "/":
            console.print("  [B]  Go back to parent folder")
            console.print("  [Q]  Back to main menu")
        else:
            console.print("  [B]  Back to main menu")
        console.print()

        nav_keys = [str(i) for i in range(1, len(entries) + 1)]
        extra = ["D", "P", "X", "B"] + (["Q"] if current != "/" else [])
        choice = prompt_choice(nav_keys + extra)

        if choice == "Q":
            # Q always exits to main menu
            break

        elif choice == "B":
            if current == "/":
                # At root, B exits to main menu
                break
            else:
                # In a subfolder, B goes up to parent
                parent = str(PurePosixPath(current).parent)
                current = parent if parent else "/"

        elif choice == "D":
            src_num = prompt_path("Enter # of file to download")
            try:
                e = entries[int(src_num) - 1]
                if e["is_dir"]:
                    print_error("Cannot download a folder directly.")
                else:
                    remote = str(PurePosixPath(current) / e["name"])
                    dest = prompt_path("Save to local path", default=str(Path.home() / e["name"]))
                    if not confirm_action(
                        "Download File",
                        [
                            ("File", e["name"]),
                            ("Source", remote),
                            ("Save To", dest),
                            ("Size", format_size(e["size"])),
                            ("Estimated Time", estimate_duration(e["size"], rate_mb_per_sec=20.0)),
                        ],
                    ):
                        pause()
                        continue
                    with spinner(f"Downloading {e['name']}..."):
                        size = asyncio.run(_download_file(udid, remote, dest))
                    print_success(f"Saved {_fmt_size(size)} to: {dest}")
            except (ValueError, IndexError):
                print_error("Invalid selection.")
            pause()

        elif choice == "P":
            local = prompt_path("Local file path to upload")
            if not local or not Path(local).exists():
                print_error(f"File not found: {local}")
            else:
                remote = str(PurePosixPath(current) / Path(local).name)
                local_size = Path(local).stat().st_size
                if not confirm_action(
                    "Upload File",
                    [
                        ("File", Path(local).name),
                        ("Source", local),
                        ("Destination", remote),
                        ("Size", format_size(local_size)),
                        ("Estimated Time", estimate_duration(local_size, rate_mb_per_sec=20.0)),
                    ],
                ):
                    pause()
                    continue
                with spinner(f"Uploading {Path(local).name}..."):
                    size = asyncio.run(_upload_file(udid, local, remote))
                print_success(f"Uploaded {_fmt_size(size)} to: {remote}")
            pause()

        elif choice == "X":
            del_num = prompt_path("Enter # of item to delete")
            try:
                e = entries[int(del_num) - 1]
                remote = str(PurePosixPath(current) / e["name"])
                if confirm_action(
                    "Delete Device Item",
                    [
                        ("Item", e["name"]),
                        ("Path", remote),
                        ("Type", "Folder" if e["is_dir"] else "File"),
                        ("Size", "Unknown" if e["is_dir"] else format_size(e["size"])),
                        ("Estimated Time", "Usually a few seconds"),
                    ],
                    warning="This cannot be undone.",
                ):
                    asyncio.run(_delete_path(udid, remote))
                    print_success(f"Deleted: {e['name']}")
            except (ValueError, IndexError):
                print_error("Invalid selection.")
            pause()

        else:
            try:
                e = entries[int(choice) - 1]
                if e["is_dir"]:
                    current = str(PurePosixPath(current) / e["name"])
                else:
                    remote = str(PurePosixPath(current) / e["name"])
                    console.print(f"  [bold]{e['name']}[/bold]  {_fmt_size(e['size'])}")
                    dest = prompt_path("Save to", default=str(Path.home() / e["name"]))
                    if confirm_action(
                        "Download File",
                        [
                            ("File", e["name"]),
                            ("Source", remote),
                            ("Save To", dest),
                            ("Size", format_size(e["size"])),
                            ("Estimated Time", estimate_duration(e["size"], rate_mb_per_sec=20.0)),
                        ],
                    ):
                        with spinner(f"Downloading..."):
                            size = asyncio.run(_download_file(udid, remote, dest))
                        print_success(f"Saved {_fmt_size(size)} to: {dest}")
                    pause()
            except (ValueError, IndexError):
                print_error("Invalid selection.")


def files_menu(udid: str) -> None:
    browse_files(udid)
