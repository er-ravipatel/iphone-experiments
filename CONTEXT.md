# Project Context

## Active Workspace

- Current working repo path: `C:\Workspace\Personal\iphone-experiments`
- Current active branch: `feature-desktop-ui`
- This repo is the source of truth for ongoing work.

## Agent Handoff Summary

**Last session completed (2026-04-16):**
- **MediaPage SRP refactor** — `media_page.py` (1525 lines) decomposed into `src/gui/pages/media/` package (6 files, ~900 lines total)
- **Milestone 5: Files page** — `src/gui/pages/files/` package with full AFC file browser
- **Logging** — `iphone_desktop.log` written to the app folder; DEBUG level throughout; noisy libs silenced
- **PopOut nav fixes** — arrow-key prev/next in `PhotoPopout`, `_live_workers` crash fix, focus policy fixes
- **`media_page.py` deleted** — legacy file removed, new package is the active implementation

**Previous sessions:**
- Extended `DeviceInfo` with 15+ new fields (IMEI, IMEI2, MEID, ICCID, phone number, board ID, chip ID, baseband, firmware, MLB serial, Find My lock, passcode status, developer mode, battery external/full states)
- Full redesign of `DiagnosticsPage` — 3uTools-style layout with categorised info tables + coloured status cards
- Live screenshot panel in Diagnostics (auto-refreshes every 4 s; gracefully degrades to "Requires Developer Mode" message when not available)
- `MediaPage` preview pane: resizable via QSplitter, pop-out floating window, full-res photo preview, EXIF metadata display
- Fixed periodic device poll resetting the media page: `_on_refresh_info()` path updates only header/dashboard every 15 s
- Viewport-aware lazy thumbnail loading, video preview with in-app `QMediaPlayer`
- `abort_all()` interface on every page, called by `MainWindow._navigate()`
- QThread crash fixes: `_live_workers: set`, signal disconnect before replacement

---

## Goal

PySide6 desktop GUI (`desktop.py`) is the primary active development surface.
Terminal CLI (`main.py`) is feature-complete.

---

## Desktop GUI App (`desktop.py`)

Entry point: `desktop.py` → `src/gui/main_window.py`

### Architecture

- `MainWindow` hosts a sidebar nav, `QStackedWidget` for pages, and an activity log.
- Device polling: `QTimer` every 2.5 s (cheap `idevice_id` call on main thread).
  - **New device / first connect** → `_on_connecting()` — full reset of all pages.
  - **Same device, periodic tick (every 15 s)** → `_on_refresh_info()` — silently refreshes header + dashboard only. Other pages are NOT reset.
- Device info fetching: `_DeviceInfoWorker(QThread)`.
- **Every page exposes `abort_all()`** — called by `MainWindow._navigate()` before switching.

### Pages

| Page | Index | Module | Notes |
|---|---|---|---|
| Dashboard | 0 | `src/gui/pages/dashboard_page.py` | Battery/storage bars, connectivity cards |
| Diagnostics | 1 | `src/gui/pages/diagnostics_page.py` | 3uTools-style — see below |
| Screenshot | 2 | `src/gui/pages/screenshot_page.py` | Capture + preview |
| Apps | 3 | `src/gui/pages/apps_page.py` | List/install/uninstall |
| Photos & Videos | 4 | `src/gui/pages/media/` | SRP package — see below |
| Files | 5 | `src/gui/pages/files/` | SRP package — see below |

### Threading Rules (critical — crashes if violated)

1. **`QPixmap` only on main thread.** Workers emit `bytes` or `QImage`; slot calls `QPixmap.fromImage()`.
2. **`_live_workers: set` on every page** with QThread workers. Add before `.start()`, discard via `finished` signal callback. Prevents Python GC destroying a running QThread.
3. **Signal disconnect before worker replacement.** Disconnect `finished`/`failed` before assigning a new worker. Park still-running workers in `_live_workers` with a `finished.connect(lambda _w=old: _live_workers.discard(_w))`.
4. **No blocking `wait()` on main thread.** Call `worker.cancel()` + disconnect signals; thread finishes naturally, kept alive by `_live_workers`.
5. **`QTimer.singleShot(0, fn)` from `threading.Thread` is unreliable.** Use a proper `QThread` with a `Signal` instead.

