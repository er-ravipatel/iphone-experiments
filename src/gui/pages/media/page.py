"""
MediaPage — Photos & Videos browser.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path, PurePosixPath

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QProgressBar, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer, QEvent
from PySide6.QtGui import QColor, QIcon, QPixmap, QImage

from ....device.info import DeviceInfo
from ....terminal.features.media import VIDEO_EXTENSIONS

from .workers import (
    ListDirWorker, ThumbnailWorker, DownloadOpenWorker,
    ExportWorker, ScanWorker, _thumb_jpeg_from_local,
)
from .widgets import GripSplitter
from .preview_panel import PreviewPanel
from ._utils import (
    THUMB_SIZE, ITEM_SIZE, LABEL_CHARS,
    cache_dir, fmt_size, ext_placeholder,
)


class MediaPage(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._current_path = "/DCIM"
        self._path_stack: list[str] = []
        self._media_files: list[dict] = []
        self._cache: Path | None = None

        self._list_worker:   ListDirWorker      | None = None
        self._thumb_worker:  ThumbnailWorker     | None = None
        self._open_worker:   DownloadOpenWorker  | None = None
        self._export_worker: ExportWorker        | None = None
        self._scan_worker:   ScanWorker          | None = None
        self._thumb_gen: int = 0
        self._live_workers: set = set()

        self._build_ui()
        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # Title row — title + summary + export buttons + status
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

        # Body: folder list | grid | preview
        body = QHBoxLayout()
        body.setSpacing(12)

        # ── Left: folder list ──────────────────────────────────────────────
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
            lambda cur, _: self._on_folder_clicked(cur) if cur else None
        )
        left_vbox.addWidget(self._folder_list)

        self._back_btn = QPushButton("← Back")
        self._back_btn.clicked.connect(self._on_back)
        left_vbox.addWidget(self._back_btn)
        body.addWidget(left)

        # ── Centre: thumbnail grid ─────────────────────────────────────────
        right = QWidget()
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.setSpacing(6)

        self._grid_lbl = QLabel("MEDIA")
        self._grid_lbl.setObjectName("SectionLabel")
        right_vbox.addWidget(self._grid_lbl)

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

        right.setMinimumWidth(0)
        self._grid.setMinimumWidth(0)

        # ── Splitter: grid | preview ───────────────────────────────────────
        self._splitter = GripSplitter(Qt.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(10)
        self._splitter.setStyleSheet(
            "QSplitter::handle:horizontal { background: #242424;"
            "  border-left: 1px solid #1a1a1a; border-right: 1px solid #1a1a1a; }"
            "QSplitter::handle:horizontal:hover { background: #1e3040; }"
        )
        self._splitter.addWidget(right)

        self._preview = PreviewPanel(self)
        self._preview.result_message.connect(self._set_result)
        self._preview.setMinimumWidth(180)
        self._preview_width = 340
        self._preview.setVisible(False)
        self._splitter.addWidget(self._preview)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([800, 0])
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        body.addWidget(self._splitter, stretch=1)
        outer.addLayout(body, stretch=1)

        self._result_lbl = QLabel()
        self._result_lbl.setObjectName("StatusLabel")
        self._result_lbl.setWordWrap(True)
        outer.addWidget(self._result_lbl)

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
            try:
                self._thumb_worker.thumbnail_ready.disconnect()
            except RuntimeError:
                pass
        self._thumb_worker = None

    def _update_breadcrumb(self) -> None:
        self._breadcrumb.setText(f"Location:  {self._current_path}")
        self._back_btn.setEnabled(self._current_path != "/DCIM")

    def _track(self, worker: QThread) -> None:
        self._live_workers.add(worker)
        worker.finished.connect(lambda: self._live_workers.discard(worker))

    def _disconnect_list_worker(self) -> None:
        if self._list_worker is not None:
            try:
                self._list_worker.finished.disconnect()
                self._list_worker.failed.disconnect()
            except RuntimeError:
                pass

    # ── Grid population ────────────────────────────────────────────────────

    def _populate(self, entries: list[dict], update_folders: bool = True) -> None:
        folders = [e for e in entries if e["is_dir"]]
        media   = [e for e in entries if not e["is_dir"] and e.get("is_media")]
        self._media_files = media

        if update_folders:
            self._folder_list.clear()
            for f in folders:
                item = QListWidgetItem(f["name"])
                item.setForeground(QColor("#4fc3f7"))
                self._folder_list.addItem(item)

        self._grid.setUpdatesEnabled(False)
        self._grid.clear()
        for f in media:
            ext   = Path(f["name"]).suffix.lower()
            icon  = ext_placeholder(ext)
            stem  = Path(f["name"]).stem
            label = stem if len(stem) <= LABEL_CHARS else stem[:LABEL_CHARS - 1] + "…"
            item  = QListWidgetItem(icon, label)
            item.setToolTip(f"{f['name']}  {fmt_size(f['size'])}")
            self._grid.addItem(item)
        self._grid.setUpdatesEnabled(True)

        n = len(media)
        total_sz = sum(f["size"] for f in media)
        if n:
            self._summary_lbl.setText(
                f"{n} file{'s' if n != 1 else ''}   {fmt_size(total_sz)}"
                "   — double-click to open"
            )
        else:
            self._summary_lbl.setText("No media files here — select a subfolder")

        self._set_export_btns(True)

        if self._udid and self._cache and media:
            self._cancel_thumb_worker()
            self._thumb_gen += 1
            gen = self._thumb_gen
            QTimer.singleShot(150, lambda: self._start_thumb_loading(gen))

    # ── Thumbnail loading ──────────────────────────────────────────────────

    def _on_thumbnail_ready(self, index: int, data: bytes) -> None:
        if index >= self._grid.count() or not data:
            return
        item = self._grid.item(index)
        if item is None:
            return
        img = QImage.fromData(data)
        if not img.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(img)))

    def _get_visible_rows(self) -> set[int]:
        visible: set[int] = set()
        vr = self._grid.viewport().rect()
        for i in range(self._grid.count()):
            item = self._grid.item(i)
            if item and vr.intersects(self._grid.visualItemRect(item)):
                visible.add(i)
        return visible

    def _start_thumb_loading(self, gen: int) -> None:
        if gen != self._thumb_gen:
            return
        if not self._udid or not self._cache or not self._media_files:
            return
        visible = self._get_visible_rows()
        self._thumb_worker = ThumbnailWorker(
            self._udid, self._media_files, self._cache, visible
        )
        self._thumb_worker.thumbnail_ready.connect(self._on_thumbnail_ready)
        self._track(self._thumb_worker)
        self._thumb_worker.start()

    def _on_scroll(self, _value: int) -> None:
        if self._thumb_worker and self._thumb_worker.isRunning():
            self._thumb_worker.add_priority_rows(self._get_visible_rows())

    # ── Arrow-key preview debounce ─────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        if obj is self._grid and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                self._preview_debounce.start()
        return super().eventFilter(obj, event)

    def _on_preview_debounce_fire(self) -> None:
        item = self._grid.currentItem()
        if item:
            self._on_item_clicked(item)

    # ── Item interaction ───────────────────────────────────────────────────

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if not self._udid or not self._cache:
            return
        row = self._grid.row(item)
        if row < 0 or row >= len(self._media_files):
            return
        self._show_preview_panel()
        self._preview.load(self._media_files[row], row, self._media_files)

    def _on_item_dbl(self, item: QListWidgetItem) -> None:
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
            from ._utils import open_system
            open_system(local)
            self._try_update_thumb(row, local)
            return

        self._set_result(f"Downloading {f['name']} for preview…")
        self._open_worker = DownloadOpenWorker(self._udid, f["path"], local)
        self._open_worker.ready.connect(lambda p, r=row: self._on_open_ready(p, r))
        self._open_worker.failed.connect(
            lambda e: self._set_result(f"Download failed: {e}", "#ef5350")
        )
        self._track(self._open_worker)
        self._open_worker.start()

    def _on_open_ready(self, local: str, row: int) -> None:
        self._set_result("")
        from ._utils import open_system
        open_system(local)
        self._try_update_thumb(row, local)

    def _try_update_thumb(self, row: int, local: str) -> None:
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
            img = QImage.fromData(jpeg)
            if not img.isNull():
                QTimer.singleShot(0, lambda i=img, r=row: self._apply_thumb(r, i))

        threading.Thread(target=_decode_in_bg, daemon=True).start()

    def _apply_thumb(self, row: int, img: QImage) -> None:
        if row >= self._grid.count():
            return
        item = self._grid.item(row)
        if item is None:
            return
        try:
            item.setIcon(QIcon(QPixmap.fromImage(img)))
        except RuntimeError:
            pass

    def _on_selection_changed(self) -> None:
        self._export_sel_btn.setEnabled(
            bool(self._grid.selectedItems()) and not self._any_busy()
        )

    # ── Splitter / preview panel show/hide ─────────────────────────────────

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        self._grid_lbl.setVisible(self._splitter.sizes()[0] >= 120)

    def _show_preview_panel(self) -> None:
        sizes = self._splitter.sizes()
        if not self._preview.isVisible() or sizes[1] < 10:
            total = sum(sizes) or (self._splitter.width() or 800)
            w = min(self._preview_width, total - 200)
            self._preview.setVisible(True)
            self._splitter.setSizes([total - w, w])

    def _hide_preview_panel(self) -> None:
        sizes = self._splitter.sizes()
        if sizes[1] > 10:
            self._preview_width = sizes[1]
        self._preview.setVisible(False)
        self._splitter.setSizes([sum(sizes), 0])

    # ── Folder navigation ──────────────────────────────────────────────────

    def _on_folder_clicked(self, item: QListWidgetItem) -> None:
        self._preview.clear()
        self._hide_preview_panel()
        folder_path = str(PurePosixPath(self._current_path) / item.text())
        self._load_right(folder_path)

    def _on_folder_dbl(self, item: QListWidgetItem) -> None:
        if self._any_busy():
            return
        self._preview.clear()
        self._hide_preview_panel()
        self._cancel_thumb_worker()
        self._path_stack.append(self._current_path)
        self._current_path = str(PurePosixPath(self._current_path) / item.text())
        self._load_dir()

    def _on_back(self) -> None:
        if self._any_busy() or not self._path_stack:
            return
        self._preview.clear()
        self._hide_preview_panel()
        self._cancel_thumb_worker()
        self._current_path = self._path_stack.pop()
        self._load_dir()

    # ── Export ─────────────────────────────────────────────────────────────

    def _on_export_selected(self) -> None:
        rows  = {self._grid.row(i) for i in self._grid.selectedItems()}
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
        self._scan_worker = ScanWorker(self._udid, self._current_path)
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
            f"Exported {count} file{'s' if count != 1 else ''}  ({fmt_size(total_bytes)})",
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
        self._export_worker = ExportWorker(self._udid, files, dest)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.finished.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._track(self._export_worker)
        self._export_worker.start()

    # ── Data loading ───────────────────────────────────────────────────────

    def _load_right(self, path: str) -> None:
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

        self._list_worker = ListDirWorker(self._udid, path)
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

        self._list_worker = ListDirWorker(self._udid, self._current_path)
        self._list_worker.finished.connect(self._populate)
        self._list_worker.failed.connect(
            lambda e: (
                self._summary_lbl.setText(""),
                self._set_result(f"Could not read folder: {e}", "#ef5350"),
            )
        )
        self._track(self._list_worker)
        self._list_worker.start()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def abort_all(self) -> None:
        """Cancel every running worker — called by MainWindow on page switch."""
        self._cancel_thumb_worker()
        self._preview.abort()
        for w in (self._list_worker, self._export_worker, self._scan_worker):
            if w is not None and w.isRunning():
                w.cancel()

    def show_no_device(self) -> None:
        self._cancel_thumb_worker()
        self._preview.clear()
        self._hide_preview_panel()
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
        self._preview.clear()
        self._hide_preview_panel()
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
        self._cache = cache_dir(info.udid)
        self._preview.set_context(info.udid, self._cache)
        self._status.setText(f"Connected: {info.name}")
        if first_connect:
            self._current_path = "/DCIM"
            self._path_stack   = []
            self._load_dir()
