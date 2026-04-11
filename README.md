# iphone-experiments

Cross-platform iPhone management tool with both a terminal CLI and a full PySide6 desktop GUI.

## Workspace Status

- Active workspace path: `C:\Workspace\Personal\iphone-experiments`
- Active repository: `iphone-experiments`
- Active development branch: `feature-desktop-ui`
- Old mistaken workspace copy under `C:\Workspace\Personal\iphone-storage-explorer\iphone-experiments` is no longer active and has been removed.

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
- Dashboard — battery, storage, connectivity cards
- Diagnostics — full device info table
- Screenshot — capture and preview in-app
- Apps — list user/system apps, install `.ipa`, uninstall
- Photos & Videos — thumbnail grid browser with:
  - Viewport-aware lazy loading (visible items first)
  - HEIC thumbnail support via pillow-heif
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

Current active branch for ongoing GUI work:

- `feature-desktop-ui`

Feature branches are available for grouped areas of the project:

- `feature-desktop-ui`
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
