"""
Background QThread workers for the Backup & Restore page.

BackupWorker and RestoreWorker own their subprocess.Popen directly
so cancel() can call proc.terminate() — run_streaming() does not
expose the process handle.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)

# Local replicas of terminal/features/backup.py helpers.
# We do NOT import that module to avoid pulling in Rich + terminal UI at load time.
_DEFAULT_BACKUP_DIR = str(Path.home() / "iphone_backups")
_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)%")


def _list_local_backups(backup_dir: str) -> list[Path]:
    """Return backup subdirectories sorted newest-first."""
    d = Path(backup_dir)
    if not d.exists():
        return []
    return sorted(
        [p for p in d.iterdir() if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _dir_size_bytes(path: Path) -> int:
    """Recursive total size of all files under *path*."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# ── Workers ────────────────────────────────────────────────────────────────────

class ListBackupsWorker(QThread):
    """Scans the local backup directory — no device connection required."""
    finished = Signal(list)   # list[Path]
    failed   = Signal(str)

    def __init__(self, backup_dir: str) -> None:
        super().__init__()
        self._backup_dir = backup_dir

    def run(self) -> None:
        log.debug("ListBackupsWorker: scanning %s", self._backup_dir)
        try:
            paths = _list_local_backups(self._backup_dir)
            log.debug("ListBackupsWorker: found %d backups", len(paths))
            self.finished.emit(paths)
        except Exception as exc:
            log.exception("ListBackupsWorker: failed")
            self.failed.emit(str(exc))


class DeleteBackupWorker(QThread):
    """Deletes a backup directory from the local filesystem."""
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, backup_path: Path) -> None:
        super().__init__()
        self._path = backup_path

    def run(self) -> None:
        log.debug("DeleteBackupWorker: deleting %s", self._path)
        try:
            shutil.rmtree(self._path)
            log.debug("DeleteBackupWorker: done")
            self.finished.emit()
        except Exception as exc:
            log.exception("DeleteBackupWorker: failed")
            self.failed.emit(str(exc))


class BackupWorker(QThread):
    """
    Runs `idevicebackup2 backup --full <dir>` and streams output.

    Owns the subprocess handle directly so cancel() can terminate it.
    """
    line_ready = Signal(str)   # one stdout line (rstripped)
    progress   = Signal(int)   # extracted percentage 0-100
    finished   = Signal()      # clean exit (returncode 0)
    failed     = Signal(str)   # non-zero exit or exception

    def __init__(self, udid: str, backup_dir: str) -> None:
        super().__init__()
        self._udid       = udid
        self._backup_dir = backup_dir
        self._cancelled  = False
        self._proc: subprocess.Popen | None = None

    def cancel(self) -> None:
        """Safe to call from the main thread at any time."""
        log.debug("BackupWorker: cancel requested")
        self._cancelled = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self) -> None:
        from ....utils.platform import find_tool
        log.debug("BackupWorker: starting for udid=%s", self._udid)

        binary = find_tool("idevicebackup2")
        if not binary:
            self.failed.emit("idevicebackup2 not found. Is libimobiledevice installed?")
            return

        Path(self._backup_dir).mkdir(parents=True, exist_ok=True)
        cmd = [binary, "-u", self._udid, "backup", "--full", self._backup_dir]
        log.debug("BackupWorker: cmd = %s", cmd)

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for raw in self._proc.stdout:
                line = raw.rstrip()
                self.line_ready.emit(line)
                m = _PERCENT_RE.search(line)
                if m:
                    self.progress.emit(int(float(m.group(1))))
            self._proc.wait()
            if self._cancelled:
                log.debug("BackupWorker: cancelled")
                self.failed.emit("Backup cancelled.")
            elif self._proc.returncode == 0:
                log.debug("BackupWorker: finished OK")
                self.finished.emit()
            else:
                log.warning("BackupWorker: exit code %d", self._proc.returncode)
                self.failed.emit(f"idevicebackup2 exited with code {self._proc.returncode}")
        except Exception as exc:
            log.exception("BackupWorker: exception")
            self.failed.emit(str(exc))
        finally:
            self._proc = None


class RestoreWorker(QThread):
    """
    Runs `idevicebackup2 restore --system -s <backup_udid> <backup_dir>`.

    Structurally identical to BackupWorker; owns subprocess for cancel support.
    """
    line_ready = Signal(str)
    progress   = Signal(int)
    finished   = Signal()
    failed     = Signal(str)

    def __init__(self, udid: str, backup_path: Path) -> None:
        super().__init__()
        self._udid        = udid
        self._backup_path = backup_path   # e.g. ~/iphone_backups/<some_udid>
        self._cancelled   = False
        self._proc: subprocess.Popen | None = None

    def cancel(self) -> None:
        log.debug("RestoreWorker: cancel requested")
        self._cancelled = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def run(self) -> None:
        from ....utils.platform import find_tool
        log.debug("RestoreWorker: restoring from %s to udid=%s",
                  self._backup_path, self._udid)

        binary = find_tool("idevicebackup2")
        if not binary:
            self.failed.emit("idevicebackup2 not found. Is libimobiledevice installed?")
            return

        backup_dir  = str(self._backup_path.parent)   # ~/iphone_backups
        backup_udid = self._backup_path.name           # the UDID subdir name

        cmd = [
            binary, "-u", self._udid,
            "-s", backup_udid,
            "restore", "--system",
            backup_dir,
        ]
        log.debug("RestoreWorker: cmd = %s", cmd)

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for raw in self._proc.stdout:
                line = raw.rstrip()
                self.line_ready.emit(line)
                m = _PERCENT_RE.search(line)
                if m:
                    self.progress.emit(int(float(m.group(1))))
            self._proc.wait()
            if self._cancelled:
                log.debug("RestoreWorker: cancelled")
                self.failed.emit("Restore cancelled.")
            elif self._proc.returncode == 0:
                log.debug("RestoreWorker: finished OK")
                self.finished.emit()
            else:
                log.warning("RestoreWorker: exit code %d", self._proc.returncode)
                self.failed.emit(f"idevicebackup2 exited with code {self._proc.returncode}")
        except Exception as exc:
            log.exception("RestoreWorker: exception")
            self.failed.emit(str(exc))
        finally:
            self._proc = None
