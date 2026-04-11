"""
Subprocess wrapper for libimobiledevice CLI tools.
All tool calls go through here so error handling is consistent.
"""
import subprocess
from dataclasses import dataclass
from typing import Optional

from .platform import find_tool


@dataclass
class RunResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int


def run(tool: str, *args: str, timeout: int = 30, udid: str | None = None) -> RunResult:
    """
    Run a libimobiledevice CLI tool with the given arguments.
    Automatically prepends -u <udid> when udid is provided.
    """
    binary = find_tool(tool)
    if not binary:
        return RunResult(
            success=False,
            stdout="",
            stderr=f"Tool '{tool}' not found. Is libimobiledevice installed?",
            returncode=-1,
        )

    cmd = [binary]
    if udid:
        cmd += ["-u", udid]
    cmd += list(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return RunResult(
            success=result.returncode == 0,
            stdout=result.stdout.strip(),
            stderr=result.stderr.strip(),
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            success=False,
            stdout="",
            stderr=f"Tool '{tool}' timed out after {timeout}s",
            returncode=-2,
        )
    except Exception as e:
        return RunResult(
            success=False,
            stdout="",
            stderr=str(e),
            returncode=-3,
        )


def run_streaming(tool: str, *args: str, udid: str | None = None):
    """
    Run a tool and yield lines of stdout in real time.
    Useful for backup/restore progress.
    """
    binary = find_tool(tool)
    if not binary:
        yield f"[ERROR] Tool '{tool}' not found."
        return

    cmd = [binary]
    if udid:
        cmd += ["-u", udid]
    cmd += list(args)

    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        for line in proc.stdout:
            yield line.rstrip()
