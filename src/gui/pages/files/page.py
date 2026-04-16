"""
FilesPage — AFC file browser + "On My iPhone" app-document browser.

Navigation domains
------------------
"root"         Virtual root: shows [📁 Media] + per-app document folders.
               Entry point whenever the device connects / page resets.
"afc"          Standard AFC tree (/DCIM, /Downloads, …).
               Entered by double-clicking the Media folder from root.
"house_arrest" Per-app Documents tree via HouseArrestService.
               Entered by double-clicking an app folder from root.

Breadcrumb root label changes with domain:
  root          → "📱 <device name>"
  afc           → "📁 Media"
  house_arrest  → "📱 <app display name>"

Up from the top of any domain always returns to the virtual root.
"""
from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt

from ....device.info import DeviceInfo
from .breadcrumb import BreadcrumbBar
from .file_table import FileTableWidget
from .action_bar import ActionBar
from .workers import (
    ListDirWorker, ListAppsWorker,
    DownloadWorker, UploadWorker,
    DeleteWorker, RenameWorker, MkdirWorker,
)

log = logging.getLogger(__name__)


class FilesPage(QWidget):
    """
    Top-level Files page.

    Responsibilities
    ----------------
    - Own the page-level state machine (no_device / connecting / ready)
    - Track the current navigation domain (root / afc / house_arrest)
    - Spawn and park background workers
    - React to child-component signals and issue commands back

    Everything else lives in the child components.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._device_name: str = ""

        # Navigation state
        self._domain: str = "root"          # "root" | "afc" | "house_arrest"
        self._current_path: str = "/"
        self._path_stack: list[str] = []
        self._app_bundle_id: str | None = None
        self._app_display_name: str | None = None

        self._live_workers: set = set()

        # Active workers (one slot each)
        self._list_worker:  ListDirWorker | ListAppsWorker | None = None
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

        self._up_btn = QPushButton("⬆  Up")
        self._up_btn.setFixedHeight(32)
        self._up_btn.setMinimumWidth(80)
        self._up_btn.setStyleSheet(
            "QPushButton { color: #4fc3f7; border: 1px solid #4fc3f7;"
            "  border-radius: 4px; padding: 4px 14px; background: transparent; }"
            "QPushButton:hover { background: #0d2233; }"
            "QPushButton:disabled { color: #333; border-color: #2a2a2a; }"
        )
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
        self._device_name = ""
        self._reset_to_root()
        self._file_table.clear_entries()
        self._status_lbl.setText("No device connected")
        self._crumb.set_root_label("📱 iPhone")
        self._crumb.set_path("/")
        self._up_btn.setEnabled(False)
        self._refresh_action_bar()

    def show_connecting(self) -> None:
        log.debug("FilesPage: show_connecting")
        self.abort_all()
        self._udid = None
        self._device_name = ""
        self._reset_to_root()
        self._file_table.clear_entries()
        self._status_lbl.setText("Connecting…")
        self._crumb.set_root_label("📱 iPhone")
        self._up_btn.setEnabled(False)
        self._refresh_action_bar()

    def show_device(self, info: DeviceInfo) -> None:
        log.debug("FilesPage: show_device udid=%s", info.udid)
        if self._udid == info.udid:
            return   # same device, keep current browsing state
        self._udid = info.udid
        self._device_name = info.name
        self._reset_to_root()
        self._status_lbl.setText(info.name)
        self._crumb.set_root_label(f"📱 {info.name}")
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

    # ── Domain helpers ─────────────────────────────────────────────────────

    def _reset_to_root(self) -> None:
        self._domain = "root"
        self._current_path = "/"
        self._path_stack = []
        self._app_bundle_id = None
        self._app_display_name = None

    def _current_bundle_id(self) -> str | None:
        """Return the bundle_id for workers when in house_arrest domain, else None."""
        return self._app_bundle_id if self._domain == "house_arrest" else None

    # ── Directory listing ──────────────────────────────────────────────────

    def _list_current(self) -> None:
        if not self._udid:
            return
        log.debug("FilesPage: listing domain=%s path=%s", self._domain, self._current_path)
        self._file_table.clear_entries()
        self._action_bar.show_progress("Listing…")
        self._crumb.set_path(self._current_path)
        self._up_btn.setEnabled(self._domain != "root" or bool(self._path_stack))
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

        if self._domain == "root":
            w: QWidget = ListAppsWorker(self._udid)
        else:
            w = ListDirWorker(self._udid, self._current_path,
                              bundle_id=self._current_bundle_id())

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
        if self._domain == "root":
            self._status_lbl.setText(
                f"{len(entries) - 1} app{'s' if len(entries) != 2 else ''}  ·  Media"
            )
        else:
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
        # ── Virtual-root sentinels ─────────────────────────────────────────
        if entry.get("_is_media_entry"):
            log.debug("FilesPage: entering AFC domain")
            self._domain = "afc"
            self._current_path = "/"
            self._path_stack = []
            self._app_bundle_id = None
            self._app_display_name = None
            self._crumb.set_root_label("📁  Media")
            self._list_current()
            return

        if entry.get("_is_app_entry"):
            bundle_id = entry["_bundle_id"]
            display   = entry["name"]
            log.debug("FilesPage: entering house_arrest domain for %s", bundle_id)
            self._domain = "house_arrest"
            self._current_path = "/"
            self._path_stack = []
            self._app_bundle_id = bundle_id
            self._app_display_name = display
            self._crumb.set_root_label(f"📱  {display}")
            self._list_current()
            return

        # ── Regular navigation ─────────────────────────────────────────────
        if entry["is_dir"]:
            self._path_stack.append(self._current_path)
            self._current_path = entry["path"]
            log.debug("FilesPage: navigate into %s", self._current_path)
            self._list_current()
        else:
            self._on_download()

    def _go_up(self) -> None:
        # At the top of a non-root domain → back to virtual root
        if self._domain in ("afc", "house_arrest") and not self._path_stack:
            log.debug("FilesPage: back to virtual root from domain=%s", self._domain)
            self._reset_to_root()
            root_label = f"📱 {self._device_name}" if self._device_name else "📱 iPhone"
            self._crumb.set_root_label(root_label)
            self._list_current()
            return

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
        # Rebuild the back-stack so Up works correctly after a breadcrumb jump.
        parts = [p for p in path.split("/") if p]
        self._path_stack = []
        built = "/"
        for p in parts:
            self._path_stack.append(built)
            built = str(PurePosixPath(built) / p)
        self._current_path = path
        log.debug("FilesPage: breadcrumb jump → %s  (stack depth %d)",
                  self._current_path, len(self._path_stack))
        self._list_current()

    # ── Action handlers ────────────────────────────────────────────────────

    def _on_upload(self) -> None:
        if not self._udid or self._domain == "root":
            return
        local, _ = QFileDialog.getOpenFileName(self, "Choose file to upload")
        if not local:
            return
        name   = Path(local).name
        remote = str(PurePosixPath(self._current_path) / name)
        log.debug("FilesPage: upload %s → %s", local, remote)
        self._start_transfer(
            UploadWorker(self._udid, local, remote,
                         bundle_id=self._current_bundle_id()),
            slot="up_worker",
            label=f"Uploading {name}…",
            on_done=lambda n: self._after_op(f"Uploaded {_fmt_size(n)}", refresh=True),
        )

    def _on_download(self) -> None:
        entry = self._file_table.selected_entry()
        if not entry or entry["is_dir"] or not self._udid or self._domain == "root":
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save file as", entry["name"])
        if not dest:
            return
        log.debug("FilesPage: download %s → %s", entry["path"], dest)
        self._start_transfer(
            DownloadWorker(self._udid, entry["path"], dest,
                           bundle_id=self._current_bundle_id()),
            slot="down_worker",
            label=f"Downloading {entry['name']}…",
            on_done=lambda n: self._after_op(f"Downloaded {_fmt_size(n)}", refresh=False),
        )

    def _on_delete(self) -> None:
        entry = self._file_table.selected_entry()
        if not entry or not self._udid or self._domain == "root":
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
            DeleteWorker(self._udid, entry["path"],
                         bundle_id=self._current_bundle_id()),
            slot="del_worker",
            label=f"Deleting {entry['name']}…",
            on_done=lambda: self._after_op("Deleted successfully", refresh=True),
        )

    def _on_rename(self) -> None:
        entry = self._file_table.selected_entry()
        if not entry or not self._udid or self._domain == "root":
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
            RenameWorker(self._udid, entry["path"], dst,
                         bundle_id=self._current_bundle_id()),
            slot="ren_worker",
            label=f"Renaming to {new_name}…",
            on_done=lambda: self._after_op("Renamed successfully", refresh=True),
        )

    def _on_mkdir(self) -> None:
        if not self._udid or self._domain == "root":
            return
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        path = str(PurePosixPath(self._current_path) / name.strip())
        log.debug("FilesPage: mkdir %s", path)
        self._start_transfer(
            MkdirWorker(self._udid, path,
                        bundle_id=self._current_bundle_id()),
            slot="mkdir_worker",
            label=f"Creating {name}…",
            on_done=lambda: self._after_op("Folder created", refresh=True),
        )

    # ── Transfer helper (DRY) ──────────────────────────────────────────────

    def _start_transfer(self, worker, *, slot: str, label: str, on_done) -> None:
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

        def _on_done(*args) -> None:
            on_done(*args)
            self._action_bar.hide_progress()
            self._refresh_action_bar()

        def _discard_worker(*_args, _w=worker) -> None:
            self._live_workers.discard(_w)

        worker.finished.connect(_on_done)
        worker.failed.connect(_on_fail)
        worker.finished.connect(_discard_worker)
        worker.failed.connect(lambda _msg, _w=worker: self._live_workers.discard(_w))
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
        # Disable file operations when at the virtual root (no real FS behind it)
        in_fs      = self._domain != "root"
        has_any    = entry is not None and not entry.get("_is_media_entry") \
                     and not entry.get("_is_app_entry")
        has_file   = has_any and not entry["is_dir"]
        busy       = self._is_busy()
        self._action_bar.set_state(
            has_device=has_device and in_fs,
            has_file_sel=has_file,
            has_any_sel=has_any,
            busy=busy,
        )
        # Up button: disabled at root domain (nothing above)
        self._up_btn.setEnabled(
            has_device and (self._domain != "root" or bool(self._path_stack))
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
