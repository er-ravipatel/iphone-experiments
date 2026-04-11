"""
Progress display helpers for long-running operations.
"""
from contextlib import contextmanager
import re
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    TaskProgressColumn,
)

console = Console()
PERCENT_RE = re.compile(r"(\d{1,3})%")


@contextmanager
def spinner(message: str):
    """Context manager that shows a spinner while the block runs."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}[/cyan]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(message)
        yield progress


@contextmanager
def progress_bar(message: str, total: int = 100):
    """Context manager exposing a progress bar. Yields the task id and progress object."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}[/cyan]"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(message, total=total)
        yield progress, task


def _style_stream_line(line: str) -> str:
    lower = line.lower()
    if lower.startswith(("error", "failed")):
        return f"[red]{line}[/red]"
    if lower.startswith(("done", "success", "completed")):
        return f"[green]{line}[/green]"
    if "%" in line:
        return f"[cyan]{line}[/cyan]"
    return f"[dim]{line}[/dim]"


def stream_output(lines, title: str = "", task_message: str = "Working...") -> None:
    """
    Show live progress for streaming CLI output.
    Percentage lines update a progress bar; all other lines update the status text.
    """
    if title:
        console.rule(f"[cyan]{title}[/cyan]")

    status = task_message
    recent_lines: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}[/cyan]"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        expand=True,
        transient=True,
    ) as progress:
        task = progress.add_task(status, total=100, completed=0)

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            match = PERCENT_RE.search(line)
            if match:
                percent = max(0, min(100, int(match.group(1))))
                status = line
                progress.update(task, completed=percent, description=status)
            else:
                status = line
                progress.update(task, description=status)

            recent_lines.append(_style_stream_line(line))
            recent_lines = recent_lines[-6:]

        progress.update(task, completed=100, description=status or task_message)

    if recent_lines:
        console.print("[bold cyan]Latest output[/bold cyan]")
        for line in recent_lines:
            console.print(f"  {line}")
