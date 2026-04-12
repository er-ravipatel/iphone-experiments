# Project Context

## Active Workspace

- Current working repo path: `C:\Workspace\Personal\iphone-experiments`
- Current active branch: `feature-desktop-ui`
- This repo is the source of truth for ongoing work.

## Agent Handoff Summary

**Last session completed (2026-04-12):**
- Extended `DeviceInfo` with 15+ new fields (IMEI, IMEI2, MEID, ICCID, phone number, board ID, chip ID, baseband, firmware, MLB serial, Find My lock, passcode status, developer mode, battery external/full states)
- Full redesign of `DiagnosticsPage` — 3uTools-style layout with categorised info tables + coloured status cards
- Live screenshot panel in Diagnostics (auto-refreshes every 4 s; gracefully degrades to "Requires Developer Mode" message when not available — `com.apple.mobile.screenshotr` is a developer service on iOS 16+)
- `MediaPage` preview pane overhaul: resizable via QSplitter, pop-out floating window, full-resolution photo preview (downloads full file, falls back to thumbnail as placeholder), EXIF metadata display
- Fixed periodic device poll resetting the media page: new `_on_refresh_info()` path updates only the header/dashboard every 15 s without touching media page state
- `_PhotoPopout` floating window with Fit/Full-Size toggle and scroll panning
- `_PhotoDecodeWorker` QThread for HEIC decode on background thread (safe QPixmap on main thread)

**Previous sessions:**
- Viewport-aware lazy thumbnail loading (visible items first, `_get_visible_rows()`)
- Video preview with in-app `QMediaPlayer` playback
- `abort_all()` interface on every page, called by `MainWindow._navigate()`
- QThread crash fixes: `_live_workers: set`, signal disconnect before replacement, no blocking `wait()` on main thread
- Concurrent AFC stat calls in `_listdir` (semaphore of 8, ~8x speedup)

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
  - **Same device, periodic tick (every 15 s)** → `_on_refresh_info()` — silently refreshes header + dashboard only. Media and Apps pages are NOT reset.
- Device info fetching: `_DeviceInfoWorker(QThread)`.
- **Every page exposes `abort_all()`** — called by `MainWindow._navigate()` before switching.

### Pages

| Page | Index | File | Notes |
|---|---|---|---|
| Dashboard | 0 | `src/gui/pages/dashboard_page.py` | Battery/storage bars, connectivity cards |
| Diagnostics | 1 | `src/gui/pages/diagnostics_page.py` | 3uTools-style — see below |
| Screenshot | 2 | `src/gui/pages/screenshot_page.py` | Capture + preview |
| Apps | 3 | `src/gui/pages/apps_page.py` | List/install/uninstall |
| Photos & Videos | 4 | `src/gui/pages/media_page.py` | Full media browser — see below |

### Threading Rules (critical — crashes if violated)

1. **`QPixmap` only on main thread.** Workers emit `bytes` or `QImage`; slot calls `QPixmap.fromImage()`.
2. **`_live_workers: set` on every page** with QThread workers. Add on `.start()`, remove on `finished`. Prevents Python GC destroying a running QThread.
3. **Signal disconnect before worker replacement.** Call `_disconnect_list_worker()` before assigning a new `_ListDirWorker`.
4. **No blocking `wait()` on main thread.** Call `worker.cancel()` + disconnect signals; thread finishes naturally, kept alive by `_live_workers`.
5. **`QTimer.singleShot(0, fn)` from `threading.Thread` is unreliable.** Use a proper `QThread` with a `Signal` instead. (Lesson learned in photo preview work.)

---

## DiagnosticsPage — 3uTools-style layout

**File:** `src/gui/pages/diagnostics_page.py`

### Layout
- **Left column** (scrollable): 4 categorised `QTableWidget`s
  - `_tbl_identity` — Device Identity (name, model, product type, model number, hardware model, iOS, build, serial, UDID, IMEI, IMEI2, MEID, ICCID, phone number, region, color)
  - `_tbl_hardware` — Hardware (CPU arch, platform, board ID, chip ID as hex, die ID, baseband version, firmware, MLB serial)
  - `_tbl_connectivity` — Connectivity (WiFi, Bluetooth, Ethernet MAC)
  - `_tbl_battery` — Battery & Storage (level, charge status, plugged in, total/used/free)
- **Right column**: 5 `_StatusCard` widgets with green ✓ / red ✗ / grey ? dot indicators
  - Activation State, iCloud Lock, Find My, Passcode, Developer Mode
- **Right column bottom**: Live screenshot panel (`_ScreenshotWorker`)
  - Auto-starts when page is shown, stops when hidden (via `showEvent`/`hideEvent`)
  - Stops retrying on `InvalidServiceError` — shows "Requires Developer Mode" message
  - Refreshes every 4 s when developer mode is enabled

### DeviceInfo — new fields (all from `ideviceinfo` default domain, no developer mode needed)

