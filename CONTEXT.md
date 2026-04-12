# Project Context

## Active Workspace

- Current working repo path: `C:\Workspace\Personal\iphone-experiments`
- Current active branch: `feature-desktop-ui`
- This repo is the source of truth for ongoing work.
- The earlier mistaken copy under `C:\Workspace\Personal\iphone-storage-explorer\iphone-experiments` is no longer in use and has been removed.

## Agent Handoff Summary

- Default branch for continued work: `feature-desktop-ui`
- Current repo state: clean working tree at the moment this context was refreshed
- Recently completed:
  - desktop icon system in `src/gui/icon.py`
  - system tray manager in `src/gui/tray.py`
  - app/tray/taskbar icon wiring in `desktop.py`, `src/gui/app.py`, and `src/gui/main_window.py`
  - permanent icon assets in `assets/app-icon.svg`, `assets/app-icon.png`, `assets/app-icon.ico`
  - tray notifications for device connected, disconnected, low battery, and low storage
- Important known issue:
  - desktop media video thumbnails are still not fully fixed and should be treated as open work
- Remaining major GUI milestones:
  - Files page
  - Backup & Restore page
  - Screen Mirror page migration from scaffold to PySide6
  - Settings page
  - packaging desktop app as a standalone Windows executable for best taskbar identity

## Goal

This repository explores a terminal-first iPhone management tool for Windows and other desktop platforms. The main direction is to keep the terminal app as the control center while using separate windows only when a richer visual surface is required, such as screen mirroring.

A full **PySide6 desktop GUI** (`desktop.py`) has been built in parallel and is the primary active development surface.

---

## Desktop GUI App (`desktop.py`)

Entry point: `desktop.py` → `src/gui/main_window.py`

### Architecture

- `MainWindow` hosts a sidebar nav, `QStackedWidget` for pages, and an activity log.
- Device polling runs on a `QTimer` (2.5 s interval, main thread, cheap `idevice_id` call).
- Device info fetching runs on a `_DeviceInfoWorker(QThread)`.
- **Every page exposes `abort_all()`** — called by `MainWindow._navigate()` before switching pages so running workers are cancelled and the outgoing page is cleanly stopped.
- Desktop app branding now uses generated icon assets stored in `assets/`.
- System tray support is wired through `src/gui/tray.py` and used by `MainWindow`.

### Pages

| Page | Index | File |
|---|---|---|
| Dashboard | 0 | `src/gui/pages/dashboard_page.py` |
| Diagnostics | 1 | `src/gui/pages/diagnostics_page.py` |
| Screenshot | 2 | `src/gui/pages/screenshot_page.py` |
| Apps | 3 | `src/gui/pages/apps_page.py` |
| Photos & Videos | 4 | `src/gui/pages/media_page.py` |

### Desktop Branding / Notifications

- App icon source: `assets/app-icon.svg`
- Generated Windows assets: `assets/app-icon.png`, `assets/app-icon.ico`
- Icon generator: `src/gui/icon.py`
- Tray manager: `src/gui/tray.py`
- `desktop.py` sets a Windows AppUserModelID for better taskbar grouping
- `MainWindow` shows tray notifications for device connected, device disconnected, low battery, and low storage

### Threading Rules (critical)

All pages follow these rules to prevent crashes:

1. **`QPixmap` must only be created on the main thread.** Workers pass raw bytes or `QImage` via signals; `QPixmap.fromImage()` is called in the slot.
2. **`_live_workers: set` keeps Python references** to all running QThread workers. Without this, Python GC can destroy a QThread while its OS thread is running → `QThread: Destroyed while thread is still running` crash.
3. **Signal disconnect before worker replacement.** When starting a new `_ListDirWorker`, `_disconnect_list_worker()` is called first to prevent the old worker's stale `finished` signal from calling `_populate()` on top of fresh data.
4. **No blocking `wait()` on main thread.** `_cancel_thumb_worker()` disconnects the signal immediately and sets `self._thumb_worker = None` — the thread runs to completion in the background, kept alive by `_live_workers`.
5. **asyncio workers** (`_ThumbnailWorker`, `_ExportWorker`, etc.) use a `_stop` flag checked between loop iterations. Single-shot async calls (`_ListDirWorker`, `_ScanWorker`) discard results via signal disconnect or flag check.

### MediaPage — Photos & Videos

Key design decisions:

**Directory listing (`_listdir` in `src/terminal/features/media.py`)**
- `afc.listdir()` returns all names in one call.
- `afc.stat()` is called concurrently (semaphore of 8) for all entries. Sequential stat was the biggest bottleneck: 300 files × ~15 ms = ~4.5 s. Concurrent stat brings it to ~0.5 s.

