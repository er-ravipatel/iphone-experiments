"""
Background QThread workers for media operations.
All workers are safe to use from the main thread — they emit signals only.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage, QPixmap

log = logging.getLogger(__name__)

from ....terminal.features.media import (
    _listdir, _download_one, _collect_all_media,
    VIDEO_EXTENSIONS,
)

# ── Image helpers (worker-thread safe, never call from main thread) ────────────

def _make_thumb_jpeg(data: bytes, ext: str) -> bytes:
    """Decode image bytes, scale to THUMB_SIZE, return JPEG bytes."""
    try:
        import io
        from PIL import Image
        if ext in (".heic", ".heif"):
            import pillow_heif
            pillow_heif.register_heif_opener()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((155, 155), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        log.exception("_make_thumb_jpeg failed for ext=%s", ext)
        return b""


def _thumb_jpeg_from_local(local: str) -> bytes:
    """Read a cached local file and return a scaled thumbnail JPEG."""
    try:
        ext = Path(local).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            return _try_video_frame(local)
        data = Path(local).read_bytes()
        return _make_thumb_jpeg(data, ext)
    except Exception:
        log.exception("_thumb_jpeg_from_local failed for %s", local)
        return b""


def _try_video_frame(local_path: str) -> bytes:
    """Extract a representative frame from a video as JPEG bytes via OpenCV."""
    try:
        import cv2
        cap = cv2.VideoCapture(local_path)
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if total > 10:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * 0.1))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            log.warning("_try_video_frame: no frame read from %s", local_path)
            return b""
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return bytes(buf) if ret else b""
    except Exception:
        log.exception("_try_video_frame failed for %s", local_path)
        return b""


# ── Workers ────────────────────────────────────────────────────────────────────

class ListDirWorker(QThread):
    finished = Signal(list)
    failed   = Signal(str)

    def __init__(self, udid: str, path: str) -> None:
        super().__init__()
        self._udid = udid
        self._path = path

    def run(self) -> None:
        log.debug("ListDirWorker: listing %s", self._path)
        try:
            entries = asyncio.run(_listdir(self._udid, self._path))
            log.debug("ListDirWorker: got %d entries for %s", len(entries), self._path)
            self.finished.emit(entries)
        except Exception as exc:
            log.exception("ListDirWorker failed for %s", self._path)
            self.failed.emit(str(exc))


class ThumbnailWorker(QThread):
    """
    Streams thumbnail JPEG bytes to the main thread one item at a time.
    Visible rows are loaded first; the rest trickle in the background.
    Call add_priority_rows() from the main thread as the user scrolls.
    """
    thumbnail_ready = Signal(int, bytes)   # (row, jpeg_bytes)

    def __init__(self, udid: str, files: list[dict], cache: Path,
                 visible_rows: set[int]) -> None:
        super().__init__()
        self._udid     = udid
        self._files    = files
        self._cache    = cache
        self._stop     = False
        self._lock     = threading.Lock()
        self._priority: set[int] = set(visible_rows)

    def cancel(self) -> None:
        self._stop = True

    def add_priority_rows(self, rows: set[int]) -> None:
        with self._lock:
            self._priority.update(rows)

    def run(self) -> None:
        log.debug("ThumbnailWorker: starting for %d files", len(self._files))
        try:
            asyncio.run(self._async_run())
        except Exception:
            log.exception("ThumbnailWorker: unexpected error in run()")
        log.debug("ThumbnailWorker: finished")

    async def _async_run(self) -> None:
        from pymobiledevice3.lockdown import create_using_usbmux
        from pymobiledevice3.services.afc import AfcService

        lockdown = await create_using_usbmux(serial=self._udid)
        async with AfcService(lockdown) as afc:
            all_indices = set(range(len(self._files)))
            done: set[int] = set()
            while not self._stop and done != all_indices:
                with self._lock:
                    priority = self._priority - done
                    self._priority.clear()

                if priority:
                    for i in sorted(priority):
                        if self._stop:
                            return
                        await self._fetch_one(afc, i)
                        done.add(i)
                else:
                    remaining = all_indices - done
                    if not remaining:
                        break
                    i = min(remaining)
                    await self._fetch_one(afc, i)
                    done.add(i)
                    await asyncio.sleep(0.05)

    async def _fetch_one(self, afc, i: int) -> None:
        f   = self._files[i]
        ext = Path(f["name"]).suffix.lower()

        if ext in VIDEO_EXTENSIONS:
            thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
            self.thumbnail_ready.emit(i, thumb_path.read_bytes() if thumb_path.exists() else b"")
            return

        thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
        if thumb_path.exists():
            self.thumbnail_ready.emit(i, thumb_path.read_bytes())
            return

        full_path = self._cache / f["name"]
        if not full_path.exists():
            try:
                data = await afc.get_file_contents(f["path"])
                full_path.write_bytes(data)
            except Exception:
                log.exception("ThumbnailWorker: failed downloading %s", f["path"])
                self.thumbnail_ready.emit(i, b"")
                return
        else:
            data = full_path.read_bytes()

        jpeg = _make_thumb_jpeg(data, ext)
        if jpeg:
            thumb_path.write_bytes(jpeg)
        self.thumbnail_ready.emit(i, jpeg)


class PhotoDecodeWorker(QThread):
    """Decodes a HEIC/non-renderable photo via Pillow and emits a scaled QPixmap."""
    ready = Signal(QPixmap)

    def __init__(self, path: str, ext: str, panel_w: int = 300) -> None:
        super().__init__()
        self._path = path
        self._ext  = ext
        self._pw   = panel_w

    def run(self) -> None:
        import io
        log.debug("PhotoDecodeWorker: decoding %s (ext=%s)", self._path, self._ext)
        px = QPixmap()
        try:
            from PIL import Image as PilImage
            if self._ext in {'.heic', '.heif'}:
                import pillow_heif
                pillow_heif.register_heif_opener()
            with PilImage.open(self._path) as im:
                copy = im.copy()
                if copy.mode not in ('RGB', 'RGBA'):
                    copy = copy.convert('RGB')
                copy.thumbnail((self._pw, self._pw))
                buf = io.BytesIO()
                copy.save(buf, format='JPEG', quality=88)
                img = QImage.fromData(buf.getvalue())
                if not img.isNull():
                    px = QPixmap.fromImage(img)
                    log.debug("PhotoDecodeWorker: decoded OK %s", self._path)
                else:
                    log.warning("PhotoDecodeWorker: QImage was null for %s", self._path)
        except Exception:
            log.exception("PhotoDecodeWorker: failed to decode %s", self._path)
        self.ready.emit(px)


class DownloadOpenWorker(QThread):
    """Downloads one file to the cache dir then signals the local path."""
    ready  = Signal(str)
    failed = Signal(str)

    def __init__(self, udid: str, remote: str, local: str) -> None:
        super().__init__()
        self._udid   = udid
        self._remote = remote
        self._local  = local

    def run(self) -> None:
        log.debug("DownloadOpenWorker: downloading %s → %s", self._remote, self._local)
        try:
            if not Path(self._local).exists():
                asyncio.run(_download_one(self._udid, self._remote, self._local))
            log.debug("DownloadOpenWorker: done %s", self._local)
            self.ready.emit(self._local)
        except Exception as exc:
            log.exception("DownloadOpenWorker: failed %s", self._remote)
            self.failed.emit(str(exc))


class ExportWorker(QThread):
    progress = Signal(int, int)   # done, total
    finished = Signal(int, int)   # count, bytes
    failed   = Signal(str)

    def __init__(self, udid: str, files: list[dict], dest_dir: str) -> None:
        super().__init__()
        self._udid  = udid
        self._files = files
        self._dest  = dest_dir
        self._stop  = False

    def cancel(self) -> None:
        self._stop = True

    def run(self) -> None:
        log.debug("ExportWorker: exporting %d files to %s", len(self._files), self._dest)
        try:
            dest = Path(self._dest)
            dest.mkdir(parents=True, exist_ok=True)
            total_bytes = 0
            for i, f in enumerate(self._files):
                if self._stop:
                    log.debug("ExportWorker: cancelled at %d/%d", i, len(self._files))
                    break
                local = dest / f["name"]
                if not local.exists():
                    size = asyncio.run(_download_one(self._udid, f["path"], str(local)))
                    total_bytes += size
                self.progress.emit(i + 1, len(self._files))
            log.debug("ExportWorker: done — %d files, %d bytes", len(self._files), total_bytes)
            self.finished.emit(len(self._files), total_bytes)
        except Exception as exc:
            log.exception("ExportWorker: failed")
            self.failed.emit(str(exc))


class ScanWorker(QThread):
    finished = Signal(list)
    failed   = Signal(str)

    def __init__(self, udid: str, root: str) -> None:
        super().__init__()
        self._udid = udid
        self._root = root
        self._stop = False

    def cancel(self) -> None:
        self._stop = True

    def run(self) -> None:
        log.debug("ScanWorker: scanning %s", self._root)
        try:
            result = asyncio.run(_collect_all_media(self._udid, self._root))
            if not self._stop:
                log.debug("ScanWorker: found %d files under %s", len(result), self._root)
                self.finished.emit(result)
        except Exception as exc:
            log.exception("ScanWorker: failed scanning %s", self._root)
            if not self._stop:
                self.failed.emit(str(exc))
