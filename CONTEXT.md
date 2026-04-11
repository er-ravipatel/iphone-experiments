# Project Context

## Goal

This repository explores a terminal-first iPhone management tool for Windows and other desktop platforms. The main direction is to keep the terminal app as the control center while using separate windows only when a richer visual surface is required, such as screen mirroring.

## Current Product Shape

The app starts in the terminal, detects a connected iPhone, renders a dashboard, and presents an interactive menu.

Implemented feature areas:

- device detection
- device information parsing
- dashboard and terminal navigation
- file transfer and browsing
- app management
- media export
- backup and restore
- diagnostics
- screenshot support
- rename support
- mirror window scaffold

## Main Runtime Flow

`main.py` is the entry point.

High-level flow:

1. prepare terminal encoding and PATH
2. verify core tools exist
3. poll for a connected device
4. fetch device info
5. render dashboard and interactive menu
6. dispatch to feature modules

## Important Modules

### `src/device`

- `detector.py`
  Detects connected devices using `idevice_id`
- `info.py`
  Builds a `DeviceInfo` object from `ideviceinfo` and `pymobiledevice3`

### `src/utils`

- `platform.py`
  Finds required tools and returns install instructions
- `runner.py`
  Common subprocess wrapper for CLI tool execution

### `src/ui`

- `dashboard.py`
  Rich dashboard for connected device state
- `menu.py`
  Interactive prompts, menu rendering, shared formatting helpers
- `progress.py`
  Spinners, progress bars, and live streaming output helpers

### `src/features`

- `files.py`
  AFC-based file browsing and transfers
- `apps.py`
  App listing, install, uninstall
- `media.py`
  Photo and video export from `DCIM`
- `backup.py`
  Backup and restore orchestration
- `diagnostics.py`
  Full diagnostics, reboot, shutdown
- `screenshot.py`
  Screenshot capture and developer-service error handling
- `rename.py`
  Rename the device
- `mirror.py`
  Dedicated mirror window scaffold with setup automation

## Storage Behavior

Storage values are taken from the `com.apple.disk_usage` domain.

Important detail:

- total device capacity is displayed using decimal GB
- free space uses `AmountDataAvailable`
- earlier misleading keys like `TotalDataAvailable` should not be used for user-visible free space

## Screenshot and Mirror Constraints

Current limitation:

- screenshot and mirror-related developer services are blocked unless Developer Mode is enabled and the Developer Disk Image is mounted

Mirror setup direction:

- use `pymobiledevice3` rather than the unstable Windows `ideviceimagemounter.exe` path
- support auto-mount and remote tunnel setup from the app
- later connect a real live frame stream into the mirror viewer

## Mirror Window Status

The current mirror window is not a full live mirroring implementation yet.

What it already does:

- opens as a separate application window
- shows connected device metadata
- checks developer mode state
- checks screenshot/developer service readiness
- automates DDI mount attempts
- automates tunnel start/stop attempts
- shows live setup logs

What is still pending:

- actual video/frame streaming backend
- rendering the live iPhone display into the viewer area

## Repo Organization

Top-level source:

- `main.py`
- `requirements.txt`
- `src/`

Development artifacts:

- `scripts/debug/`

## Branch Strategy

`master` contains the complete codebase snapshot.

Feature branches currently represent project areas and were created from the same baseline:

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

## Next Good Steps

- connect the mirror window to a real live stream backend
- improve developer-mode detection and setup messaging
- reduce encoding artifacts in some terminal strings
- add tests for storage parsing and runner behavior
- optionally split feature branches into feature-specific change history instead of baseline copies