| Field | Source key | Notes |
|---|---|---|
| `imei` | `InternationalMobileEquipmentIdentity` | |
| `imei2` | `InternationalMobileEquipmentIdentity2` | dual-SIM |
| `meid` | `MobileEquipmentIdentifier` | |
| `iccid` | `IntegratedCircuitCardIdentity` | SIM card |
| `phone_number` | `PhoneNumber` | |
| `model_number` | `ModelNumber` | SKU, e.g. "MGMN3" |
| `hardware_model` | `HardwareModel` | e.g. "D53pAP" |
| `hardware_platform` | `HardwarePlatform` | e.g. "t8101" |
| `board_id` | `BoardId` | |
| `chip_id` | `ChipID` | shown as hex via `chip_id_hex` property |
| `die_id` | `DieID` | |
| `baseband_version` | `BasebandVersion` | |
| `firmware_version` | `FirmwareVersion` | |
| `mlb_serial` | `MLBSerialNumber` | motherboard serial |
| `ethernet_address` | `EthernetAddress` | |
| `find_my_locked` | `NonVolatileRAM.fm-activation-locked` | base64-decoded "YES"/"NO" |
| `password_protected` | `PasswordProtected` | |
| `battery_external_connected` | `ExternalConnected` (battery domain) | |
| `battery_fully_charged` | `FullyCharged` (battery domain) | |
| `developer_mode` | `com.apple.security.mac.amfi → DeveloperModeStatus` | via pymobiledevice3 |

**Screenshot service constraint:** `com.apple.mobile.screenshotr` is a developer service on iOS 16+. Both `idevicescreenshot` (libimobiledevice) and pymobiledevice3 confirm `InvalidService` without developer mode. No workaround exists at the Apple protocol level.

---

## MediaPage — Photos & Videos

**File:** `src/gui/pages/media_page.py`

### Preview pane (updated)

- Hidden by default, shown when any file is selected.
- **Resizable**: implemented as `QSplitter` between grid and preview panel (`self._inner_splitter`). Panel width is remembered in `self._preview_panel_width` and restored on next open.
- **Pop-out button**: "⤢ Pop Out" button opens `_PhotoPopout(QWidget, Qt.Window)` — floating window with Fit/Full-Size toggle and scroll area for panning.
- **Photo preview** (stack index 2):
  - Shows full-resolution photo, not thumbnail.
  - JPEG/PNG: loaded directly with `QImage(path)` on main thread (fast, Qt-native).
  - HEIC: decoded by `_PhotoDecodeWorker(QThread)` via Pillow + pillow-heif, emits `QPixmap` via signal.
  - If full file not cached: shows thumbnail as placeholder, downloads file in background via `_DownloadOpenWorker`, then replaces with full-res on completion.
  - EXIF metadata (dimensions, date taken) read in `threading.Thread`, updates label via `QTimer.singleShot(0, lambda html=...: label.setText(html))`.
- **Video preview** (stack index 1): unchanged — `QMediaPlayer` + `QVideoWidget`, auto-play on click.
- `_clear_preview()` hides panel and stops any playing video.
- `_show_preview_panel()` / `_hide_preview_panel()` manage splitter sizes.
- Video pop-out: opens file in system player via `_open_system()` (moving `QMediaPlayer` between windows is not supported in Qt).

### Toolbar buttons
Removed `setFixedWidth` from Export buttons — replaced with `setMinimumWidth`. This allows the splitter handle to move left freely (fixed widths were forcing a minimum width on the grid panel that blocked leftward drag).

---

## DeviceInfo (`src/device/info.py`)

- `find_my_locked`: parsed from `NonVolatileRAM` multiline block in `ideviceinfo` output. The block contains `fm-activation-locked: <base64>` where base64 decodes to "YES" or "NO".
- `chip_id_hex`: computed property — converts decimal chip ID string to `0xXXXX` hex format.
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
| 5 | Files | AFC file browser — upload / download / delete / rename |
| 6 | Backup & Restore | streaming output, progress bar, restore confirmation |
| 7 | Screen Mirror | port tkinter scaffold to PySide6 + live stream (needs dev mode) |

**Other open items:**
- Video thumbnail improvement: extract frame without downloading full file (partial download or on-device frame extraction)
- Suppress OpenCV ffmpeg stderr noise when extracting video frames
- Package desktop app as standalone Windows `.exe`

---

## Repo Organization

```
iphone-experiments/
  main.py              ← terminal entry point
  desktop.py           ← GUI entry point
  requirements.txt
  assets/              ← app icons (svg/png/ico)
  src/
    gui/
      app.py           ← QApplication factory + dark stylesheet
      icon.py          ← icon generator
      tray.py          ← system tray manager
      main_window.py
      pages/
        dashboard_page.py
        diagnostics_page.py   ← 3uTools-style, updated this session
        screenshot_page.py
        apps_page.py
        media_page.py         ← full media browser, updated this session
      widgets/
        device_header.py
    device/
      detector.py      ← idevice_id wrapper
      info.py          ← DeviceInfo dataclass + fetcher, extended this session
    terminal/
      features/        ← shared feature modules (media, apps, backup, etc.)
    utils/
      platform.py
      runner.py
  scripts/debug/
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