**Thumbnail loading (`_ThumbnailWorker`)**
- Grid items are populated with placeholder icons first (`setUpdatesEnabled(False/True)` suppresses per-item repaints for large folders).
- `QTimer.singleShot(150, ...)` defers worker start so the grid layout has rendered and `_get_visible_rows()` returns accurate viewport data.
- Visible rows are loaded first (priority set), background rows at ~20/sec with `asyncio.sleep(0.05)`.
- On scroll, `_on_scroll()` calls `worker.add_priority_rows()` to reprioritize.
- `_make_thumb_jpeg()` runs entirely in the worker thread (decoding HEIC via pillow-heif, scaling via Pillow). Emits small JPEG bytes. Main thread only calls `QImage.fromData()` + `QPixmap.fromImage()`.
- Thumbnail JPEGs are cached as `_thumb_{stem}.jpg` in `%TEMP%/iphone_explorer/{udid8}/`. Revisiting a folder is near-instant.

**Video thumbnails**
- Videos emit cached `_thumb_{stem}.jpg` if it exists (generated on first preview).
- On first single-click, video is downloaded and played via `QMediaPlayer`.
- After download, `_try_update_thumb(row, local)` extracts a frame via OpenCV (`_try_video_frame`), saves the thumbnail JPEG to cache, and schedules `_apply_thumb(row, img)` on the main thread via `QTimer.singleShot(0, ...)`.

**Navigation**
- Single-click folder → `_load_right()`: loads right grid only, left panel unchanged. `_disconnect_list_worker()` called first.
- Double-click folder → `_load_dir()`: full navigation, both panels reload.
- Arrow-key folder nav connected via `currentItemChanged` signal.

**Preview panel**
- 320 px right-side panel, video-only. Photo single-click calls `_clear_preview()` which stops any playing video.
- `QMediaPlayer` + `QVideoWidget` with play/pause, stop, seek slider, time display.
- "Open in System App" button (`os.startfile` on Windows).

### AppsPage

- `_live_workers: set` tracks all running workers to prevent GC crash.
- `_ListAppsWorker` wraps `asyncio.run(_list_apps(...))`.
- `_AppActionWorker` runs install/uninstall coroutines.
- Auto-loads app list on first device connect.

### Thumbnail Cache Location

```
%TEMP%\iphone_explorer\{udid[:8]}\
  {filename}.{ext}          ← full downloaded file
  _thumb_{stem}.jpg         ← pre-scaled JPEG thumbnail (THUMB_SIZE=155px)
```

---

## Terminal App (`main.py`)

High-level flow:

1. Prepare terminal encoding and PATH
2. Verify core tools exist
3. Poll for connected device
4. Fetch device info
5. Render dashboard and interactive menu
6. Dispatch to feature modules

### Important Modules

#### `src/device`
- `detector.py` — detects devices using `idevice_id`
- `info.py` — builds `DeviceInfo` from `ideviceinfo` and `pymobiledevice3`

#### `src/utils`
- `platform.py` — finds required tools, returns install instructions
- `runner.py` — common subprocess wrapper

#### `src/ui`
- `dashboard.py` — Rich dashboard
- `menu.py` — interactive prompts and formatting helpers
- `progress.py` — spinners, progress bars, live streaming output

#### `src/terminal/features`
- `files.py` — AFC file browsing and transfers
- `apps.py` — app listing, install, uninstall
- `media.py` — photo/video export from DCIM; `_listdir` uses concurrent stat
- `backup.py` — backup and restore
- `diagnostics.py` — diagnostics, reboot, shutdown
- `screenshot.py` — screenshot capture
- `rename.py` — device rename
- `mirror.py` — mirror window scaffold

---

## Storage Behavior

Storage values from `com.apple.disk_usage` domain.
- Total capacity: decimal GB
- Free space: `AmountDataAvailable`
- Do not use `TotalDataAvailable` for user-visible free space

## Screenshot / Mirror Constraints

- Developer services blocked without Developer Mode enabled and DDI mounted
- Mirror: use `pymobiledevice3`, not `ideviceimagemounter.exe`
- Mirror live frame stream backend still pending

---

## Repo Organization

```
iphone-experiments/
  main.py              ← terminal entry point
  desktop.py           ← GUI entry point
  requirements.txt
  src/
    gui/
      main_window.py
      pages/
      widgets/
    device/
    terminal/
      features/
    utils/
  scripts/debug/
```

## Branch Strategy

`master` — full codebase  
`feature-desktop-ui` — active GUI development

Feature branches (terminal): `feature-files`, `feature-apps`, `feature-media`, `feature-backup`, `feature-diagnostics`, `feature-screenshot`, `feature-rename`, `feature-mirror`, `feature-device`, `feature-ui`, `feature-utils`

## Dependencies

```
PySide6>=6.6.0          # GUI framework
pillow-heif>=0.15.0     # HEIC thumbnail decoding
opencv-python-headless>=4.8.0  # video frame extraction
pymobiledevice3>=4.0.0  # AFC, device services
rich>=13.7.0            # terminal UI
textual>=0.61.0
click>=8.1.7
```

## Next Steps (GUI)

- Files page — AFC file browser with upload/download/delete
- Backup & Restore page — streaming output, progress bar
- Screen Mirror page — port tkinter scaffold to PySide6 + live stream
- Improve video thumbnail generation (extract without downloading full file)
- Suppress OpenCV ffmpeg stderr noise
