# iphone-experiments

Cross-platform iPhone management tool with both a terminal CLI and a full PySide6 desktop GUI.
The desktop roadmap is now centered on USB-based iPhone troubleshooting and recovery.

## Workspace Status

- Active workspace path: `C:\Workspace\Personal\iphone-experiments`
- Active repository: `iphone-experiments`
- Active development branch: `feature-troubleshoot-page`
- Old mistaken workspace copy under `C:\Workspace\Personal\iphone-storage-explorer\iphone-experiments` is no longer active and has been removed.

## Agent Handoff

- Source of truth: this repo and this workspace path
- Branch to continue on by default: `feature-troubleshoot-page`
- Current troubleshooting milestone (2026-04-16):
  - The desktop app is now explicitly positioned as a USB-based iPhone troubleshooting and recovery tool
  - `TroubleshootPage` has been added near the top of the sidebar as a dedicated diagnosis surface
  - `TroubleshootService` builds reusable snapshots, issue cards, health summaries, and recommended action shortcuts
  - Current issue coverage: no device, blocked device info / likely trust-unlock required, low storage, backup risk, developer mode off, screenshot readiness, mirror readiness, and missing critical tools
  - Troubleshoot actions route into existing desktop pages like Files, Photos & Videos, Backup & Restore, Screenshot, Diagnostics, and Settings
- Latest completed work (2026-04-12):
  - **DiagnosticsPage** fully redesigned — 3uTools-style layout with 4 categorised info tables (Identity, Hardware, Connectivity, Battery) + 5 status cards (Activation, iCloud Lock, Find My, Passcode, Developer Mode) + live screenshot panel
  - **DeviceInfo** extended with 15+ new fields: IMEI, IMEI2, MEID, ICCID, phone number, model number, hardware model, board ID, chip ID (hex), die ID, baseband, firmware, MLB serial, Find My lock (from NVRAM), passcode status, developer mode, battery external/full states
  - **MediaPage** preview pane overhauled: resizable via QSplitter, pop-out floating window (`_PhotoPopout`), full-resolution photo preview (HEIC decoded via `_PhotoDecodeWorker` on background thread), EXIF metadata display
  - Device polling split into two paths: new-device → full reset; same-device periodic → header/dashboard only (media/apps pages no longer reset every 15 s)
  - Screenshot service gracefully degrades to "Requires Developer Mode" message on iOS 16+ (no loop / stderr flooding)
  - Previous sessions: desktop branding/icon, system tray with notifications, lazy thumbnail loading, video preview with in-app player, `abort_all()` on every page, QThread crash fixes, concurrent AFC stat calls (~8x speedup)
- Highest-priority known gap:
  - video thumbnails still require downloading the full file (no partial/frame extraction yet)
- Major desktop pages still pending:
  - Milestone 5: Files (AFC browser — upload/download/delete/rename)
  - Milestone 6: Backup & Restore (streaming output, progress bar)
  - Milestone 7: Screen Mirror (PySide6 port + live frame stream, needs Developer Mode)

## Entry Points

| Mode | Command |
|---|---|
| Terminal CLI | `python main.py` |
| Desktop GUI | `python desktop.py` |

## Desktop GUI Features

- Desktop app icon with permanent Windows `.ico` asset in `assets/`
- System tray integration with device connect/disconnect notifications
- Battery and storage status notifications for the connected device
- Live device detection and auto-connect (polls every 2.5 s)
- Troubleshoot â€” health banner, issue cards, recommended actions, and compact technical status
- Dashboard — battery, storage, connectivity cards
- Diagnostics — 3uTools-style layout:
  - Device Identity table (name, model, iOS, build, serial, UDID, IMEI/IMEI2/MEID, ICCID, phone number, region, color)
  - Hardware table (CPU arch, platform, board ID, chip ID hex, die ID, baseband, firmware, MLB serial)
  - Connectivity table (WiFi, Bluetooth, Ethernet MAC)
  - Battery & Storage table (level, charge status, plugged, total/used/free)
  - Status cards with green/red/grey dot indicators: Activation, iCloud Lock, Find My, Passcode, Developer Mode
  - Live screenshot panel (auto-refreshes every 4 s; shows "Requires Developer Mode" when unavailable on iOS 16+)
- Screenshot — capture and preview in-app
- Apps — list user/system apps, install `.ipa`, uninstall
- Photos & Videos — full media browser:
  - Viewport-aware lazy loading (visible items first)
  - HEIC thumbnail and full-resolution support via pillow-heif
  - Resizable preview pane via QSplitter drag handle
  - Pop-out floating photo window with Fit/Full-Size toggle
  - Full-resolution photo preview with EXIF metadata (dimensions, date)
  - Video preview with built-in player (play/pause/seek)
  - Video thumbnails via OpenCV (generated on first preview)
  - Concurrent AFC stat calls for fast folder listing
  - Thumbnail JPEG cache in `%TEMP%\iphone_explorer\`
  - Export selected / all / all subfolders

## Terminal CLI Features

- Device dashboard (Rich)
- File browsing and transfer via AFC
- App listing, install, uninstall
- Photo/video export from DCIM
- Backup and restore
- Diagnostics, reboot, shutdown
- Screenshot capture
- Device rename
- Screen mirror scaffold with automated setup

## Tech Stack

- Python 3.12
- PySide6 — desktop GUI
- Rich — terminal UI
- `pymobiledevice3` — AFC, device services
- `libimobiledevice` CLI tools
- pillow-heif — HEIC image decoding
- opencv-python-headless — video frame extraction

## Project Structure

```text
iphone-experiments/
  main.py              ← terminal entry point
  desktop.py           ← GUI entry point
  requirements.txt
  src/
    gui/
      main_window.py
      pages/           ← one file per page
      widgets/
    device/
    terminal/
      features/        ← shared with terminal app
    utils/
  scripts/debug/
```

## Run Locally

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the desktop GUI:

```powershell
python desktop.py
```

Run the terminal CLI:

```powershell
python main.py
```

## Requirements

You need working iPhone communication on the host machine:

- Apple device drivers / iTunes or Apple Devices support on Windows
- `libimobiledevice` tools available in `PATH` or under `~/libimobiledevice`
- trusted USB connection between PC and iPhone

For screenshot and mirroring-related developer services, you may also need:

- Developer Mode enabled on the iPhone
- Developer Disk Image mounted
- remote tunnel started for modern iOS versions

## Branch Layout

`master` contains the full working codebase.

Current active branch for ongoing troubleshooting GUI work:

- `feature-troubleshoot-page`

Feature branches are available for grouped areas of the project:

- `feature-desktop-ui`
- `feature-troubleshoot-page`
- `feature-files`
- `feature-apps`
- `feature-media`
- `feature-backup`
- `feature-diagnostics`
- `feature-screenshot`
- `feature-rename`
- `feature-mirror`
- `feature-device`
- `feature-ui`
- `feature-utils`

## Notes

- `scripts/debug/` contains troubleshooting PowerShell scripts used during development.
- The screen mirror window is currently a setup and orchestration scaffold. The live frame rendering backend is still to be integrated.
- Desktop branding assets live under `assets/app-icon.svg`, `assets/app-icon.png`, and `assets/app-icon.ico`.
