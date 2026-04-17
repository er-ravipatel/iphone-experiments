# Project Context

## Active Workspace

- Current working repo path: `C:\Workspace\Personal\iphone-experiments`
- Current active branch: `feature-passcode-recovery-assistant`
- This repo is the source of truth for ongoing work.

## Agent Handoff Summary

**Current troubleshooting session (2026-04-16):**
- The desktop app direction is now explicitly a USB-based iPhone troubleshooting and recovery tool
- `TroubleshootPage` is being added near the top of the sidebar as a new diagnosis-focused page
- `TroubleshootService` is the reusable logic layer for snapshots, issue detection, health summaries, and recommended actions
- Current MVP issue coverage: no device, blocked device info / likely trust-unlock required, low storage, backup risk, developer mode off, screenshot readiness, mirror readiness, and missing critical tools

**Current recovery-preparation session (2026-04-17):**
- Branch: `feature-passcode-recovery-assistant`
- Adding `Passcode Recovery` and `Recovery Mode Assistant` as guided recovery flows
- The app explicitly does not bypass device passcodes or Activation Lock
- Current goal is to prepare users for supported erase/restore and recovery-mode steps while surfacing local backup availability first
- Next planned phase after this work: richer restore guidance, recovery-mode verification on real hardware, and eventually firmware/update workflow support

**Last session completed (2026-04-16):**
- **MediaPage SRP refactor** — `media_page.py` (1525 lines) decomposed into `src/gui/pages/media/` package (6 files)
- **Milestone 5: Files page** — `src/gui/pages/files/` SRP package (breadcrumb, file table, action bar, workers, page)
- **Milestone 6: Backup & Restore page** — `src/gui/pages/backup_restore/` SRP package (backup table, output log, action bar, workers, page)
- **Logging** — `iphone_desktop.log` written to app folder; DEBUG level throughout
- **PopOut nav fixes** — arrow-key prev/next in `PhotoPopout`, `_live_workers` crash fix, focus policy fixes
- **Bug fixes post-verification** — breadcrumb stack rebuild, lambda tuple → named inner functions, `blockSignals` around `clear_entries()`
- `media_page.py` deleted; new package is the active implementation

> ⚠️ **Milestone 5 (Files) and Milestone 6 (Backup & Restore) have NOT been manually tested against a real device.** Code passes import checks only. Must be verified end-to-end with a connected iPhone before considering them production-ready.

**Previous sessions:**
- Extended `DeviceInfo` with 15+ new fields (IMEI, IMEI2, MEID, ICCID, phone number, board ID, chip ID, baseband, firmware, MLB serial, Find My lock, passcode status, developer mode, battery external/full states)
- Full redesign of `DiagnosticsPage` — 3uTools-style with categorised info tables + status cards
- Live screenshot panel in Diagnostics (auto-refreshes every 4 s; gracefully degrades without Developer Mode)
- `MediaPage` preview pane: resizable splitter, pop-out floating window, full-res photo preview, EXIF metadata
- Fixed periodic device poll resetting media page: `_on_refresh_info()` updates only header/dashboard
- Viewport-aware lazy thumbnail loading, video preview with in-app `QMediaPlayer`
- `abort_all()` interface on every page, called by `MainWindow._navigate()`
- QThread crash fixes: `_live_workers: set`, signal disconnect before replacement

---

## Goal

PySide6 desktop GUI (`desktop.py`) is the primary active development surface.
Terminal CLI (`main.py`) is feature-complete.
The desktop product vision is a USB-based iPhone troubleshooting and recovery app that highlights what is wrong, why it is happening, and the next safe action.

---

## Desktop GUI App (`desktop.py`)

Entry point: `desktop.py` → `src/gui/main_window.py`

### Architecture

- `MainWindow` hosts a sidebar nav, `QStackedWidget` for pages, and an activity log.
- Device polling: `QTimer` every 2.5 s (cheap `idevice_id` call on main thread).
  - **New device / first connect** → `_on_connecting()` — full reset of all pages.
  - **Same device, periodic tick (every 15 s)** → `_on_refresh_info()` — silently refreshes header + dashboard only.
- Device info fetching: `_DeviceInfoWorker(QThread)`.
- Sidebar now includes `Troubleshoot` near the top. It is intended to become the flagship diagnosis surface for the desktop app.
- **Every page exposes `abort_all()`** — called by `MainWindow._navigate()` before switching.

