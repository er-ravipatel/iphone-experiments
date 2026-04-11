# iphone-experiments

Cross-platform iPhone management experiments built around a terminal-first workflow.

This project is a Python CLI application inspired by desktop iPhone utility tools. It detects a connected iPhone, shows device information in the terminal, and exposes interactive actions for file browsing, app management, media export, backup and restore, diagnostics, screenshots, device rename, and a screen mirror workflow scaffold.

## Current Features

- Detect connected iPhones over USB
- Show dashboard with model, iOS version, battery, and storage
- Browse device files using AFC via `pymobiledevice3`
- List, install, and uninstall apps
- Export photos and videos from `DCIM`
- Create and restore device backups
- Run reboot and shutdown diagnostics
- Capture screenshots when developer services are available
- Rename the connected device
- Open a dedicated screen mirror window scaffold with automated setup actions

## Tech Stack

- Python 3.12
- Rich for terminal UI
- `libimobiledevice` CLI tools
- `pymobiledevice3` for modern device services and AFC access
- Tkinter for the mirror viewer scaffold

## Project Structure

```text
iphone-experiments/
  main.py
  requirements.txt
  src/
    device/
    features/
    ui/
    utils/
  scripts/
    debug/
```

## Run Locally

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the app:

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

Feature branches are available for grouped areas of the project:

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
