"""
FilesPage — AFC file browser orchestrator.

Composes BreadcrumbBar + FileTableWidget + ActionBar and manages workers.
Contains no rendering logic — delegates everything to its child components.

States driven by MainWindow:
  show_no_device()
  show_connecting()
  show_device(info)
  abort_all()
"""
from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFileDialog, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt

from ....device.info import DeviceInfo
from .breadcrumb import BreadcrumbBar
from .file_table import FileTableWidget
from .action_bar import ActionBar
from .workers import (
    ListDirWorker, DownloadWorker, UploadWorker,
    DeleteWorker, RenameWorker, MkdirWorker,
)

log = logging.getLogger(__name__)


class FilesPage(QWidget):
    """
    Top-level Files page.

    Responsibilities
    ----------------
    - Own the page-level state machine (no_device / connecting / ready)
    - Spawn and park background workers
    - React to child-component signals and issue commands back

    Everything else lives in the child components.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._current_path = "/"
        self._path_stack: list[str] = []
        self._live_workers: set = set()

        # Active workers (one slot each)
        self._list_worker:  ListDirWorker  | None = None
        self._down_worker:  DownloadWorker | None = None
        self._up_worker:    UploadWorker   | None = None
        self._del_worker:   DeleteWorker   | None = None
        self._ren_worker:   RenameWorker   | None = None
        self._mkdir_worker: MkdirWorker    | None = None

        self._build_ui()
        self.show_no_device()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(10)

        # Title + status
        title_row = QHBoxLayout()
        title = QLabel("File Browser")
        title.setObjectName("PageTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self._status_lbl = QLabel()
        self._status_lbl.setObjectName("StatusLabel")
        title_row.addWidget(self._status_lbl)
        outer.addLayout(title_row)

        # Breadcrumb + Up button on one row
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        self._crumb = BreadcrumbBar()
        self._crumb.path_selected.connect(self._on_breadcrumb_selected)
        nav_row.addWidget(self._crumb, stretch=1)

        from PySide6.QtWidgets import QPushButton
        self._up_btn = QPushButton("⬆ Up")
        self._up_btn.setFixedSize(60, 32)
        self._up_btn.clicked.connect(self._go_up)
        nav_row.addWidget(self._up_btn)
        outer.addLayout(nav_row)

        # File table
        self._file_table = FileTableWidget()
        self._file_table.entry_activated.connect(self._on_entry_activated)
        self._file_table.selection_changed.connect(self._on_selection_changed)
        outer.addWidget(self._file_table, stretch=1)

        # Action bar
        self._action_bar = ActionBar()
        self._action_bar.upload_requested.connect(self._on_upload)
        self._action_bar.download_requested.connect(self._on_download)
        self._action_bar.delete_requested.connect(self._on_delete)
        self._action_bar.rename_requested.connect(self._on_rename)
        self._action_bar.mkdir_requested.connect(self._on_mkdir)
        outer.addWidget(self._action_bar)

    # ── State machine ──────────────────────────────────────────────────────

    def show_no_device(self) -> None:
        log.debug("FilesPage: show_no_device")
        self.abort_all()
        self._udid = None
        self._file_table.clear_entries()
        self._status_lbl.setText("No device connected")
        self._crumb.set_path("/")
        self._up_btn.setEnabled(False)
        self._refresh_action_bar()

    def show_connecting(self) -> None:
        log.debug("FilesPage: show_connecting")
        self.abort_all()
        self._udid = None
        self._file_table.clear_entries()
        self._status_lbl.setText("Connecting…")
        self._up_btn.setEnabled(False)
        self._refresh_action_bar()

    def show_device(self, info: DeviceInfo) -> None:
        log.debug("FilesPage: show_device udid=%s", info.udid)
        if self._udid == info.udid:
            return   # same device, keep current browsing state
        self._udid = info.udid
        self._current_path = "/"
        self._path_stack = []
        self._status_lbl.setText(info.name)
        self._list_current()

    def abort_all(self) -> None:
        """Cancel all running workers safely (park running threads in _live_workers)."""
        log.debug("FilesPage: abort_all")
        for w in (self._list_worker, self._down_worker, self._up_worker,
                  self._del_worker, self._ren_worker, self._mkdir_worker):
            if w is not None and w.isRunning():
                log.debug("FilesPage: parking %s", type(w).__name__)
                self._live_workers.add(w)
                try:
                    w.finished.disconnect()
                    w.failed.disconnect()
                except RuntimeError:
                    pass
                w.finished.connect(lambda _w=w: self._live_workers.discard(_w))
        self._list_worker = self._down_worker = self._up_worker = None
        self._del_worker = self._ren_worker = self._mkdir_worker = None
        self._action_bar.hide_progress()

    # ── Directory listing ──────────────────────────────────────────────────

    def _list_current(self) -> None:
        if not self._udid:
            return
        log.debug("FilesPage: listing %s", self._current_path)
        self._file_table.clear_entries()
        self._action_bar.show_progress("Listing…")
        self._crumb.set_path(self._current_path)
        self._up_btn.setEnabled(self._current_path != "/")
        self._refresh_action_bar()

        # Park any existing list worker before replacing
        if self._list_worker and self._list_worker.isRunning():
            old = self._list_worker
            self._live_workers.add(old)
            try:
                old.finished.disconnect()
                old.failed.disconnect()
            except RuntimeError:
                pass
            old.finished.connect(lambda _w=old: self._live_workers.discard(_w))

        w = ListDirWorker(self._udid, self._current_path)
        self._list_worker = w
        self._live_workers.add(w)
        w.finished.connect(self._on_list_done)
        w.failed.connect(self._on_list_failed)
        w.finished.connect(lambda _l, _w=w: self._live_workers.discard(_w))
        w.failed.connect(lambda _m, _w=w: self._live_workers.discard(_w))
        w.start()

    def _on_list_done(self, entries: list[dict]) -> None:
        log.debug("FilesPage: list done — %d entries", len(entries))
        self._action_bar.hide_progress()
        self._file_table.load_entries(entries)
        dirs  = sum(1 for e in entries if e["is_dir"])
        files = sum(1 for e in entries if not e["is_dir"])
        self._status_lbl.setText(
            f"{dirs} folder{'s' if dirs != 1 else ''}  ·  "
            f"{files} file{'s' if files != 1 else ''}"
        )
        self._refresh_action_bar()

    def _on_list_failed(self, msg: str) -> None:
        log.error("FilesPage: list failed: %s", msg)
        self._action_bar.hide_progress()
        self._status_lbl.setText(f"Error reading directory: {msg}")
        self._refresh_action_bar()

    # ── Navigation ─────────────────────────────────────────────────────────

    def _on_entry_activated(self, entry: dict) -> None:
        if entry["is_dir"]:
            self._path_stack.append(self._current_path)
            self._current_path = entry["path"]
            log.debug("FilesPage: navigate into %s", self._current_path)
            self._list_current()
        else:
            self._on_download()

    def _go_up(self) -> None:
        if self._path_stack:
            self._current_path = self._path_stack.pop()
        else:
            parent = str(PurePosixPath(self._current_path).parent)
            self._current_path = parent or "/"
        log.debug("FilesPage: go up → %s", self._current_path)
        self._list_current()

    def _on_breadcrumb_selected(self, path: str) -> None:
        if path == self._current_path:
            return
        # Rebuild stack: all ancestors of *path*
        parts = [p for p in path.split("/") if p]
        self._path_stack = []
        built = "/"
        for p in parts[:-1]:
            self._path_stack.append(built)
            built = str(PurePosixPath(built) / p)
        self._current_path = path
        log.debug("FilesPage: breadcrumb jump → %s", self._current_path)
        self._list_current()

    # ── Action handlers ────────────────────────────────────────────────────

    def _on_upload(self) -> None:
        if not self._udid:
            return
        local, _ = QFileDialog.getOpenFileName(self, "Choose file to upload")
        if not local:
            return
        name   = Path(local).name
        remote = str(PurePosixPath(self._current_path) / name)
        log.debug("FilesPage: upload %s → %s", local, remote)
        self._start_transfer(
            UploadWorker(self._udid, local, remote),
            slot="up_worker",
            label=f"Uploading {name}…",
            on_done=lambda n: self._after_op(f"Uploaded {_fmt_size(n)}", refresh=True),
        )

    def _on_download(self) -> None:
        entry = self._file_table.selected_entry()
        if not entry or entry["is_dir"] or not self._udid:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save file as", entry["name"])
        if not dest:
            return
        log.debug("FilesPage: download %s → %s", entry["path"], dest)
        self._start_transfer(
            DownloadWorker(self._udid, entry["path"], dest),
            slot="down_worker",
            label=f"Downloading {entry['name']}…",
            on_done=lambda n: self._after_op(f"Downloaded {_fmt_size(n)}", refresh=False),
        )

    def _on_delete(self) -> None:
        entry = self._file_table.selected_entry()
        if not entry or not self._udid:
            return
        kind = "folder" if entry["is_dir"] else "file"
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {kind} '{entry['name']}' from the device?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        ) != QMessageBox.Yes:
            return
        log.debug("FilesPage: delete %s", entry["path"])
        self._start_transfer(
            DeleteWorker(self._udid, entry["path"]),
            slot="del_worker",
            label=f"Deleting {entry['name']}…",
            on_done=lambda: self._after_op("Deleted successfully", refresh=True),
        )

    def _on_rename(self) -> None:
        entry = self._file_table.selected_entry()
        if not entry or not self._udid:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=entry["name"]
        )
        if not ok or not new_name.strip() or new_name.strip() == entry["name"]:
            return
        new_name = new_name.strip()
        dst = str(PurePosixPath(self._current_path) / new_name)
        log.debug("FilesPage: rename %s → %s", entry["path"], dst)
        self._start_transfer(
            RenameWorker(self._udid, entry["path"], dst),
            slot="ren_worker",
            label=f"Renaming to {new_name}…",
            on_done=lambda: self._after_op("Renamed successfully", refresh=True),
        )

    def _on_mkdir(self) -> None:
        if not self._udid:
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        path = str(PurePosixPath(self._current_path) / name.strip())
        log.debug("FilesPage: mkdir %s", path)
        self._start_transfer(
            MkdirWorker(self._udid, path),
            slot="mkdir_worker",
            label=f"Creating {name}…",
            on_done=lambda: self._after_op("Folder created", refresh=True),
        )

    # ── Transfer helper (DRY) ──────────────────────────────────────────────

    def _start_transfer(self, worker, *, slot: str, label: str, on_done) -> None:
        """
        Generic helper to start any single-slot transfer worker.

        Parameters
        ----------
        worker  : the QThread worker to start
        slot    : name of the instance attribute that holds this worker type
        label   : progress bar text
        on_done : callable connected to worker.finished
        """
        setattr(self, f"_{slot}", worker)
        self._live_workers.add(worker)
        self._action_bar.show_progress(label)
        self._refresh_action_bar()

        def _on_fail(msg: str) -> None:
            log.error("FilesPage [%s]: %s", slot, msg)
            self._action_bar.hide_progress()
            self._refresh_action_bar()
            self._status_lbl.setText(f"Error: {msg}")
            QMessageBox.critical(self, "Operation Failed", msg)

        # worker.finished may be Signal() or Signal(int) depending on worker type
        worker.finished.connect(lambda *args: (on_done(*args), self._action_bar.hide_progress(), self._refresh_action_bar()))
        worker.failed.connect(_on_fail)
        worker.finished.connect(lambda *_a, _w=worker: self._live_workers.discard(_w))
        worker.failed.connect(lambda _m, _w=worker: self._live_workers.discard(_w))
        worker.start()

    def _after_op(self, msg: str, *, refresh: bool) -> None:
        self._status_lbl.setText(msg)
        if refresh:
            self._list_current()

    # ── Action-bar state sync ──────────────────────────────────────────────

    def _on_selection_changed(self, entry) -> None:
        self._refresh_action_bar()

    def _refresh_action_bar(self) -> None:
        entry      = self._file_table.selected_entry()
        has_device = self._udid is not None
        has_any    = entry is not None
        has_file   = has_any and not entry["is_dir"]
        busy       = self._is_busy()
        self._action_bar.set_state(
            has_device=has_device,
            has_file_sel=has_file,
            has_any_sel=has_any,
            busy=busy,
        )

    def _is_busy(self) -> bool:
        transfer_workers = [
            self._down_worker, self._up_worker,
            self._del_worker, self._ren_worker, self._mkdir_worker,
        ]
        return any(w is not None and w.isRunning() for w in transfer_workers)


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"