### Pages

| Page | Index | Module | Manual Test Status |
|---|---|---|---|
| Dashboard | 0 | `pages/dashboard_page.py` | ✅ Tested |
| Diagnostics | 1 | `pages/diagnostics_page.py` | ✅ Tested |
| Screenshot | 2 | `pages/screenshot_page.py` | ✅ Tested |
| Apps | 3 | `pages/apps_page.py` | ✅ Tested |
| Photos & Videos | 4 | `pages/media/` | ✅ Tested |
| Files | 5 | `pages/files/` | ⚠️ **NOT manually tested** |
| Backup & Restore | 6 | `pages/backup_restore/` | ⚠️ **NOT manually tested** |

### Threading Rules (critical — crashes if violated)

1. **`QPixmap` only on main thread.** Workers emit `bytes` or `QImage`; slot calls `QPixmap.fromImage()`.
2. **`_live_workers: set` on every page** — add before `.start()`, discard via `finished` signal callback. Prevents Python GC destroying a running QThread.
3. **Signal disconnect before worker replacement.** Disconnect `finished`/`failed` before assigning a new worker. Park still-running workers in `_live_workers` first.
4. **No blocking `wait()` on main thread.** Call `worker.cancel()` + disconnect signals; thread finishes naturally.
5. **`QTimer.singleShot(0, fn)` from `threading.Thread` is unreliable.** Use a proper `QThread` with a `Signal` instead.

---

## MediaPage — Photos & Videos

**Package:** `src/gui/pages/media/`

| File | Class | Responsibility |
|---|---|---|
| `_utils.py` | — | Constants (`THUMB_SIZE=155`, `ITEM_SIZE=162`) + pure helpers |
| `workers.py` | 6 workers | `ListDirWorker`, `ThumbnailWorker`, `PhotoDecodeWorker`, `DownloadOpenWorker`, `ExportWorker`, `ScanWorker` |
| `widgets.py` | `GripSplitter`, `PhotoPopout` | Custom splitter; floating photo viewer with prev/next nav |
| `preview_panel.py` | `PreviewPanel` | Photo/video preview, EXIF, pop-out trigger |
| `page.py` | `MediaPage` | Orchestrator — wires everything via signals |

### Key behaviours
- Thumbnail grid: `ITEM_SIZE=162`, `setSpacing(2)` — tight layout, folders first, lazy-loaded.
- MEDIA section label auto-hides when grid panel < 120 px (`_on_splitter_moved`).
- Arrow-key debounce: `QTimer(400ms, singleShot=True)`. Preview loads only after 400 ms pause.
- Preview cleared on folder switch; `PhotoPopout` supports arrow-key prev/next.
- **`PhotoPopout._live_workers`**: critical — keeps running `PhotoDecodeWorker` refs alive when navigating quickly. Without this, Python GC destroys the running thread → app crash.

---

## FilesPage — AFC File Browser

**Package:** `src/gui/pages/files/`

> ⚠️ **Not manually tested against a real device.**

| File | Class | Responsibility |
|---|---|---|
| `workers.py` | 6 workers | `ListDirWorker`, `DownloadWorker`, `UploadWorker`, `DeleteWorker`, `RenameWorker`, `MkdirWorker` |
| `breadcrumb.py` | `BreadcrumbBar` | **Reusable** clickable path bar — emits `path_selected(str)` |
| `file_table.py` | `FileTableWidget` | **Reusable** sortable table — emits `entry_activated(dict)`, `selection_changed(object)` |
| `action_bar.py` | `ActionBar` | Upload/Download/Delete/Rename/New Folder buttons; `set_state()` API |
| `page.py` | `FilesPage` | Thin orchestrator |

### Verification checklist (needs device)
- [ ] Navigate to `/` root — folders listed correctly
- [ ] Double-click folder → navigate in; Up button goes back
- [ ] Breadcrumb segment click jumps to correct ancestor (stack rebuilt correctly)
- [ ] Upload a file, verify it appears in the list
- [ ] Download a file, verify it saves correctly
- [ ] Delete a file/folder with confirmation, verify it's removed
- [ ] Rename a file, verify new name appears
- [ ] New Folder, verify it appears
- [ ] Navigate away during list load — no crash
- [ ] Connect → disconnect → reconnect — page resets cleanly

### Known limitations
- AFC only exposes user-accessible paths (DCIM, Media, Documents, etc.)
- Download loads full file into RAM before writing — no streaming for large files

