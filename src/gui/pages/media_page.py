"""
MediaPage — browse DCIM, preview photos & videos as thumbnails.
Double-click any file to open it with the system default app.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path, PurePosixPath

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QProgressBar, QSizePolicy, QStackedWidget, QSlider,
    QSplitter, QSplitterHandle, QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer, QUrl, QEvent
from PySide6.QtGui import QColor, QIcon, QPixmap, QImage, QPainter, QFont

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

from ...device.info import DeviceInfo
from ...terminal.features.media import (
    _listdir, _download_one, _collect_all_media,
    PHOTO_EXTENSIONS, VIDEO_EXTENSIONS,
)

# Extensions Qt can decode directly into QImage
_RENDERABLE = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

THUMB_SIZE  = 155   # icon canvas
ITEM_SIZE   = 162   # grid cell width (7px padding around thumb)
LABEL_CHARS = 14    # max chars shown under each thumbnail


class _GripSplitterHandle(QSplitterHandle):
    """Splitter handle that paints three dot-pairs as a grip affordance."""

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        dot_color = QColor("#5a5a5a")
        hover_color = QColor("#4fc3f7")
        # Detect hover via underMouse
        color = hover_color if self.underMouse() else dot_color
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        cx = self.width() // 2
        cy = self.height() // 2
        r = 2  # dot radius
        gap = 5  # vertical gap between dot centres
        for dy in (-gap, 0, gap):
            p.drawEllipse(cx - r, cy + dy - r, r * 2, r * 2)
        p.end()


class _GripSplitter(QSplitter):
    """QSplitter that uses _GripSplitterHandle for visual drag affordance."""

    def createHandle(self):  # noqa: N802
        return _GripSplitterHandle(self.orientation(), self)


# ── Utilities ──────────────────────────────────────────────────────────────────

def _cache_dir(udid: str) -> Path:
    base = Path(tempfile.gettempdir()) / "iphone_explorer" / udid[:8]
    base.mkdir(parents=True, exist_ok=True)
    return base


def _open_system(path: str) -> None:
    """Open a local file with the OS default application."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def _fmt_size(size: int) -> str:
    if not size:
        return ""
    if size >= 1_000_000_000:
        return f"{size / 1_000_000_000:.1f} GB"
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size / 1_000:.0f} KB"
    return f"{size} B"


def _make_placeholder(label: str, bg: str, fg: str) -> QIcon:
    px = QPixmap(THUMB_SIZE, THUMB_SIZE)
    px.fill(QColor(bg))
    p = QPainter(px)
    # Dim border
    p.setPen(QColor(fg).darker(120))
    p.drawRect(px.rect().adjusted(0, 0, -1, -1))
    # Label text
    p.setPen(QColor(fg))
    p.setFont(QFont("Segoe UI", 12, QFont.Bold))
    p.drawText(px.rect(), Qt.AlignCenter, label)
    p.end()
    return QIcon(px)


def _ext_placeholder(ext: str) -> QIcon:
    """Per-extension placeholder — shows the actual format (HEIC, MOV, etc.)."""
    ext_upper = ext.lstrip(".").upper() or "FILE"
    if ext_upper in ("HEIC", "HEIF"):
        return _make_placeholder(ext_upper, "#1c1a14", "#ffa726")
    if ext.lower() in VIDEO_EXTENSIONS:
        return _make_placeholder(ext_upper, "#14141f", "#4fc3f7")
    return _make_placeholder(ext_upper, "#1a1a1a", "#9e9e9e")


def _make_thumb_jpeg(data: bytes, ext: str) -> bytes:
    """
    Decode image bytes in a worker thread, scale to THUMB_SIZE, return JPEG bytes.
    Uses Pillow for all formats (HEIC/HEIF via pillow-heif, JPEG/PNG natively).
    Returns empty bytes on failure.
    Called exclusively from worker threads — never the main thread.
    """
    try:
        import io
        from PIL import Image
        if ext in (".heic", ".heif"):
            import pillow_heif
            pillow_heif.register_heif_opener()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception:
        return b""


def _thumb_jpeg_from_local(local: str) -> bytes:
    """Read a cached local file and return a scaled thumbnail JPEG. Worker-thread safe."""
    try:
        ext = Path(local).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            return _try_video_frame(local)   # already returns JPEG bytes
        data = Path(local).read_bytes()
        return _make_thumb_jpeg(data, ext)
    except Exception:
        return b""


def _try_video_frame(local_path: str) -> bytes:
    """
    Extract a representative frame from a video as JPEG bytes using OpenCV.
    Seeks to 10% into the video for a more useful frame than frame 0.
    Returns empty bytes if OpenCV is unavailable or extraction fails.
    """
    try:
        import cv2
        cap = cv2.VideoCapture(local_path)
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if total > 10:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * 0.1))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return b""
        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return bytes(buf) if ret else b""
    except Exception:
        return b""


# ── Workers ────────────────────────────────────────────────────────────────────

class _ListDirWorker(QThread):
    finished = Signal(list)
    failed   = Signal(str)

    def __init__(self, udid: str, path: str) -> None:
        super().__init__()
        self._udid = udid
        self._path = path

    def run(self) -> None:
        try:
            self.finished.emit(asyncio.run(_listdir(self._udid, self._path)))
        except Exception as exc:
            self.failed.emit(str(exc))


