"""
Passcode recovery service.

Builds guidance-oriented snapshots for passcode-related lockout situations.
This service never attempts bypass-style actions. It only helps the UI explain
safe recovery paths, local backup availability, and the next best step.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..core.results import ServiceResult
from ..device.info import DeviceInfo
from ..gui import settings
from ..gui.pages.backup_restore.workers import _dir_size_bytes, _list_local_backups


class PasscodeProblemType(str, Enum):
    DEVICE_PASSCODE = "device_passcode"
    SCREEN_TIME = "screen_time"
    RECENT_CHANGE = "recent_change"


class RecoveryPath(str, Enum):
    ERASE_AND_RESTORE = "erase_and_restore"
    APPLE_ACCOUNT_RESET = "apple_account_reset"
    PREVIOUS_PASSCODE_WINDOW = "previous_passcode_window"


@dataclass(frozen=True)
class BackupAvailability:
    has_backup: bool
    backup_count: int = 0
    latest_path: str = ""
    latest_date: str = ""
    latest_size: str = ""
    backup_root: str = ""


@dataclass(frozen=True)
class RecoveryStep:
    title: str
    detail: str
    emphasis: str = ""


@dataclass
class PasscodeRecoverySnapshot:
    problem_type: PasscodeProblemType
    recovery_path: RecoveryPath
    device_connected: bool = False
    device_info_available: bool = False
    device_name: str = ""
    device_model: str = ""
    ios_version: str = ""
    backup: BackupAvailability = field(
        default_factory=lambda: BackupAvailability(False)
    )
    summary: str = ""
    warning: str = ""
    notes: list[str] = field(default_factory=list)
    steps: list[RecoveryStep] = field(default_factory=list)


class PasscodeRecoveryService:
    def get_passcode_recovery_snapshot(
        self,
        problem_type: PasscodeProblemType,
        info: DeviceInfo | None = None,
    ) -> ServiceResult[PasscodeRecoverySnapshot]:
        backup = self.find_local_backups()
        backup_info = backup.data if backup.success and backup.data is not None else BackupAvailability(False)
        snapshot = PasscodeRecoverySnapshot(
            problem_type=problem_type,
            recovery_path=self._recovery_path(problem_type),
            device_connected=info is not None,
            device_info_available=info is not None,
            device_name=info.name if info else "",
            device_model=info.model if info else "",
            ios_version=info.ios_version if info else "",
            backup=backup_info,
        )
        snapshot.summary = self._summary(problem_type, snapshot)
        snapshot.warning = self._warning(problem_type, snapshot)
        snapshot.notes = self._notes(problem_type, snapshot)
        snapshot.steps = self.build_recovery_steps(problem_type, snapshot)
        return ServiceResult(success=True, data=snapshot)

    def find_local_backups(self) -> ServiceResult[BackupAvailability]:
        backup_root = settings.backup_dir()
        try:
            paths = _list_local_backups(backup_root)
            if not paths:
                return ServiceResult(
                    success=True,
                    data=BackupAvailability(
                        has_backup=False,
                        backup_count=0,
                        backup_root=backup_root,
                    ),
                )
            latest = paths[0]
            latest_stat = latest.stat()
            size_text = self._fmt_size(_dir_size_bytes(latest))
            return ServiceResult(
                success=True,
                data=BackupAvailability(
                    has_backup=True,
                    backup_count=len(paths),
                    latest_path=str(latest),
                    latest_date=self._fmt_mtime(latest_stat.st_mtime),
                    latest_size=size_text,
                    backup_root=backup_root,
                ),
            )
        except Exception as exc:
            return ServiceResult(success=False, error=str(exc))

    def build_recovery_steps(
        self,
        problem_type: PasscodeProblemType,
        snapshot: PasscodeRecoverySnapshot,
    ) -> list[RecoveryStep]:
        if problem_type == PasscodeProblemType.SCREEN_TIME:
            return [
                RecoveryStep(
                    "Open Screen Time settings",
                    "On the iPhone, go to Settings > Screen Time and choose the change/reset flow for the Screen Time passcode.",
                ),
                RecoveryStep(
                    "Use the Apple Account used for Screen Time",
                    "Apple supports resetting a forgotten Screen Time passcode with the Apple Account that was used when it was set up.",
                    emphasis="This is different from the device unlock passcode.",
                ),
                RecoveryStep(
                    "Only erase the iPhone if other recovery paths fail",
                    "A full erase is not the first-line path for Screen Time passcode issues.",
                ),
            ]

        if problem_type == PasscodeProblemType.RECENT_CHANGE:
            return [
                RecoveryStep(
                    "Try the previous-passcode recovery path",
                    "Recent iOS versions can allow the previous device passcode to unlock the iPhone within a short grace window after a passcode change.",
                    emphasis="This is Apple device behavior, not something the app performs.",
                ),
                RecoveryStep(
                    "Check the iPhone directly",
                    "If the device offers a 'Forgot Passcode?' or previous-passcode option on the lockout screen, follow the on-device instructions.",
                ),
                RecoveryStep(
                    "Prepare for erase and restore if the grace window has expired",
                    "If the old-passcode window is unavailable, the supported path becomes erase/reset and restore from backup if one exists.",
                ),
            ]

        return [
            RecoveryStep(
                "Do not keep guessing the device passcode",
                "Repeated failed attempts can lock the iPhone further and slow down the recovery process.",
            ),
            RecoveryStep(
                "Check backup availability first",
                "If a recent local backup exists, you can restore your data after the device is erased and set up again.",
                emphasis="No valid backup means current locked-device data may be lost during recovery.",
            ),
            RecoveryStep(
                "Use Recovery Mode to erase and restore",
                "A forgotten device passcode is recovered by erasing/resetting the iPhone, then restoring from backup if available.",
            ),
        ]

    @staticmethod
    def _recovery_path(problem_type: PasscodeProblemType) -> RecoveryPath:
        if problem_type == PasscodeProblemType.SCREEN_TIME:
            return RecoveryPath.APPLE_ACCOUNT_RESET
        if problem_type == PasscodeProblemType.RECENT_CHANGE:
            return RecoveryPath.PREVIOUS_PASSCODE_WINDOW
        return RecoveryPath.ERASE_AND_RESTORE

    @staticmethod
    def _summary(
        problem_type: PasscodeProblemType,
        snapshot: PasscodeRecoverySnapshot,
    ) -> str:
        if problem_type == PasscodeProblemType.SCREEN_TIME:
            return "Screen Time passcode issues usually use an Apple Account-based reset path instead of erasing the iPhone."
        if problem_type == PasscodeProblemType.RECENT_CHANGE:
            return "If the passcode was changed recently, the iPhone may still allow the previous passcode for a limited time."
        if snapshot.backup.has_backup:
            return "A forgotten device passcode is recovered by erasing the iPhone and restoring from a backup if one exists."
        return "A forgotten device passcode is recovered by erasing the iPhone. No local backup was found yet."

    @staticmethod
    def _warning(
        problem_type: PasscodeProblemType,
        snapshot: PasscodeRecoverySnapshot,
    ) -> str:
        if problem_type == PasscodeProblemType.SCREEN_TIME:
            return "Do not treat a Screen Time passcode problem like a full device passcode lockout."
        if problem_type == PasscodeProblemType.RECENT_CHANGE:
            return "The previous-passcode grace period is time-limited and handled on the iPhone itself."
        if snapshot.backup.has_backup:
            return "Erasing the iPhone removes the forgotten device passcode, but Activation Lock may still require the previous Apple Account afterwards."
        return "Erasing the iPhone removes the forgotten device passcode, but current on-device data cannot be preserved without a backup."

    @staticmethod
    def _notes(
        problem_type: PasscodeProblemType,
        snapshot: PasscodeRecoverySnapshot,
    ) -> list[str]:
        notes: list[str] = []
        if snapshot.device_connected:
            notes.append(
                f"Connected device: {snapshot.device_name or 'Unknown'}"
                + (f" ({snapshot.device_model})" if snapshot.device_model else "")
            )
        else:
            notes.append("No currently connected device is required to inspect local backups and prepare the recovery path.")
        if snapshot.backup.has_backup:
            notes.append(
                f"Latest local backup: {snapshot.backup.latest_date} | {snapshot.backup.latest_size}"
            )
        else:
            notes.append(f"No local backup was found under {snapshot.backup.backup_root}.")
        if problem_type == PasscodeProblemType.SCREEN_TIME:
            notes.append("Screen Time recovery is handled differently from device unlock passcode recovery.")
        elif problem_type == PasscodeProblemType.RECENT_CHANGE:
            notes.append("If the old-passcode grace window is unavailable, the supported fallback is erase and restore.")
        else:
            notes.append("This app does not bypass device passcodes. It only helps prepare the supported recovery path.")
        return notes

    @staticmethod
    def _fmt_size(n: int) -> str:
        if n < 1024 ** 2:
            return f"{n / 1024:.1f} KB"
        if n < 1024 ** 3:
            return f"{n / 1024 ** 2:.1f} MB"
        return f"{n / 1024 ** 3:.2f} GB"

    @staticmethod
    def _fmt_mtime(timestamp: float) -> str:
        from datetime import datetime

        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
