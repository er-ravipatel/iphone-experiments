"""
Background QThread workers for the Files page.

All workers accept an optional `bundle_id` parameter:
  - bundle_id=None  → use AfcService  (standard Media folder access)
  - bundle_id="..."  → use HouseArrestService  (per-app Documents access)

HouseArrestService inherits AfcService so all file operations are identical;
only the service construction differs.

Extra worker:
  ListAppsWorker — lists User apps that expose their Documents folder via
  UIFileSharingEnabled or UISupportsDocumentBrowser, used for the virtual
  root "On My iPhone" listing.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)


# ── Service factory ────────────────────────────────────────────────────────────

async def _get_afc(lockdown, bundle_id: str | None):
    """
    Return an AfcService (or HouseArrestService) context manager.
    Use as:  async with _get_afc(lockdown, bundle_id) as afc: ...
    """
    if bundle_id:
        from pymobiledevice3.services.house_arrest import HouseArrestService
        return await HouseArrestService.create(lockdown, bundle_id=bundle_id)
    from pymobiledevice3.services.afc import AfcService
    return AfcService(lockdown)


# ── Async helpers ──────────────────────────────────────────────────────────────

async def _async_listdir(udid: str, path: str,
                         bundle_id: str | None = None) -> list[dict]:
    from pymobiledevice3.lockdown import create_using_usbmux

    lockdown = await create_using_usbmux(serial=udid)
    async with await _get_afc(lockdown, bundle_id) as afc:
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
            entries.append({"name": name, "path": full,
                            "is_dir": is_dir, "size": size})
        return entries


async def _async_download(udid: str, remote: str, local: str,
                          bundle_id: str | None = None) -> int:
    from pymobiledevice3.lockdown import create_using_usbmux

    lockdown = await create_using_usbmux(serial=udid)
    async with await _get_afc(lockdown, bundle_id) as afc:
        data = await afc.get_file_contents(remote)
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(data)
        return len(data)


async def _async_upload(udid: str, local: str, remote: str,
                        bundle_id: str | None = None) -> int:
    from pymobiledevice3.lockdown import create_using_usbmux

    data = Path(local).read_bytes()
    lockdown = await create_using_usbmux(serial=udid)
    async with await _get_afc(lockdown, bundle_id) as afc:
        await afc.set_file_contents(remote, data)
        return len(data)


async def _async_delete(udid: str, remote: str,
                        bundle_id: str | None = None) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux

    lockdown = await create_using_usbmux(serial=udid)
    async with await _get_afc(lockdown, bundle_id) as afc:
        await afc.rm(remote, recursive=True)


async def _async_rename(udid: str, src: str, dst: str,
                        bundle_id: str | None = None) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux

    lockdown = await create_using_usbmux(serial=udid)
    async with await _get_afc(lockdown, bundle_id) as afc:
        await afc.rename(src, dst)


async def _async_mkdir(udid: str, path: str,
                       bundle_id: str | None = None) -> None:
    from pymobiledevice3.lockdown import create_using_usbmux

    lockdown = await create_using_usbmux(serial=udid)
    async with await _get_afc(lockdown, bundle_id) as afc:
        await afc.makedirs(path)


async def _async_list_apps(udid: str) -> list[dict]:
    """
    Return the virtual-root entry list:
      [{"name": "📁 Media", ...media_sentinel...},
       {"name": "AppName", "_bundle_id": "...", "_is_app_entry": True, ...}, ...]

    Apps are filtered to those with UIFileSharingEnabled or
    UISupportsDocumentBrowser so only genuinely accessible ones appear.
    """
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.installation_proxy import InstallationProxyService

    lockdown = await create_using_usbmux(serial=udid)
    async with InstallationProxyService(lockdown) as svc:
        apps = await svc.get_apps(application_type="User")

    entries: list[dict] = [
        # Sentinel that page.py recognises as "enter AFC domain"
        {
            "name": "📁  Media",
            "path": "/",
            "is_dir": True,
            "size": 0,
            "_is_media_entry": True,
        }
    ]

    for bundle_id, info in sorted(apps.items(),
                                  key=lambda kv: kv[1].get("CFBundleDisplayName", "")):
        if not (info.get("UIFileSharingEnabled") or
                info.get("UISupportsDocumentBrowser")):
            continue
        display = info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle_id
        entries.append({
            "name": display,
            "path": "/",
            "is_dir": True,
            "size": 0,
            "_bundle_id": bundle_id,
            "_is_app_entry": True,
        })

    return entries


# ── Workers ────────────────────────────────────────────────────────────────────

class ListDirWorker(QThread):
    finished = Signal(list)   # list[dict]
    failed   = Signal(str)

    def __init__(self, udid: str, path: str,
                 bundle_id: str | None = None) -> None:
        super().__init__()
        self._udid      = udid
        self._path      = path
        self._bundle_id = bundle_id

    def run(self) -> None:
        domain = f"app:{self._bundle_id}" if self._bundle_id else "afc"
        log.debug("ListDirWorker [%s]: listing %s", domain, self._path)
        try:
            entries = asyncio.run(
                _async_listdir(self._udid, self._path, self._bundle_id)
            )
            log.debug("ListDirWorker: %d entries", len(entries))
            self.finished.emit(entries)
        except Exception as exc:
            log.exception("ListDirWorker: failed for %s", self._path)
            self.failed.emit(str(exc))


class ListAppsWorker(QThread):
    """Lists User apps that support file sharing — used for the virtual root."""
    finished = Signal(list)   # list[dict]
    failed   = Signal(str)

    def __init__(self, udid: str) -> None:
        super().__init__()
        self._udid = udid

    def run(self) -> None:
        log.debug("ListAppsWorker: listing file-sharing apps")
        try:
            entries = asyncio.run(_async_list_apps(self._udid))
            log.debug("ListAppsWorker: %d entries", len(entries))
            self.finished.emit(entries)
        except Exception as exc:
            log.exception("ListAppsWorker: failed")
            self.failed.emit(str(exc))


class DownloadWorker(QThread):
    finished = Signal(int)    # bytes written
    failed   = Signal(str)

    def __init__(self, udid: str, remote: str, local: str,
                 bundle_id: str | None = None) -> None:
        super().__init__()
        self._udid      = udid
        self._remote    = remote
        self._local     = local
        self._bundle_id = bundle_id

    def run(self) -> None:
        log.debug("DownloadWorker: %s → %s", self._remote, self._local)
        try:
            n = asyncio.run(
                _async_download(self._udid, self._remote, self._local, self._bundle_id)
            )
            log.debug("DownloadWorker: wrote %d bytes", n)
            self.finished.emit(n)
        except Exception as exc:
            log.exception("DownloadWorker: failed for %s", self._remote)
            self.failed.emit(str(exc))


class UploadWorker(QThread):
    finished = Signal(int)    # bytes written
    failed   = Signal(str)

    def __init__(self, udid: str, local: str, remote: str,
                 bundle_id: str | None = None) -> None:
        super().__init__()
        self._udid      = udid
        self._local     = local
        self._remote    = remote
        self._bundle_id = bundle_id

    def run(self) -> None:
        log.debug("UploadWorker: %s → %s", self._local, self._remote)
        try:
            n = asyncio.run(
                _async_upload(self._udid, self._local, self._remote, self._bundle_id)
            )
            log.debug("UploadWorker: wrote %d bytes", n)
            self.finished.emit(n)
        except Exception as exc:
            log.exception("UploadWorker: failed for %s", self._local)
            self.failed.emit(str(exc))


class DeleteWorker(QThread):
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, udid: str, remote: str,
                 bundle_id: str | None = None) -> None:
        super().__init__()
        self._udid      = udid
        self._remote    = remote
        self._bundle_id = bundle_id

    def run(self) -> None:
        log.debug("DeleteWorker: deleting %s", self._remote)
        try:
            asyncio.run(_async_delete(self._udid, self._remote, self._bundle_id))
            log.debug("DeleteWorker: deleted %s", self._remote)
            self.finished.emit()
        except Exception as exc:
            log.exception("DeleteWorker: failed for %s", self._remote)
            self.failed.emit(str(exc))


class RenameWorker(QThread):
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, udid: str, src: str, dst: str,
                 bundle_id: str | None = None) -> None:
        super().__init__()
        self._udid      = udid
        self._src       = src
        self._dst       = dst
        self._bundle_id = bundle_id

    def run(self) -> None:
        log.debug("RenameWorker: %s → %s", self._src, self._dst)
        try:
            asyncio.run(_async_rename(self._udid, self._src, self._dst, self._bundle_id))
            log.debug("RenameWorker: done")
            self.finished.emit()
        except Exception as exc:
            log.exception("RenameWorker: failed %s → %s", self._src, self._dst)
            self.failed.emit(str(exc))


class MkdirWorker(QThread):
    finished = Signal()
    failed   = Signal(str)

    def __init__(self, udid: str, path: str,
                 bundle_id: str | None = None) -> None:
        super().__init__()
        self._udid      = udid
        self._path      = path
        self._bundle_id = bundle_id

    def run(self) -> None:
        log.debug("MkdirWorker: creating %s", self._path)
        try:
            asyncio.run(_async_mkdir(self._udid, self._path, self._bundle_id))
            log.debug("MkdirWorker: created %s", self._path)
            self.finished.emit()
        except Exception as exc:
            log.exception("MkdirWorker: failed for %s", self._path)
            self.failed.emit(str(exc))