class _ThumbnailWorker(QThread):
    """
    Streams raw image bytes back to the main thread one file at a time.
    Visible rows (visible_rows) are loaded first with no delay; the rest
    trickle in the background (~25/sec) so the UI stays responsive.
    Call add_priority_rows() from the main thread as the user scrolls.
    """
    thumbnail_ready = Signal(int, bytes)   # (row, raw_bytes)

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
        """Main-thread call: reprioritize newly visible rows."""
        with self._lock:
            self._priority.update(rows)

    def run(self) -> None:
        asyncio.run(self._async_run())

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
                    # Visible items — one by one so each thumbnail pops in immediately
                    for i in sorted(priority):
                        if self._stop:
                            return
                        await self._fetch_one(afc, i)
                        done.add(i)
                else:
                    # Background items — sequential with small pause
                    remaining = all_indices - done
                    if not remaining:
                        break
                    i = min(remaining)
                    await self._fetch_one(afc, i)
                    done.add(i)
                    await asyncio.sleep(0.05)   # ~20/sec, keeps USB calm

    async def _fetch_one(self, afc, i: int) -> None:
        """
        Download file if needed, then decode + scale to thumbnail in this worker
        thread so the main thread only does a trivial QImage.fromData() call.
        """
        f = self._files[i]
        ext = Path(f["name"]).suffix.lower()

        if ext in VIDEO_EXTENSIONS:
            # Emit cached thumbnail if already generated (from a prior preview download)
            thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
            self.thumbnail_ready.emit(i, thumb_path.read_bytes() if thumb_path.exists() else b"")
            return

        # Thumbnail cache: small pre-scaled JPEG so repeated visits are instant
        thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
        if thumb_path.exists():
            self.thumbnail_ready.emit(i, thumb_path.read_bytes())
            return

        # Download full file if not already cached
        full_path = self._cache / f["name"]
        if not full_path.exists():
            try:
                data = await afc.get_file_contents(f["path"])
                full_path.write_bytes(data)
            except Exception:
                self.thumbnail_ready.emit(i, b"")
                return
        else:
            data = full_path.read_bytes()

        # Decode + scale in worker thread (CPU-heavy, must NOT run on main thread)
        jpeg = _make_thumb_jpeg(data, ext)
        if jpeg:
            thumb_path.write_bytes(jpeg)
        self.thumbnail_ready.emit(i, jpeg)