---

## MediaPage — Photos & Videos

**Package:** `src/gui/pages/media/`

| File | Class | Responsibility |
|---|---|---|
| `__init__.py` | — | Re-exports `MediaPage` |
| `_utils.py` | — | Constants (`THUMB_SIZE=155`, `ITEM_SIZE=162`) + pure helpers |
| `workers.py` | 6 workers | `ListDirWorker`, `ThumbnailWorker`, `PhotoDecodeWorker`, `DownloadOpenWorker`, `ExportWorker`, `ScanWorker` |
| `widgets.py` | `GripSplitter`, `PhotoPopout` | Custom splitter with grip dots; floating photo viewer with prev/next nav |
| `preview_panel.py` | `PreviewPanel` | Photo/video preview, EXIF metadata, pop-out |
| `page.py` | `MediaPage` | Orchestrator — wires everything via signals |

### Key behaviours

- **Thumbnail grid**: `ITEM_SIZE=162`, `setSpacing(2)` — tight layout. Folders first, lazy-loaded.
- **MEDIA section label**: auto-hides when grid panel < 120 px wide (via `_on_splitter_moved`).
- **Arrow-key debounce**: `eventFilter` on grid intercepts arrow keys → `QTimer(400ms, singleShot=True)`. Preview loads only after 400 ms pause.
- **Preview**: cleared on folder switch; pop-out (`PhotoPopout`) supports arrow-key prev/next navigation across photos.
- **`PhotoPopout._live_workers`**: critical — keeps running `PhotoDecodeWorker` refs alive when navigating quickly. Without this, Python GC destroys the running thread → app crash.

---

## FilesPage — AFC File Browser

**Package:** `src/gui/pages/files/`

| File | Class | Responsibility |
|---|---|---|
| `__init__.py` | — | Re-exports `FilesPage` |
| `workers.py` | 6 workers | `ListDirWorker`, `DownloadWorker`, `UploadWorker`, `DeleteWorker`, `RenameWorker`, `MkdirWorker` |
| `breadcrumb.py` | `BreadcrumbBar` | Reusable clickable path bar — emits `path_selected(str)` |
| `file_table.py` | `FileTableWidget` | Reusable sortable table (folders first) — emits `entry_activated(dict)`, `selection_changed(object)` |
| `action_bar.py` | `ActionBar` | Upload/Download/Delete/Rename/New Folder buttons + progress. Driven entirely by `set_state()` — zero business logic inside. |
| `page.py` | `FilesPage` | Thin orchestrator — wires components via signals, manages workers |

### Design patterns

- **Single Responsibility**: each class has exactly one job
- **Observer**: siblings never call each other directly; all cross-component messages flow through signals
- **Facade**: `FilesPage` is the only public surface; internals are hidden
- **Template Method**: every worker implements only `run()`

### Key behaviours

- Root starts at `/` — user can navigate the full AFC filesystem
- Double-click folder → navigate in; double-click file → download prompt
- Breadcrumb segments are clickable — jump to any ancestor (back-stack rebuilt correctly)
- `ActionBar.set_state()` disables buttons during transfers so no double-ops
- `blockSignals(True/False)` around `clear_entries()` prevents spurious selection callbacks

### Known limitations

- AFC only exposes user-accessible paths (Documents, DCIM, Media, etc.) — system paths are locked
- Download loads full file into RAM before writing; no streaming for large files

---

## DiagnosticsPage — 3uTools-style layout

**File:** `src/gui/pages/diagnostics_page.py`

