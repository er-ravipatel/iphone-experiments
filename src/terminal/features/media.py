"""
Photo and video browser — Windows Explorer-style navigation via pymobiledevice3 AFC.
Browse DCIM folders, select individual files or bulk-export entire folders.
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
from ..ui.progress import progress_bar, spinner


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tiff", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp"}
MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS


def _fmt_size(size: int) -> str:
    return format_size(size)


def _media_icon(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "[magenta]VID[/magenta]"
    return "[cyan]IMG[/cyan]"


# ── AFC helpers ────────────────────────────────────────────────────────────────

async def _listdir(udid: str, path: str) -> list[dict]:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        names = sorted(await afc.listdir(path))

        # Stat all entries concurrently (8 in-flight at once) instead of
        # one round-trip per file — cuts 300-file listing from ~4s to ~0.5s.
        sem = asyncio.Semaphore(8)

        async def _stat_one(name: str) -> dict:
            full = str(PurePosixPath(path) / name)
            async with sem:
                try:
                    info = await afc.stat(full)
                    is_dir = info.get("st_ifmt") == "S_IFDIR"
                    size   = int(info.get("st_size", 0))
                except Exception:
                    is_dir = False
                    size   = 0
            ext = Path(name).suffix.lower()
            return {
                "name":     name,
                "path":     full,
                "is_dir":   is_dir,
                "size":     size,
                "is_media": ext in MEDIA_EXTENSIONS,
            }

        return list(await asyncio.gather(*[_stat_one(n) for n in names]))


async def _download_one(udid: str, remote_path: str, local_path: str) -> int:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        data = await afc.get_file_contents(remote_path)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(data)
        return len(data)


async def _download_many(udid: str, entries: list[dict], dest_dir: str) -> tuple[int, int]:
    """Download multiple files. Returns (count, total_bytes)."""
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    lockdown = await create_using_usbmux(serial=udid)
    count = 0
    total_bytes = 0

    async with AfcService(lockdown) as afc:
        for e in entries:
            local = dest / e["name"]
            if not local.exists():
                data = await afc.get_file_contents(e["path"])
                local.write_bytes(data)
                total_bytes += len(data)
            count += 1

    return count, total_bytes


# ── UI ─────────────────────────────────────────────────────────────────────────

def _render_entries(entries: list[dict], current: str, page: int, page_size: int = 20):
    """Render a paginated table of directory entries. Returns total pages."""
    total = len(entries)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    chunk = entries[start: start + page_size]

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("#",    style="dim",    width=5)
    table.add_column("Type", width=5)
    table.add_column("Name", style="white",  width=36)
    table.add_column("Size", style="yellow", width=12)

    for i, e in enumerate(chunk, start + 1):
        if e["is_dir"]:
            # Count how many media files are inside (show folder summary)
            table.add_row(str(i), "[cyan]DIR[/cyan]", e["name"] + "/", "")
        else:
            table.add_row(str(i), _media_icon(e["name"]), e["name"], _fmt_size(e["size"]))

    console.print(table)

    media_in_view = [e for e in chunk if e["is_media"]]
    total_media = [e for e in entries if e["is_media"]]
    if total_media:
        total_size = sum(e["size"] for e in total_media)
        console.print(
            f"  [dim]{len(total_media)} media files in this folder  "
            f"({_fmt_size(total_size)} total)[/dim]"
        )

    if total_pages > 1:
        console.print(f"  [dim]Page {page + 1}/{total_pages}[/dim]")

    return total_pages, chunk, start


def _export_with_progress(udid: str, files: list[dict], dest: str) -> None:
    """Run a bulk download with a Rich progress bar."""
    if not files:
        print_info("No media files to export.")
        return

    with progress_bar(f"Exporting {len(files)} files...", total=len(files)) as (prog, task):
        async def run():
            from pymobiledevice3.lockdown import create_using_usbmux
            from pymobiledevice3.services.afc import AfcService

            dest_path = Path(dest)
            dest_path.mkdir(parents=True, exist_ok=True)
            lockdown = await create_using_usbmux(serial=udid)
            async with AfcService(lockdown) as afc:
                for f in files:
                    local = dest_path / f["name"]
                    if not local.exists():
                        data = await afc.get_file_contents(f["path"])
                        local.write_bytes(data)
                    prog.advance(task)

        asyncio.run(run())

    print_success(f"Exported {len(files)} files to: {dest}")


def browse_media(udid: str) -> None:
    """Main media browser — navigate DCIM like Windows Explorer."""
    current = "/DCIM"
    page = 0
    PAGE_SIZE = 20

    while True:
        print_section(f"Photos & Videos  |  {current}")

        try:
            entries = asyncio.run(_listdir(udid, current))
        except Exception as e:
            print_error(f"Could not read folder: {e}")
            pause()
            return

        media_files = [e for e in entries if e["is_media"]]
        total_pages, page_chunk, page_start = _render_entries(
            entries, current, page, PAGE_SIZE
        )

        console.print()
        console.print("  [bold]Navigate:[/bold]")
        console.print("  [#]   Open folder / select file to download")
        if total_pages > 1:
            console.print("  [N]   Next page    [V]  Previous page")
        console.print()
        console.print("  [bold]Export:[/bold]")
        console.print("  [E]   Export ALL media in this folder")
        console.print("  [S]   Select multiple files to export")
        if current != "/DCIM":
            console.print("  [A]   Export everything in ALL subfolders (bulk)")
        console.print()
        if current != "/DCIM":
            console.print("  [B]   Go back to parent folder")
            console.print("  [Q]   Back to main menu")
        else:
            console.print("  [B]   Back to main menu")
        console.print()

        valid = [str(i) for i in range(page_start + 1, page_start + len(page_chunk) + 1)]
        extra = ["E", "S", "B"]
        if current != "/DCIM":
            extra += ["Q", "A"]
        if total_pages > 1:
            extra += ["N", "V"]

        choice = prompt_choice(valid + extra)

        # ── Navigation ──────────────────────────────────────────────────────
        if choice == "B":
            if current == "/DCIM":
                break
            current = str(PurePosixPath(current).parent)
            page = 0

        elif choice == "Q":
            break

        elif choice == "N":
            page = min(page + 1, total_pages - 1)

        elif choice == "V":
            page = max(page - 1, 0)

        # ── Export all in current folder ────────────────────────────────────
        elif choice == "E":
            if not media_files:
                print_error("No media files in this folder.")
                pause()
                continue
            folder_name = PurePosixPath(current).name or "DCIM"
            default_dest = str(Path.home() / "iphone_photos" / folder_name)
            total_size = sum(f["size"] for f in media_files)
            console.print(f"\n  [bold cyan]{len(media_files)}[/bold cyan] files  [yellow]{_fmt_size(total_size)}[/yellow]")
            console.print(f"  Save to: [cyan]{default_dest}[/cyan]\n")
            console.print("  [Y] Yes, export here")
            console.print("  [C] Choose a different folder")
            console.print("  [X] Cancel\n")
            action = prompt_choice(["Y", "C", "X"])
            if action == "X":
                continue
            dest = prompt_path("Export to folder", default=default_dest) if action == "C" else default_dest
            if not confirm_action(
                "Export Folder Media",
                [
                    ("Source Folder", current),
                    ("Files", str(len(media_files))),
                    ("Total Size", format_size(total_size)),
                    ("Save To", dest),
                    ("Estimated Time", estimate_duration(total_size, rate_mb_per_sec=20.0)),
                ],
            ):
                continue
            _export_with_progress(udid, media_files, dest)
            pause()

        # ── Select multiple ─────────────────────────────────────────────────
        elif choice == "S":
            file_entries = [e for e in page_chunk if not e["is_dir"]]
            if not file_entries:
                print_error("No files on this page to select.")
                pause()
                continue

            console.print("\n  Enter file numbers separated by commas (e.g. 1,3,5)")
            console.print("  Or type [bold]ALL[/bold] to select all on this page\n")
            sel = prompt_path("Selection").strip().upper()

            if sel == "ALL":
                selected = file_entries
            else:
                try:
                    indices = [int(x.strip()) - 1 - page_start for x in sel.split(",")]
                    selected = [file_entries[i] for i in indices if 0 <= i < len(file_entries)]
                except (ValueError, IndexError):
                    print_error("Invalid selection.")
                    pause()
                    continue

            if not selected:
                print_error("No valid files selected.")
                pause()
                continue

            default_dest = str(Path.home() / "iphone_photos")
            total_size = sum(f["size"] for f in selected)
            console.print(f"\n  [bold cyan]{len(selected)}[/bold cyan] files selected  [yellow]{_fmt_size(total_size)}[/yellow]")
            console.print(f"  Save to: [cyan]{default_dest}[/cyan]\n")
            console.print("  [Y] Yes, export here")
            console.print("  [C] Choose a different folder")
            console.print("  [X] Cancel\n")
            action = prompt_choice(["Y", "C", "X"])
            if action == "X":
                continue
            dest = prompt_path("Export to folder", default=default_dest) if action == "C" else default_dest
            if not confirm_action(
                "Export Selected Media",
                [
                    ("Source Folder", current),
                    ("Files", str(len(selected))),
                    ("Total Size", format_size(total_size)),
                    ("Save To", dest),
                    ("Estimated Time", estimate_duration(total_size, rate_mb_per_sec=20.0)),
                ],
            ):
                continue
            _export_with_progress(udid, selected, dest)
            pause()

        # ── Bulk export all subfolders ───────────────────────────────────────
        elif choice == "A":
            print_info("Scanning all subfolders...")
            try:
                all_files = asyncio.run(_collect_all_media(udid, current))
            except Exception as e:
                print_error(f"Scan failed: {e}")
                pause()
                continue

            if not all_files:
                print_error("No media files found.")
                pause()
                continue

            total_size = sum(f["size"] for f in all_files)
            console.print(
                f"\n  Found [bold cyan]{len(all_files)}[/bold cyan] files "
                f"([yellow]{_fmt_size(total_size)}[/yellow])\n"
            )
            dest = prompt_path(
                "Export all to folder",
                default=str(Path.home() / "iphone_photos"),
            )
            if confirm_action(
                "Bulk Export Media",
                [
                    ("Source Root", current),
                    ("Files", str(len(all_files))),
                    ("Total Size", format_size(total_size)),
                    ("Save To", dest),
                    ("Estimated Time", estimate_duration(total_size, rate_mb_per_sec=20.0)),
                ],
                warning="This can take a while for large libraries.",
            ):
                _export_with_progress(udid, all_files, dest)
            pause()

        # ── Open folder / select file ────────────────────────────────────────
        else:
            try:
                idx = int(choice) - 1
                e = entries[idx]
                if e["is_dir"]:
                    current = e["path"]
                    page = 0
                else:
                    # Single file download
                    default_dest = str(Path.home() / "iphone_photos" / e["name"])
                    console.print(f"\n  [bold white]{e['name']}[/bold white]  [yellow]{_fmt_size(e['size'])}[/yellow]")
                    console.print(f"  Save to: [cyan]{default_dest}[/cyan]")
                    console.print()
                    console.print("  [Y] Yes, save here")
                    console.print("  [C] Choose a different path")
                    console.print("  [X] Cancel")
                    console.print()
                    action = prompt_choice(["Y", "C", "X"])
                    if action == "X":
                        continue
                    elif action == "C":
                        dest = prompt_path("Save to", default=default_dest)
                    else:
                        dest = default_dest
                    if not confirm_action(
                        "Download Media File",
                        [
                            ("File", e["name"]),
                            ("Source", e["path"]),
                            ("Size", format_size(e["size"])),
                            ("Save To", dest),
                            ("Estimated Time", estimate_duration(e["size"], rate_mb_per_sec=20.0)),
                        ],
                    ):
                        continue
                    with spinner(f"Downloading {e['name']}..."):
                        size = asyncio.run(_download_one(udid, e["path"], dest))
                    print_success(f"Saved {_fmt_size(size)} to: {dest}")
                    pause()
            except (ValueError, IndexError):
                print_error("Invalid selection.")


async def _collect_all_media(udid: str, root: str) -> list[dict]:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    files = []

    async with AfcService(lockdown) as afc:
        async def walk(path: str):
            try:
                names = await afc.listdir(path)
            except Exception:
                return
            for name in sorted(names):
                full = str(PurePosixPath(path) / name)
                try:
                    info = await afc.stat(full)
                    is_dir = info.get("st_ifmt") == "S_IFDIR"
                    size = int(info.get("st_size", 0))
                except Exception:
                    is_dir = False
                    size = 0
                if is_dir:
                    await walk(full)
                elif Path(name).suffix.lower() in MEDIA_EXTENSIONS:
                    files.append({"name": name, "path": full, "size": size})

        await walk(root)

    return files


def media_menu(udid: str) -> None:
    browse_media(udid)
