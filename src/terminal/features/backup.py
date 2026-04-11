"""
Backup and restore via idevicebackup2.
"""
from pathlib import Path
from rich.table import Table
from rich import box

from ...device.info import DeviceInfo
from ...utils.runner import run, run_streaming
from ..ui.menu import (
    console, print_section, print_success, print_error, print_info,
    prompt_path, prompt_choice, confirm, confirm_action,
    format_size, estimate_duration, pause
)
from ..ui.progress import stream_output


DEFAULT_BACKUP_DIR = str(Path.home() / "iphone_backups")


def _list_local_backups(backup_dir: str) -> list[Path]:
    d = Path(backup_dir)
    if not d.exists():
        return []
    # Each subdirectory named after a UDID is a backup
    return sorted(
        [p for p in d.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def create_backup(info: DeviceInfo) -> None:
    udid = info.udid
    backup_dir = prompt_path("Backup destination folder", default=DEFAULT_BACKUP_DIR)
    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    encrypted = confirm("Encrypt backup?")
    if encrypted:
        password = prompt_path("Set backup password")
        if not password:
            print_error("Backup password cannot be empty.")
            pause()
            return

        print_info("Enabling backup encryption on the device...")
        encryption_result = run("idevicebackup2", "encryption", "on", password, udid=udid)
        if not encryption_result.success:
            print_error(f"Could not enable backup encryption: {encryption_result.stderr}")
            pause()
            return

    estimated_size = info.used_storage_gb * (1024**3)
    if not confirm_action(
        "Create Backup",
        [
            ("Device", info.name),
            ("Destination", backup_dir),
            ("Estimated Backup Size", format_size(int(estimated_size))),
            ("Used Device Storage", f"{info.used_storage_gb} GB"),
            ("Estimated Time", estimate_duration(int(estimated_size), rate_mb_per_sec=18.0, fallback="Several minutes")),
            ("Encryption", "Enabled" if encrypted else "Off"),
        ],
        warning="Keep the iPhone connected until the backup finishes.",
    ):
        return

    cmd_args = ["backup", "--full", backup_dir]

    print_info(f"Starting backup to: {backup_dir}")
    print_info("This may take several minutes. Do not disconnect the device.")
    console.print()

    lines = run_streaming("idevicebackup2", *cmd_args, udid=udid)
    stream_output(lines, title="Backup Progress", task_message="Preparing backup...")

    backup_path = Path(backup_dir) / udid
    if backup_path.exists():
        print_success(f"Backup complete: {backup_path}")
    else:
        print_error("Backup may have failed. Check output above.")
    pause()


def restore_backup(info: DeviceInfo) -> None:
    udid = info.udid
    backup_dir = prompt_path("Backup folder (containing UDID subfolder)", default=DEFAULT_BACKUP_DIR)
    backups = _list_local_backups(backup_dir)

    if not backups:
        print_error(f"No backups found in: {backup_dir}")
        pause()
        return

    table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
    table.add_column("#",      style="dim",   width=4)
    table.add_column("UDID",   style="cyan",  width=44)
    table.add_column("Date",   style="white", width=20)

    for i, p in enumerate(backups, 1):
        import datetime
        mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(str(i), p.name, mtime)

    console.print(table)
    choice = prompt_path("Enter # of backup to restore (or 'b' to go back)")
    if choice.lower() == "b":
        return
    try:
        idx = int(choice) - 1
        selected = backups[idx]
    except (ValueError, IndexError):
        print_error("Invalid selection.")
        pause()
        return

    password_arg = []
    if confirm("Is this backup encrypted?"):
        password = prompt_path("Enter backup password")
        if not password:
            print_error("Backup password cannot be empty.")
            pause()
            return
        password_arg = ["--password", password]

    backup_size = _dir_size_bytes(selected)
    if not confirm_action(
        "Restore Backup",
        [
            ("Target Device", info.name),
            ("Backup UDID", selected.name),
            ("Backup Folder", str(selected)),
            ("Backup Size", format_size(backup_size)),
            ("Estimated Time", estimate_duration(backup_size, rate_mb_per_sec=15.0, fallback="Several minutes")),
            ("Encrypted", "Yes" if password_arg else "No"),
        ],
        warning="Current data on the device can be replaced during restore.",
    ):
        return

    print_info("Starting restore. Do not disconnect the device.")
    lines = run_streaming(
        "idevicebackup2",
        "-s", selected.name,
        "restore", "--system",
        *password_arg,
        backup_dir,
        udid=udid,
    )
    stream_output(lines, title="Restore Progress", task_message="Preparing restore...")
    pause()


def list_backups(udid: str) -> None:
    backup_dir = prompt_path("Backup folder to list", default=DEFAULT_BACKUP_DIR)
    backups = _list_local_backups(backup_dir)
    if not backups:
        print_info(f"No backups found in: {backup_dir}")
    else:
        import datetime
        table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        table.add_column("UDID",  style="cyan",  width=44)
        table.add_column("Date",  style="white", width=20)
        table.add_column("Size",  style="yellow", width=10)
        for p in backups:
            mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size_mb = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / (1024 * 1024)
            table.add_row(p.name, mtime, f"{size_mb:.0f} MB")
        console.print(table)
    pause()


def backup_menu(info: DeviceInfo) -> None:
    while True:
        print_section("Backup & Restore")
        console.print("  [1] Create Backup")
        console.print("  [2] Restore Backup")
        console.print("  [3] List Local Backups")
        console.print("  [B] Back")
        console.print()

        choice = prompt_choice(["1", "2", "3", "B"])
        if choice == "1":
            create_backup(info)
        elif choice == "2":
            restore_backup(info)
        elif choice == "3":
            list_backups(info.udid)
        elif choice == "B":
            break
