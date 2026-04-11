"""
Rename the connected device using idevicename.
"""
from ...utils.runner import run
from ..ui.menu import console, print_success, print_error, prompt_path, confirm_action, pause


def rename_device(udid: str, current_name: str) -> None:
    console.print(f"Current name: [bold cyan]{current_name}[/bold cyan]")
    new_name = prompt_path("New device name", default=current_name)
    if not new_name or new_name == current_name:
        return
    if not confirm_action(
        "Rename Device",
        [
            ("Current Name", current_name),
            ("New Name", new_name),
            ("Estimated Time", "About 2-10 sec"),
        ],
    ):
        return
    result = run("idevicename", "-n", new_name, udid=udid)
    if result.success:
        print_success(f"Device renamed to: {new_name}")
    else:
        print_error(f"Rename failed: {result.stderr}")
    pause()