---

## BackupRestorePage — Backup & Restore

**Package:** `src/gui/pages/backup_restore/`

> ⚠️ **Not manually tested against a real device.**

| File | Class | Responsibility |
|---|---|---|
| `workers.py` | 4 workers | `ListBackupsWorker` (filesystem), `DeleteBackupWorker`, `BackupWorker`, `RestoreWorker` |
| `backup_table.py` | `BackupTableWidget` | Sortable local backup list; loads without device; `selection_changed(Path\|None)` |
| `output_log.py` | `OutputLog` | Streaming `QPlainTextEdit` + determinate `QProgressBar`; `append_line/set_progress/clear` |
| `action_bar.py` | `ActionBar` | 4 buttons; Cancel styled red when busy; `set_state()` API |
| `page.py` | `BackupRestorePage` | Thin orchestrator; `GripSplitter` between table and log |

### Key design decisions
- `BackupWorker`/`RestoreWorker` own `subprocess.Popen` directly (not via `run_streaming()`) so `cancel()` can call `proc.terminate()`
- Terminal `backup.py` helpers replicated locally to avoid loading Rich at GUI import time
- Backup directory: `~/iphone_backups/<UDID>/`
- Progress extracted via regex `\d{1,3}(?:\.\d+)?%` from each `idevicebackup2` output line
- Backup list visible even without a device — `show_no_device()` still calls `_load_backups()`
- Restore shows prominent warning dialog with red confirm button

### Verification checklist (needs device)
- [ ] Without device: backup list shows existing `~/iphone_backups/` entries (or placeholder)
- [ ] Without device: New Backup / Restore disabled; Delete enabled if row selected
- [ ] Connect device → New Backup → output log streams in real time → progress bar advances
- [ ] Cancel mid-backup → process terminates within seconds → buttons re-enable
- [ ] Select backup row → Restore → confirmation dialog shows → red confirm button → restore streams
- [ ] Delete backup → confirmation → row removed from table, directory deleted on disk
- [ ] Navigate away during backup → operation cancelled cleanly, no crash
- [ ] Disconnect mid-backup → `abort_all()` fires → no crash

---

## DiagnosticsPage — 3uTools-style layout

**File:** `src/gui/pages/diagnostics_page.py`

- Left: 4 categorised `QTableWidget`s (Identity, Hardware, Connectivity, Battery & Storage)
- Right: 5 `_StatusCard` widgets (Activation, iCloud Lock, Find My, Passcode, Developer Mode)
- Right bottom: Live screenshot panel (auto 4 s refresh; gracefully degrades without Developer Mode)

---

## DeviceInfo (`src/device/info.py`)

- `find_my_locked`: parsed from `NonVolatileRAM` multiline block; base64-decoded "YES"/"NO".
- `chip_id_hex`: computed property — decimal chip ID to `0xXXXX` hex.
- `icloud_locked`: True if `activation_state` is not "Activated".

---

## Screenshot / Mirror Constraints

- `com.apple.mobile.screenshotr` requires Developer Mode on iOS 16+. No workaround.
- Mirror: live frame stream backend still pending (Milestone 7).
- Developer Mode: Settings → Privacy & Security → Developer Mode → On → restart.

---

## Pending Milestones (GUI)

| Milestone | Page | Status |
|---|---|---|
| 5 | Files | ✅ Code complete — ⚠️ needs device verification |
| 6 | Backup & Restore | ✅ Code complete — ⚠️ needs device verification |
| 7 | Screen Mirror | Not started — needs Developer Mode on iOS 16+ |

**Other open items:**
- Video thumbnail without full download (partial AFC read or on-device frame extraction)
- Suppress OpenCV ffmpeg stderr noise
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
        media/                  ← SRP package (6 files) ✅ tested
        files/                  ← SRP package (6 files) ⚠️ needs verification
        backup_restore/         ← SRP package (6 files) ⚠️ needs verification
      widgets/
        device_header.py
    device/
      detector.py
      info.py          ← DeviceInfo dataclass + fetcher
    terminal/
      features/        ← shared feature modules
    utils/
      platform.py      ← find_tool() for libimobiledevice binaries
      runner.py        ← run_streaming() for subprocess output
```

## Branch Strategy

`master` — full codebase  
`feature-desktop-ui` — active GUI development (current, ahead of master)

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