### Layout
- **Left column** (scrollable): 4 categorised `QTableWidget`s
  - `_tbl_identity` — Device Identity (name, model, product type, iOS, build, serial, UDID, IMEI, IMEI2, MEID, ICCID, phone number, region, color)
  - `_tbl_hardware` — Hardware (CPU arch, platform, board ID, chip ID as hex, die ID, baseband version, firmware, MLB serial)
  - `_tbl_connectivity` — Connectivity (WiFi, Bluetooth, Ethernet MAC)
  - `_tbl_battery` — Battery & Storage (level, charge status, plugged in, total/used/free)
- **Right column**: 5 `_StatusCard` widgets with green ✓ / red ✗ / grey ? dot indicators
  - Activation State, iCloud Lock, Find My, Passcode, Developer Mode
- **Right column bottom**: Live screenshot panel (`_ScreenshotWorker`)
  - Auto-starts when page is shown, stops when hidden
  - Stops retrying on `InvalidServiceError` — shows "Requires Developer Mode"
  - Refreshes every 4 s when developer mode is enabled

---

## DeviceInfo (`src/device/info.py`)

- `find_my_locked`: parsed from `NonVolatileRAM` multiline block; base64-decoded "YES"/"NO".
- `chip_id_hex`: computed property — converts decimal chip ID to `0xXXXX` hex.
- `icloud_locked`: computed property — True if `activation_state` is not "Activated".
- NVRAM parsing: `_parse_nvram()` walks raw text looking for indented lines after `NonVolatileRAM:` header.

---

## Screenshot / Mirror Constraints

- `com.apple.mobile.screenshotr` requires Developer Mode on iOS 16+. Confirmed by both `idevicescreenshot` and pymobiledevice3.
- Mirror: use `pymobiledevice3`, not `ideviceimagemounter.exe`. Live frame stream backend still pending.
- Developer Mode: Settings → Privacy & Security → Developer Mode → toggle On → restart device.

---

## Pending Milestones (GUI)

| Milestone | Page | Notes |
|---|---|---|
| 6 | Backup & Restore | streaming output, progress bar, restore confirmation |
| 7 | Screen Mirror | PySide6 port + live stream (needs dev mode on iOS 16+) |

**Other open items:**
- Video thumbnail improvement: extract frame without downloading full file
- Suppress OpenCV ffmpeg stderr noise when extracting video frames
- Package desktop app as standalone Windows `.exe`

---

## Logging

- Log file: `c:\Workspace\Personal\iphone-experiments\iphone_desktop.log`
- Level: DEBUG throughout; asyncio, pymobiledevice3, urllib3 silenced to WARNING
- Tail: `Get-Content .\iphone_desktop.log -Wait -Tail 50`

---

## Repo Organization

```
iphone-experiments/
  main.py              ← terminal entry point
  desktop.py           ← GUI entry point (logging setup here)
  requirements.txt
  assets/              ← app icons (svg/png/ico)
  src/
    gui/
      app.py           ← QApplication factory + dark stylesheet
      icon.py          ← icon generator
      tray.py          ← system tray manager
      main_window.py   ← sidebar nav, QStackedWidget, device polling
      pages/
        dashboard_page.py
        diagnostics_page.py
        screenshot_page.py
        apps_page.py
        media/         ← SRP package (6 files)
          __init__.py, _utils.py, workers.py, widgets.py, preview_panel.py, page.py
        files/         ← SRP package (6 files)
          __init__.py, workers.py, breadcrumb.py, file_table.py, action_bar.py, page.py
      widgets/
        device_header.py
    device/
      detector.py      ← idevice_id wrapper
      info.py          ← DeviceInfo dataclass + fetcher
    terminal/
      features/        ← shared feature modules (media, apps, backup, files, etc.)
    utils/
      platform.py
      runner.py
```

## Branch Strategy

`master` — full codebase  
`feature-desktop-ui` — active GUI development (current)

## Dependencies

```
PySide6>=6.6.0
pillow-heif>=0.15.0
opencv-python-headless>=4.8.0
pymobiledevice3>=4.0.0
rich>=13.7.0
textual>=0.61.0
click>=8.1.7
```
