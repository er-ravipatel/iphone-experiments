"""
Background QThread workers for the Files page.
All workers emit signals only — safe to use from the main thread.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)


# ── Async helpers ──────────────────────────────────────────────────────────────

async def _async_listdir(udid: str, path: str) -> list[dict]:
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
            entries.append({"name": name, "path": full, "is_dir": is_dir, "size": size})
        return entries


async def _async_download(udid: str, remote: str, local: str) -> int:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        data = await afc.get_file_contents(remote)
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(data)
        return len(data)


async def _async_upload(udid: str, local: str, remote: str) -> int:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    data = Path(local).read_bytes()
    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        await afc.set_file_contents(remote, data)
        return len(data)


async def _async_delete(udid: str, remote: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        await afc.rm(remote, recursive=True)


async def _async_rename(udid: str, src: str, dst: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        await afc.rename(src, dst)


async def _async_mkdir(udid: str, path: str) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService

    lockdown = await create_using_usbmux(serial=udid)
    async with AfcService(lockdown) as afc:
        await afc.makedirs(path)


# ── Workers ────────────────────────────────────────────────────────────────────

class ListDirWorker(QThread):
    finished = Signal(list)   # list[dict]
    failed   = Signal(str)

    def __init__(self, udid: str, path: str) -> None:
        super().__init__()
        self._udid = udid
        self._path = path

    def run(self) -> None:
        log.debug("ListDirWorker: listing %s", self._path)
        try:
            entries = asyncio.run(_async_listdir(self._udid, self._path))
            log.debug("ListDirWorker: %d entries in %s", len(entries), self._path)
            self.finished.emit(entries)
        except Exception as exc:
            log.exception("ListDirWorker: failed for %s", self._path)
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    finished = Signal(int)    # bytes written
    failed   = Signal(str)

    def __init__(self, udid: str, remote: str, local: str) -> None:
        super().__init__()
        self._udid   = udid
        self._remote = remote
        self._local  = local

    def run(self) -> None:
        log.debug("DownloadWorker: %s → %s", self._remote, self._local)
        try:
            n = asyncio.run(_async_download(self._udid, self._remote, self._local))
            log.debug("DownloadWorker: wrote %d bytes", n)
            self.finished.emit(n)
        except Exception as exc:
            log.exception("DownloadWorker: failed for %s", self._remote)
            self.failed.emit(str(exc))


class UploadWorker(QThread):
    finished = Signal(int)    # bytes written
    failed   = Signal(str)

    def __init__(self, udid: str, local: str, remote: str) -> None:
        super().__init__()
        self._udid   = udid
        self._local  = local
        self._remote = remote

    def run(self) -> None:
        log.debug("UploadWorker: %s → %s", self._local, self._remote)
        try:
            n = asyncio.run(_async_upload(self._udid, self._local, self._remote))
            log.debug("UploadWorker: wrote %d bytes", n)
            self.finished.emit(n)
        except Exception as exc:
            log.exception("UploadWorker: failed for %s", self._local)
            self.failed.emit(str(exc))


class DeleteWorker(QThread):
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, udid: str, remote: str) -> None:
        super().__init__()
        self._udid   = udid
        self._remote = remote

    def run(self) -> None:
        log.debug("DeleteWorker: deleting %s", self._remote)
        try:
            asyncio.run(_async_delete(self._udid, self._remote))
            log.debug("DeleteWorker: deleted %s", self._remote)
            self.finished.emit()
        except Exception as exc:
            log.exception("DeleteWorker: failed for %s", self._remote)
            self.failed.emit(str(exc))


class RenameWorker(QThread):
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, udid: str, src: str, dst: str) -> None:
        super().__init__()
        self._udid = udid
        self._src  = src
        self._dst  = dst

    def run(self) -> None:
        log.debug("RenameWorker: %s → %s", self._src, self._dst)
        try:
            asyncio.run(_async_rename(self._udid, self._src, self._dst))
            log.debug("RenameWorker: done")
            self.finished.emit()
        except Exception as exc:
            log.exception("RenameWorker: failed %s → %s", self._src, self._dst)
            self.failed.emit(str(exc))


class MkdirWorker(QThread):
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, udid: str, path: str) -> None:
        super().__init__()
        self._udid = udid
        self._path = path

    def run(self) -> None:
        log.debug("MkdirWorker: creating %s", self._path)
        try:
            asyncio.run(_async_mkdir(self._udid, self._path))
            log.debug("MkdirWorker: created %s", self._path)
            self.finished.emit()
        except Exception as exc:
            log.exception("MkdirWorker: failed for %s", self._path)
            self.failed.emit(str(exc))