class _PhotoPopout(QWidget):
    """Floating full-resolution photo viewer window."""

    def __init__(self, local_path: str, ext: str, title: str) -> None:
        super().__init__(None, Qt.Window)
        self.setWindowTitle(f"Preview — {title}")
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(960, 720)
        self._worker: _PhotoDecodeWorker | None = None

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        # Toolbar
        bar = QHBoxLayout()
        self._fit_btn = QPushButton("Fit to Window")
        self._fit_btn.setCheckable(True)
        self._fit_btn.setChecked(True)
        self._fit_btn.clicked.connect(self._toggle_fit)
        bar.addWidget(self._fit_btn)
        bar.addStretch()
        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color: #616161; font-size: 11px;")
        bar.addWidget(self._info_lbl)
        vbox.addLayout(bar)

        # Scroll area + image label
        self._scroll = QScrollArea()
        self._scroll.setAlignment(Qt.AlignCenter)
        self._scroll.setStyleSheet("QScrollArea { background: #0d0d0d; border: none; }")
        self._img_lbl = QLabel("Loading…")
        self._img_lbl.setAlignment(Qt.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent; color: #555;")
        self._scroll.setWidget(self._img_lbl)
        self._scroll.setWidgetResizable(True)
        vbox.addWidget(self._scroll, stretch=1)

        self._local_path = local_path
        self._ext = ext
        self._full_pixmap = QPixmap()
        self._fit_mode = True

        self._load()
        self.show()

    def _load(self) -> None:
        if self._ext in _RENDERABLE:
            img = QImage(self._local_path)
            if not img.isNull():
                self._full_pixmap = QPixmap.fromImage(img)
                self._apply_pixmap()
            else:
                self._img_lbl.setText("Cannot render image")
        else:
            self._worker = _PhotoDecodeWorker(self._local_path, self._ext, 8000)
            self._worker.ready.connect(self._on_decoded)
            self._worker.start()

    def _on_decoded(self, px: QPixmap) -> None:
        self._full_pixmap = px
        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        if self._full_pixmap.isNull():
            self._img_lbl.setText("Cannot render image")
            return
        w, h = self._full_pixmap.width(), self._full_pixmap.height()
        self._info_lbl.setText(f"{w} × {h} px")
        self._render()

    def _render(self) -> None:
        if self._full_pixmap.isNull():
            return
        if self._fit_mode:
            avail = self._scroll.viewport().size()
            px = self._full_pixmap.scaled(avail, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            px = self._full_pixmap
        self._img_lbl.setPixmap(px)

    def _toggle_fit(self, checked: bool) -> None:
        self._fit_mode = checked
        self._fit_btn.setText("Fit to Window" if checked else "Full Size")
        self._scroll.setWidgetResizable(checked)
        self._render()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_mode:
            self._render()


class _PhotoDecodeWorker(QThread):
    """Decodes a HEIC/non-renderable photo via Pillow and emits a scaled QPixmap."""
    ready = Signal(QPixmap)

    def __init__(self, path: str, ext: str, panel_w: int = 300) -> None:
        super().__init__()
        self._path = path
        self._ext  = ext
        self._pw   = panel_w

    def run(self) -> None:
        import io
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
        except Exception:
            pass
        self.ready.emit(px)


class _DownloadOpenWorker(QThread):
    """Downloads one file to the cache dir then signals the local path."""
    ready  = Signal(str)
    failed = Signal(str)

    def __init__(self, udid: str, remote: str, local: str) -> None:
        super().__init__()
        self._udid   = udid
        self._remote = remote
        self._local  = local

    def run(self) -> None:
        try:
            if not Path(self._local).exists():
                asyncio.run(_download_one(self._udid, self._remote, self._local))
            self.ready.emit(self._local)
        except Exception as exc:
            self.failed.emit(str(exc))


class _ExportWorker(QThread):
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
        try:
            dest = Path(self._dest)
            dest.mkdir(parents=True, exist_ok=True)
            total_bytes = 0
            for i, f in enumerate(self._files):
                if self._stop:
                    break
                local = dest / f["name"]
                if not local.exists():
                    size = asyncio.run(_download_one(self._udid, f["path"], str(local)))
                    total_bytes += size
                self.progress.emit(i + 1, len(self._files))
            self.finished.emit(len(self._files), total_bytes)
        except Exception as exc:
            self.failed.emit(str(exc))


class _ScanWorker(QThread):
    finished = Signal(list)
    failed   = Signal(str)

    def __init__(self, udid: str, root: str) -> None:
        super().__init__()
        self._udid   = udid
        self._root   = root
        self._stop   = False

    def cancel(self) -> None:
        self._stop = True   # result is discarded by MediaPage if stop is set

    def run(self) -> None:
        try:
            result = asyncio.run(_collect_all_media(self._udid, self._root))
            if not self._stop:
                self.finished.emit(result)
        except Exception as exc:
            if not self._stop:
                self.failed.emit(str(exc))


# ── Page ───────────────────────────────────────────────────────────────────────

class MediaPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._current_path = "/DCIM"
        self._path_stack: list[str] = []
        self._media_files: list[dict] = []
        self._cache: Path | None = None

        self._list_worker:    _ListDirWorker       | None = None
        self._thumb_worker:   _ThumbnailWorker      | None = None
        self._open_worker:    _DownloadOpenWorker   | None = None
        self._export_worker:  _ExportWorker         | None = None
        self._scan_worker:    _ScanWorker           | None = None
        self._preview_worker: _DownloadOpenWorker   | None = None
        self._thumb_gen: int = 0
        # Holds references to all running workers so Python's GC never destroys
        # a QThread while its OS thread is still executing (→ crash).
        self._live_workers: set = set()
        self._preview_local: str | None = None   # path of currently previewed file
        self._preview_row:   int = -1

        self._build_ui()

        # Media player (video playback)
        if _HAS_MULTIMEDIA:
            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.setVideoOutput(self._video_widget)
            self._player.playbackStateChanged.connect(self._on_player_state)
            self._player.positionChanged.connect(self._on_video_pos)
            self._player.durationChanged.connect(self._on_video_dur)
        else:
            self._player = None

        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # Title row — title + export buttons + status label
        title_row = QHBoxLayout()
        title = QLabel("Photos & Videos")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addSpacing(16)

        self._summary_lbl = QLabel()
        self._summary_lbl.setObjectName("StatusLabel")
        title_row.addWidget(self._summary_lbl)
        title_row.addStretch()

        self._export_sel_btn = QPushButton("Export Selected")
        self._export_sel_btn.clicked.connect(self._on_export_selected)
        title_row.addWidget(self._export_sel_btn)

        self._export_all_btn = QPushButton("Export All")
        self._export_all_btn.clicked.connect(self._on_export_all)
        title_row.addWidget(self._export_all_btn)

        self._export_bulk_btn = QPushButton("Export All Subfolders")
        self._export_bulk_btn.setToolTip("Recursively export every media file under this folder")
        self._export_bulk_btn.clicked.connect(self._on_export_bulk)
        title_row.addWidget(self._export_bulk_btn)

        self._status = QLabel()
        self._status.setObjectName("StatusLabel")
        title_row.addSpacing(12)
        title_row.addWidget(self._status)
        outer.addLayout(title_row)

        self._breadcrumb = QLabel()
        self._breadcrumb.setObjectName("StatusLabel")
        outer.addWidget(self._breadcrumb)

        # Body: folder list (left) + grid (right)
        body = QHBoxLayout()
        body.setSpacing(12)

        # Left — folder list
        left = QWidget()
        left.setFixedWidth(200)
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(6)

        fldr_lbl = QLabel("FOLDERS")
        fldr_lbl.setObjectName("SectionLabel")
        left_vbox.addWidget(fldr_lbl)

        self._folder_list = QListWidget()
        self._folder_list.setObjectName("Card")
        self._folder_list.setStyleSheet("#Card { border-radius: 6px; padding: 4px; }")
        self._folder_list.itemClicked.connect(self._on_folder_clicked)
        self._folder_list.itemDoubleClicked.connect(self._on_folder_dbl)
        self._folder_list.currentItemChanged.connect(
            lambda current, _prev: self._on_folder_clicked(current) if current else None
        )
        left_vbox.addWidget(self._folder_list)

        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self._on_back)
        left_vbox.addWidget(self._back_btn)

        body.addWidget(left)

        # Right — grid + progress
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(6)

        self._grid_lbl = QLabel("MEDIA")
        self._grid_lbl.setObjectName("SectionLabel")
        right_vbox.addWidget(self._grid_lbl)

        # Thumbnail grid
        self._grid = QListWidget()
        self._grid.setViewMode(QListWidget.IconMode)
        self._grid.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
        self._grid.setGridSize(QSize(ITEM_SIZE, ITEM_SIZE + 28))
        self._grid.setSpacing(2)
        self._grid.setResizeMode(QListWidget.Adjust)
        self._grid.setUniformItemSizes(True)
        self._grid.setMovement(QListWidget.Static)
        self._grid.setSelectionMode(QListWidget.ExtendedSelection)
        self._grid.setStyleSheet(
            "QListWidget { background: #181818; border: 1px solid #272727; border-radius: 6px; }"
            "QListWidget::item { color: #9e9e9e; border-radius: 4px; }"
            "QListWidget::item:selected { background: #0d2233; color: #4fc3f7; }"
        )
        self._grid.itemClicked.connect(self._on_item_clicked)
        self._grid.itemDoubleClicked.connect(self._on_item_dbl)
        self._grid.itemSelectionChanged.connect(self._on_selection_changed)
        self._grid.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Arrow-key preview debounce: wait 1 s of inactivity before loading preview
        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.setInterval(400)
        self._preview_debounce.timeout.connect(self._on_preview_debounce_fire)
        self._grid.installEventFilter(self)
        right_vbox.addWidget(self._grid, stretch=1)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        right_vbox.addWidget(self._progress)

        # Grid panel can shrink freely — toolbar buttons are in the page header
        right.setMinimumWidth(0)
        self._grid.setMinimumWidth(0)

        # Inner splitter: grid (stretch) | preview (resizable, hidden by default)
        self._inner_splitter = _GripSplitter(Qt.Horizontal)
        self._inner_splitter.setChildrenCollapsible(False)
        self._inner_splitter.setHandleWidth(10)
        self._inner_splitter.setStyleSheet(
            "QSplitter::handle:horizontal {"
            "  background: #242424;"
            "  border-left: 1px solid #1a1a1a; border-right: 1px solid #1a1a1a;"
            "}"
            "QSplitter::handle:horizontal:hover { background: #1e3040; }"
        )
        self._inner_splitter.addWidget(right)
        self._preview_panel = self._build_preview_panel()
        self._preview_panel.setMinimumWidth(180)
        self._preview_panel_width = 340   # remembered width across hide/show
        self._preview_panel.setVisible(False)
        self._inner_splitter.addWidget(self._preview_panel)
        self._inner_splitter.setStretchFactor(0, 1)
        self._inner_splitter.setStretchFactor(1, 0)
        self._inner_splitter.setSizes([800, 0])
        self._inner_splitter.splitterMoved.connect(self._on_splitter_moved)

        body.addWidget(self._inner_splitter, stretch=1)
        outer.addLayout(body, stretch=1)

        self._result_lbl = QLabel()
        self._result_lbl.setObjectName("StatusLabel")
        self._result_lbl.setWordWrap(True)
        outer.addWidget(self._result_lbl)

    def _build_preview_panel(self) -> QWidget:
        panel = QWidget()
        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        # Header row: label
        hdr = QLabel("PREVIEW")
        hdr.setObjectName("SectionLabel")
        vbox.addWidget(hdr)

        # Stacked area: placeholder / photo / video
        self._preview_stack = QStackedWidget()
        self._preview_stack.setStyleSheet(
            "QStackedWidget { background: #111; border: 1px solid #272727; border-radius: 6px; }"
        )

        # 0 — placeholder
        ph = QLabel("Select a file\nto preview")
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet("color: #383838; font-size: 13px; background: transparent;")
        self._preview_stack.addWidget(ph)

        # 1 — video
        if _HAS_MULTIMEDIA:
            video_container = QWidget()
            video_container.setStyleSheet("background: transparent;")
            vc_vbox = QVBoxLayout(video_container)
            vc_vbox.setContentsMargins(0, 0, 0, 0)
            vc_vbox.setSpacing(4)

            self._video_widget = QVideoWidget()
            self._video_widget.setMinimumHeight(200)
            vc_vbox.addWidget(self._video_widget, stretch=1)

            # Controls row
            ctrl = QHBoxLayout()
            self._play_btn = QPushButton("▶")
            self._play_btn.setFixedWidth(36)
            self._play_btn.clicked.connect(self._on_play_pause)
            ctrl.addWidget(self._play_btn)

            self._stop_btn = QPushButton("■")
            self._stop_btn.setFixedWidth(36)
            self._stop_btn.clicked.connect(self._on_stop_video)
            ctrl.addWidget(self._stop_btn)

            self._seek_slider = QSlider(Qt.Horizontal)
            self._seek_slider.setRange(0, 0)
            self._seek_slider.sliderMoved.connect(self._on_seek)
            ctrl.addWidget(self._seek_slider, stretch=1)

            self._time_lbl = QLabel("0:00")
            self._time_lbl.setObjectName("StatusLabel")
            self._time_lbl.setFixedWidth(40)
            ctrl.addWidget(self._time_lbl)

            vc_vbox.addLayout(ctrl)
            self._preview_stack.addWidget(video_container)
        else:
            no_vid = QLabel("QtMultimedia\nnot available")
            no_vid.setAlignment(Qt.AlignCenter)
            no_vid.setStyleSheet("color: #555; font-size: 11px; background: transparent;")
            self._preview_stack.addWidget(no_vid)

        # 2 — photo
        photo_w = QWidget()
        photo_w.setStyleSheet("background: transparent;")
        photo_vbox = QVBoxLayout(photo_w)
        photo_vbox.setContentsMargins(4, 4, 4, 4)
        photo_vbox.setSpacing(6)
        self._photo_img_lbl = QLabel()
        self._photo_img_lbl.setAlignment(Qt.AlignCenter)
        self._photo_img_lbl.setMinimumHeight(160)
        self._photo_img_lbl.setStyleSheet("background: transparent;")
        photo_vbox.addWidget(self._photo_img_lbl, stretch=1)
        self._photo_meta_lbl = QLabel()
        self._photo_meta_lbl.setWordWrap(True)
        self._photo_meta_lbl.setTextFormat(Qt.RichText)
        self._photo_meta_lbl.setStyleSheet("color: #757575; font-size: 11px; background: transparent;")
        photo_vbox.addWidget(self._photo_meta_lbl)
        self._preview_stack.addWidget(photo_w)   # index 2

        vbox.addWidget(self._preview_stack, stretch=1)

        # File info / actions
        self._prev_name_lbl = QLabel()
        self._prev_name_lbl.setObjectName("StatusLabel")
        self._prev_name_lbl.setWordWrap(True)
        vbox.addWidget(self._prev_name_lbl)

        btn_row = QHBoxLayout()
        self._prev_open_btn = QPushButton("Open in System App")
        self._prev_open_btn.setEnabled(False)
        self._prev_open_btn.clicked.connect(self._on_preview_open_sys)
        btn_row.addWidget(self._prev_open_btn)

        self._popout_btn = QPushButton("⤢ Pop Out")
        self._popout_btn.setEnabled(False)
        self._popout_btn.setToolTip("Open in floating window")
        self._popout_btn.clicked.connect(self._pop_out_preview)
        btn_row.addWidget(self._popout_btn)

        vbox.addLayout(btn_row)

        return panel

    # ── Helpers ────────────────────────────────────────────────────────────

    def _set_result(self, text: str, color: str = "#9e9e9e") -> None:
        self._result_lbl.setText(text)
        self._result_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _set_export_btns(self, enabled: bool) -> None:
        has_sel = bool(self._grid.selectedItems())
        self._export_sel_btn.setEnabled(enabled and has_sel)
        self._export_all_btn.setEnabled(enabled and bool(self._media_files))
        self._export_bulk_btn.setEnabled(enabled)

    def _any_busy(self) -> bool:
        return any(
            w is not None and w.isRunning()
            for w in (self._list_worker, self._export_worker, self._scan_worker)
        )

    def _cancel_thumb_worker(self) -> None:
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.cancel()
            # Disconnect signal immediately so any in-flight emissions from the
            # old worker are silently dropped — no blocking wait on main thread.
            try:
                self._thumb_worker.thumbnail_ready.disconnect()
            except RuntimeError:
                pass
        self._thumb_worker = None

    def _update_breadcrumb(self) -> None:
        self._breadcrumb.setText(f"Location:  {self._current_path}")
        self._back_btn.setEnabled(self._current_path != "/DCIM")

    def _populate(self, entries: list[dict], update_folders: bool = True) -> None:
        folders = [e for e in entries if e["is_dir"]]
        media   = [e for e in entries if not e["is_dir"] and e.get("is_media")]
        self._media_files = media

        # Left folder panel — only updated on full navigation
        if update_folders:
            self._folder_list.clear()
            for f in folders:
                folder_item = QListWidgetItem(f["name"])
                folder_item.setForeground(QColor("#4fc3f7"))
                self._folder_list.addItem(folder_item)

        # Right grid — placeholder icons first (per file extension).
        # Disable updates while bulk-adding items to avoid a repaint per addItem().
        self._grid.setUpdatesEnabled(False)
        self._grid.clear()
        for f in media:
            ext = Path(f["name"]).suffix.lower()
            icon = _ext_placeholder(ext)
            stem = Path(f["name"]).stem
            label = stem if len(stem) <= LABEL_CHARS else stem[:LABEL_CHARS - 1] + "…"
            grid_item = QListWidgetItem(icon, label)
            grid_item.setToolTip(f"{f['name']}  {_fmt_size(f['size'])}")
            self._grid.addItem(grid_item)
        self._grid.setUpdatesEnabled(True)

        n = len(media)
        total_sz = sum(f["size"] for f in media)
        if n:
            self._summary_lbl.setText(
                f"{n} file{'s' if n != 1 else ''}   {_fmt_size(total_sz)}"
                "   — double-click to open"
            )
        else:
            self._summary_lbl.setText("No media files here — select a subfolder")

        self._set_export_btns(True)

        # Defer thumbnail loading so the grid has time to render its layout first.
        # The timer fires after ~150 ms; _start_thumb_loading then queries which
        # items are actually visible so the worker can prioritise them.
        if self._udid and self._cache and media:
            self._cancel_thumb_worker()
            self._thumb_gen += 1
            gen = self._thumb_gen
            QTimer.singleShot(150, lambda: self._start_thumb_loading(gen))

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_thumbnail_ready(self, index: int, data: bytes) -> None:
        if index >= self._grid.count() or not data:
            return
        item = self._grid.item(index)
        if item is None:
            return
        # Worker already decoded + scaled — this is a small JPEG, fast to load
        img = QImage.fromData(data)
        if not img.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(img)))

    # ── Viewport-aware thumbnail helpers ───────────────────────────────────

    def _get_visible_rows(self) -> set[int]:
        """Return indices of grid items currently visible in the viewport."""
        visible: set[int] = set()
        vr = self._grid.viewport().rect()
        for i in range(self._grid.count()):
            item = self._grid.item(i)
            if item and vr.intersects(self._grid.visualItemRect(item)):
                visible.add(i)
        return visible

    def _start_thumb_loading(self, gen: int) -> None:
        """
        Kicked off by QTimer.singleShot after _populate() so the grid has
        rendered and we can query which rows are actually on screen.
        If a newer populate has already run (gen mismatch) we bail out.
        """
        if gen != self._thumb_gen:
            return
        if not self._udid or not self._cache or not self._media_files:
            return
        visible = self._get_visible_rows()
        self._thumb_worker = _ThumbnailWorker(
            self._udid, self._media_files, self._cache, visible
        )
        self._thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._track(self._thumb_worker)
        self._thumb_worker.start()

    def _on_scroll(self, _value: int) -> None:
        """When the user scrolls, push newly visible rows to the front of the queue."""
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.add_priority_rows(self._get_visible_rows())

    # ── Preview panel ──────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        """Restart preview debounce timer when arrow keys are pressed in the grid."""
        if obj is self._grid and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                self._preview_debounce.start()   # restarts 1 s countdown
        return super().eventFilter(obj, event)

    def _on_preview_debounce_fire(self) -> None:
        """Called 1 s after the last arrow-key press — show preview for current item."""
        item = self._grid.currentItem()
        if item:
            self._on_item_clicked(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Single click — preview videos only (photos are ignored)."""
        if not self._udid or not self._cache:
            return
        row = self._grid.row(item)
        if row < 0 or row >= len(self._media_files):
            return
        f = self._media_files[row]
        ext = Path(f["name"]).suffix.lower()

        self._show_preview_panel()
        self._preview_row = row
        self._prev_name_lbl.setText(f["name"])
        self._prev_open_btn.setEnabled(False)
        self._popout_btn.setEnabled(False)

        local = str(self._cache / f["name"])

        if ext not in VIDEO_EXTENSIONS:
            if self._player:
                self._player.stop()
                self._player.setSource(QUrl())
            if Path(local).exists():
                self._preview_local = local
                self._prev_open_btn.setEnabled(True)
                self._popout_btn.setEnabled(True)
            self._show_photo_preview(row, f)
            return

        if Path(local).exists():
            self._preview_local = local
            self._prev_open_btn.setEnabled(True)
            self._popout_btn.setEnabled(True)
            self._show_video_preview(local, ext)
            thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
            if not thumb_path.exists():
                self._try_update_thumb(row, local)
        else:
            self._preview_stack.setCurrentIndex(0)
            self._set_result(f"Downloading {f['name']} for preview…")
            self._preview_worker = _DownloadOpenWorker(self._udid, f["path"], local)
            self._preview_worker.ready.connect(
                lambda p, r=row, e=ext: self._on_preview_ready(p, e, r)
            )
            self._preview_worker.failed.connect(
                lambda err: self._set_result(f"Download failed: {err}", "#ef5350")
            )
            self._track(self._preview_worker)
            self._preview_worker.start()

    def _on_preview_ready(self, local: str, ext: str, row: int) -> None:
        self._set_result("")
        self._preview_local = local
        self._prev_open_btn.setEnabled(True)
        self._popout_btn.setEnabled(True)
        if ext in VIDEO_EXTENSIONS:
            self._show_video_preview(local, ext)
            self._try_update_thumb(row, local)
        else:
            self._show_photo_preview(row, self._media_files[row])

    def _show_video_preview(self, local: str, ext: str) -> None:
        """Start video playback in the preview panel."""
        if not _HAS_MULTIMEDIA or not self._player:
            return
        self._player.stop()
        self._preview_stack.setCurrentIndex(1)
        self._play_btn.setText("▶")
        self._seek_slider.setValue(0)
        self._time_lbl.setText("0:00")
        self._player.setSource(QUrl.fromLocalFile(local))
        self._player.play()
        self._play_btn.setText("⏸")

    def _show_photo_preview(self, row: int, f: dict) -> None:
        """Show full-resolution photo in the preview panel. Downloads if not cached."""
        ext = Path(f["name"]).suffix.lower()
        thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
        full_path  = self._cache / f["name"]
        local      = str(full_path)

        self._preview_stack.setCurrentIndex(2)
        self._photo_img_lbl.setPixmap(QPixmap())

        size_str = _fmt_size(f.get("size", 0))
        self._photo_meta_lbl.setText(
            f"<b>{f['name']}</b><br>"
            f"<font color='#555'>Path:</font> {f['path']}<br>"
            f"<font color='#555'>Size:</font> {size_str}"
        )

        if full_path.exists():
            # Full file available — decode and show at full quality
            self._decode_and_show_photo(local, ext, f, size_str)
        else:
            # Not cached yet — show thumbnail as placeholder while downloading
            if thumb_path.exists():
                img = QImage(str(thumb_path))
                if not img.isNull():
                    pw = max(self._preview_panel.width() - 16, 280)
                    self._photo_img_lbl.setPixmap(
                        QPixmap.fromImage(img.scaled(pw, pw, Qt.KeepAspectRatio,
                                                     Qt.SmoothTransformation))
                    )
                self._photo_img_lbl.setText("Downloading full photo…")
            else:
                self._photo_img_lbl.setText("Downloading…")

            self._set_result(f"Downloading {f['name']}…")
            self._preview_worker = _DownloadOpenWorker(self._udid, f["path"], local)
            self._preview_worker.ready.connect(
                lambda p, r=row, e=ext: self._on_preview_ready(p, e, r)
            )
            self._preview_worker.failed.connect(
                lambda err: (self._set_result(f"Download failed: {err}", "#ef5350"),
                             self._photo_img_lbl.setText("Download failed"))
            )
            self._track(self._preview_worker)
            self._preview_worker.start()

    def _decode_and_show_photo(self, local: str, ext: str, f: dict, size_str: str) -> None:
        """Decode a downloaded photo and show it. Handles JPEG/PNG directly, HEIC via worker."""
        pw = max(self._preview_panel.width() - 16, 280)
        if ext in _RENDERABLE:
            img = QImage(local)
            if not img.isNull():
                self._photo_img_lbl.setText("")
                self._photo_img_lbl.setPixmap(
                    QPixmap.fromImage(img.scaled(pw, pw, Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation))
                )
            else:
                self._photo_img_lbl.setText("Cannot render preview")
            threading.Thread(
                target=self._fetch_photo_meta,
                args=(local, ext, f, size_str),
                daemon=True,
            ).start()
        else:
            # HEIC / other — decode via QThread so the main thread never blocks
            self._photo_img_lbl.setText("Decoding…")
            w = _PhotoDecodeWorker(local, ext, pw)
            w.ready.connect(
                lambda px, fw=f, ss=size_str, ex=ext: self._apply_photo_pixmap(px, fw, ss, ex)
            )
            self._track(w)
            w.start()

    def _apply_photo_pixmap(self, px: QPixmap, f: dict, size_str: str,
                            ext: str) -> None:
        """Main-thread slot: apply decoded photo pixmap and trigger meta fetch."""
        self._photo_img_lbl.setText("")
        if px.isNull():
            self._photo_img_lbl.setText("Cannot render preview")
        else:
            self._photo_img_lbl.setPixmap(px)
        full_path = self._cache / f["name"]
        threading.Thread(
            target=self._fetch_photo_meta,
            args=(str(full_path), ext, f, size_str),
            daemon=True,
        ).start()

    def _fetch_photo_meta(self, img_src: str, ext: str, f: dict, size_str: str) -> None:
        """Background thread: read EXIF/dimensions from Pillow, then update label via signal."""
        width = height = 0
        date_str = ""
        try:
            from PIL import Image as PilImage
            if ext in {'.heic', '.heif'}:
                import pillow_heif
                pillow_heif.register_heif_opener()
            with PilImage.open(img_src) as im:
                width, height = im.size
                exif = im._getexif() if hasattr(im, '_getexif') else None
                if exif:
                    date_str = str(exif.get(36867) or exif.get(306) or "")
        except Exception:
            pass

        dim_str = f"{width} × {height} px" if width else ""
        meta_html = (
            f"<b>{f['name']}</b><br>"
            f"<font color='#555'>Path:</font> {f['path']}<br>"
            f"<font color='#555'>Size:</font> {size_str}"
            + (f"<br><font color='#555'>Dimensions:</font> {dim_str}" if dim_str else "")
            + (f"<br><font color='#555'>Date:</font> {date_str}" if date_str else "")
        )
        # Post to main thread via the label's thread-safe setText via invokeMethod
        self._photo_meta_lbl.setProperty("_pending_html", meta_html)
        QTimer.singleShot(0, lambda html=meta_html: self._photo_meta_lbl.setText(html))

    def _on_preview_open_sys(self) -> None:
        if self._preview_local and Path(self._preview_local).exists():
            _open_system(self._preview_local)

    # ── Video player controls ──────────────────────────────────────────────

    def _on_play_pause(self) -> None:
        if not self._player:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_stop_video(self) -> None:
        if self._player:
            self._player.stop()

    def _on_seek(self, pos_ms: int) -> None:
        if self._player:
            self._player.setPosition(pos_ms)

    def _on_player_state(self, state) -> None:
        if not _HAS_MULTIMEDIA:
            return
        if state == QMediaPlayer.PlayingState:
            self._play_btn.setText("⏸")
        else:
            self._play_btn.setText("▶")

    def _on_video_pos(self, pos_ms: int) -> None:
        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(pos_ms)
        self._seek_slider.blockSignals(False)
        secs = pos_ms // 1000
        self._time_lbl.setText(f"{secs // 60}:{secs % 60:02d}")

    def _on_video_dur(self, dur_ms: int) -> None:
        self._seek_slider.setRange(0, dur_ms)

    def _clear_preview(self) -> None:
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())
        self._preview_stack.setCurrentIndex(0)
        self._prev_name_lbl.setText("")
        self._prev_open_btn.setEnabled(False)
        self._popout_btn.setEnabled(False)
        self._photo_img_lbl.setPixmap(QPixmap())
        self._photo_meta_lbl.setText("")
        self._preview_local = None
        self._preview_row   = -1
        self._hide_preview_panel()

    # ── Preview panel show / hide / pop-out ───────────────────────────────

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Hide the MEDIA section label when the grid panel is too narrow to show it."""
        grid_width = self._inner_splitter.sizes()[0]
        self._grid_lbl.setVisible(grid_width >= 120)

    def _show_preview_panel(self) -> None:
        sizes = self._inner_splitter.sizes()
        if not self._preview_panel.isVisible() or sizes[1] < 10:
            total = sum(sizes) or (self._inner_splitter.width() or 800)
            w = min(self._preview_panel_width, total - 200)
            self._preview_panel.setVisible(True)
            self._inner_splitter.setSizes([total - w, w])

    def _hide_preview_panel(self) -> None:
        sizes = self._inner_splitter.sizes()
        if sizes[1] > 10:
            self._preview_panel_width = sizes[1]   # remember for next open
        self._preview_panel.setVisible(False)
        total = sum(sizes)
        self._inner_splitter.setSizes([total, 0])

    def _pop_out_preview(self) -> None:
        """Open current preview in a floating window."""
        if self._preview_stack.currentIndex() == 2 and self._preview_local:
            # Photo pop-out
            ext = Path(self._preview_local).suffix.lower()
            name = Path(self._preview_local).name
            self._popout_win = _PhotoPopout(self._preview_local, ext, name)
        elif self._preview_stack.currentIndex() == 1 and self._preview_local:
            # Video — open in system player
            _open_system(self._preview_local)

    def _on_folder_clicked(self, item: QListWidgetItem) -> None:
        """Single click — show folder's files in the right grid; left panel stays."""
        # No _any_busy() guard: _load_right disconnects the old worker's signals
        # before starting a new one, so rapid switching is safe.
        self._clear_preview()
        folder_path = str(PurePosixPath(self._current_path) / item.text())
        self._load_right(folder_path)

    def _on_folder_dbl(self, item: QListWidgetItem) -> None:
        """Double click — navigate into the folder; reload both panels."""
        if self._any_busy():
            return
        self._clear_preview()
        self._cancel_thumb_worker()
        self._path_stack.append(self._current_path)
        self._current_path = str(PurePosixPath(self._current_path) / item.text())
        self._load_dir()

    def _on_back(self) -> None:
        if self._any_busy() or not self._path_stack:
            return
        self._clear_preview()
        self._cancel_thumb_worker()
        self._current_path = self._path_stack.pop()
        self._load_dir()

    def _on_item_dbl(self, item: QListWidgetItem) -> None:
        """Download full file (or use cache) then open with system default app."""
        if not self._udid or self._any_busy():
            return
        row = self._grid.row(item)
        if row >= len(self._media_files):
            return
        f = self._media_files[row]

        local = str(
            self._cache / f["name"] if self._cache
            else Path(tempfile.gettempdir()) / "iphone_explorer" / f["name"]
        )

        if Path(local).exists():
            _open_system(local)
            # File already cached — try to update thumbnail if still placeholder
            self._try_update_thumb(row, local)
            return

        self._set_result(f"Downloading {f['name']} for preview…")
        self._open_worker = _DownloadOpenWorker(self._udid, f["path"], local)
        self._open_worker.ready.connect(lambda p, r=row: self._on_open_ready(p, r))
        self._open_worker.failed.connect(
            lambda e: self._set_result(f"Download failed: {e}", "#ef5350")
        )
        self._track(self._open_worker)
        self._open_worker.start()

    def _on_open_ready(self, local: str, row: int) -> None:
        self._set_result("")
        _open_system(local)
        self._try_update_thumb(row, local)

    def _try_update_thumb(self, row: int, local: str) -> None:
        """Generate + cache a thumbnail from a local file, then update the grid icon."""
        cache = self._cache

        def _decode_in_bg() -> None:
            jpeg = _thumb_jpeg_from_local(local)
            if not jpeg:
                return
            if cache:
                thumb_path = cache / ("_thumb_" + Path(local).stem + ".jpg")
                try:
                    thumb_path.write_bytes(jpeg)
                except Exception:
                    pass
            # QImage is thread-safe; QPixmap is NOT — create it on main thread
            img = QImage.fromData(jpeg)
            if not img.isNull():
                QTimer.singleShot(0, lambda i=img, r=row: self._apply_thumb(r, i))

        threading.Thread(target=_decode_in_bg, daemon=True).start()

    def _apply_thumb(self, row: int, img: QImage) -> None:
        """Apply a decoded QImage as a grid icon — always called on the main thread."""
        if row >= self._grid.count():
            return
        item = self._grid.item(row)
        if item is None:
            return
        try:
            item.setIcon(QIcon(QPixmap.fromImage(img)))
        except RuntimeError:
            pass  # item was deleted between scheduling and execution

    def _on_selection_changed(self) -> None:
        self._export_sel_btn.setEnabled(
            bool(self._grid.selectedItems()) and not self._any_busy()
        )

    def _on_export_selected(self) -> None:
        rows = {self._grid.row(i) for i in self._grid.selectedItems()}
        files = [self._media_files[r] for r in sorted(rows) if r < len(self._media_files)]
        if not files:
            return
        dest = self._pick_dest()
        if dest:
            self._start_export(files, dest)

    def _on_export_all(self) -> None:
        if not self._media_files:
            return
        dest = self._pick_dest()
        if dest:
            self._start_export(self._media_files, dest)

    def _on_export_bulk(self) -> None:
        if self._any_busy():
            return
        self._set_result("Scanning subfolders…")
        self._set_export_btns(False)
        self._scan_worker = _ScanWorker(self._udid, self._current_path)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.failed.connect(
            lambda e: (self._set_result(f"Scan failed: {e}", "#ef5350"),
                       self._set_export_btns(True))
        )
        self._track(self._scan_worker)
        self._scan_worker.start()

    def _on_scan_done(self, files: list) -> None:
        if not files:
            self._set_result("No media files found.", "#ffa726")
            self._set_export_btns(True)
            return
        dest = self._pick_dest()
        if dest:
            self._start_export(files, dest)
        else:
            self._set_export_btns(True)
            self._set_result("")

    def _on_export_progress(self, done: int, total: int) -> None:
        self._progress.setValue(done)
        self._set_result(f"Exporting…  {done} / {total}")

    def _on_export_done(self, count: int, total_bytes: int) -> None:
        self._progress.setVisible(False)
        self._set_export_btns(True)
        self._set_result(
            f"Exported {count} file{'s' if count != 1 else ''}  ({_fmt_size(total_bytes)})",
            color="#66bb6a",
        )

    def _on_export_failed(self, error: str) -> None:
        self._progress.setVisible(False)
        self._set_export_btns(True)
        self._set_result(f"Export failed: {error}", "#ef5350")

    def _pick_dest(self) -> str | None:
        folder = PurePosixPath(self._current_path).name or "DCIM"
        path = QFileDialog.getExistingDirectory(
            self, "Choose Export Folder",
            str(Path.home() / "iphone_photos" / folder),
        )
        return path or None

    def _start_export(self, files: list[dict], dest: str) -> None:
        self._progress.setRange(0, len(files))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._set_export_btns(False)
        self._set_result(f"Exporting {len(files)} files…")
        self._export_worker = _ExportWorker(self._udid, files, dest)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._track(self._export_worker)
        self._export_worker.start()

    # ── Data loading ───────────────────────────────────────────────────────

    def _track(self, worker: QThread) -> None:
        """Keep a Python reference to a worker until its thread finishes."""
        self._live_workers.add(worker)
        worker.finished.connect(lambda: self._live_workers.discard(worker))

    def _disconnect_list_worker(self) -> None:
        """Disconnect signals from the current list worker so stale results are dropped."""
        if self._list_worker is not None:
            try:
                self._list_worker.finished.disconnect()
                self._list_worker.failed.disconnect()
            except RuntimeError:
                pass

    def _load_right(self, path: str) -> None:
        """Load a folder's files into the right grid only — left panel unchanged."""
        if not self._udid:
            return
        self._disconnect_list_worker()
        self._cancel_thumb_worker()
        self._grid.clear()
        self._media_files = []
        self._summary_lbl.setText("Loading…")
        self._set_export_btns(False)
        self._set_result("")
        self._breadcrumb.setText(f"Viewing:  {path}")

        self._list_worker = _ListDirWorker(self._udid, path)
        self._list_worker.finished.connect(
            lambda entries: self._populate(entries, update_folders=False)
        )
        self._list_worker.failed.connect(
            lambda e: (
                self._summary_lbl.setText(""),
                self._set_result(f"Could not read folder: {e}", "#ef5350"),
            )
        )
        self._track(self._list_worker)
        self._list_worker.start()

    def _load_dir(self) -> None:
        if not self._udid:
            return
        self._disconnect_list_worker()
        self._cancel_thumb_worker()
        self._update_breadcrumb()
        self._grid.clear()
        self._folder_list.clear()
        self._media_files = []
        self._summary_lbl.setText("Loading…")
        self._set_export_btns(False)
        self._set_result("")

        self._list_worker = _ListDirWorker(self._udid, self._current_path)
        self._list_worker.finished.connect(self._populate)
        self._list_worker.failed.connect(
            lambda e: (
                self._summary_lbl.setText(""),
                self._set_result(f"Could not read folder: {e}", "#ef5350"),
            )
        )
        self._track(self._list_worker)
        self._list_worker.start()

    # ── Abort ──────────────────────────────────────────────────────────────

    def abort_all(self) -> None:
        """Cancel every running worker — called by MainWindow on page switch."""
        self._cancel_thumb_worker()
        if self._player:
            self._player.stop()
        for w in (self._list_worker, self._export_worker, self._scan_worker):
            if w is not None and w.isRunning():
                w.cancel()

    # ── State setters ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        self._cancel_thumb_worker()
        self._clear_preview()
        self._udid = None
        self._cache = None
        self._media_files = []
        self._status.setText("No device connected.")
        self._grid.clear()
        self._folder_list.clear()
        self._summary_lbl.setText("")
        self._breadcrumb.setText("")
        self._progress.setVisible(False)
        self._set_result("")
        self._set_export_btns(False)
        self._back_btn.setEnabled(False)

    def show_connecting(self) -> None:
        self._cancel_thumb_worker()
        self._clear_preview()
        self._udid = None
        self._cache = None
        self._status.setText("Connecting…")
        self._grid.clear()
        self._folder_list.clear()
        self._summary_lbl.setText("")
        self._set_export_btns(False)
        self._back_btn.setEnabled(False)

    def show_device(self, info: DeviceInfo) -> None:
        first_connect = self._udid is None
        self._udid  = info.udid
        self._cache = _cache_dir(info.udid)
        self._status.setText(f"Connected: {info.name}")
        if first_connect:
            self._current_path = "/DCIM"
            self._path_stack   = []
            self._load_dir()
