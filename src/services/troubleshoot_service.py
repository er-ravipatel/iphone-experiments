"""
Troubleshoot service.

Builds a structured snapshot of the current device/app state and derives
actionable troubleshooting issues for the desktop UI.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..core.results import ServiceResult
from ..device.info import DeviceInfo
from ..utils.platform import check_tools
from ..utils.runner import run


class TroubleshootSeverity(str, Enum):
    HEALTHY = "healthy"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TroubleshootAction(str, Enum):
    REFRESH = "refresh"
    OPEN_FILES = "open_files"
    OPEN_MEDIA = "open_media"
    OPEN_BACKUP = "open_backup"
    OPEN_SCREENSHOT = "open_screenshot"
    OPEN_DIAGNOSTICS = "open_diagnostics"
    OPEN_SETTINGS = "open_settings"
    OPEN_PASSCODE_RECOVERY = "open_passcode_recovery"
    OPEN_RECOVERY_MODE = "open_recovery_mode"


@dataclass(frozen=True)
class TroubleshootIssue:
    id: str
    title: str
    severity: TroubleshootSeverity
    summary: str
    details: str = ""
    recommended_action: TroubleshootAction = TroubleshootAction.REFRESH
    action_label: str = "Refresh"
    page_target: str = ""
    is_blocking: bool = False


@dataclass(frozen=True)
class RecommendedAction:
    id: TroubleshootAction
    label: str
    description: str = ""


@dataclass
class TroubleshootSnapshot:
    connected: bool = False
    device_detected: bool = False
    device_info_available: bool = False
    device_name: str = ""
    device_model: str = ""
    battery_level: int | None = None
    free_storage_gb: float | None = None
    total_storage_gb: float | None = None
    developer_mode: bool | None = None
    screenshot_status: str = "Unknown"
    screenshot_detail: str = ""
    mirror_status: str = "Unknown"
    mirror_detail: str = ""
    info_error: str = ""
    critical_tools_missing: list[str] = field(default_factory=list)
    issues: list[TroubleshootIssue] = field(default_factory=list)
    recommended_actions: list[RecommendedAction] = field(default_factory=list)
    overall_severity: TroubleshootSeverity = TroubleshootSeverity.INFO
    overall_status: str = "Attention Needed"
    overall_summary: str = ""


class TroubleshootService:
    _CRITICAL_TOOLS = {"idevice_id", "ideviceinfo"}

    def get_troubleshoot_snapshot(
        self,
        *,
        info: DeviceInfo | None = None,
        device_detected: bool = False,
        info_error: str = "",
    ) -> ServiceResult[TroubleshootSnapshot]:
        snapshot = TroubleshootSnapshot(
            connected=info is not None,
            device_detected=device_detected or info is not None,
            device_info_available=info is not None,
            info_error=info_error,
        )

        tools = check_tools()
        snapshot.critical_tools_missing = [
            name for name, path in tools.items()
            if path is None and name in self._CRITICAL_TOOLS
        ]

        if info is not None:
            snapshot.device_name = info.name
            snapshot.device_model = info.model
            snapshot.battery_level = info.battery_level
            snapshot.free_storage_gb = info.free_storage_gb
            snapshot.total_storage_gb = info.total_storage_gb
            snapshot.developer_mode = info.developer_mode
            snap_status, snap_detail = self._probe_screenshot_service(info.udid, info.developer_mode)
            snapshot.screenshot_status = snap_status
            snapshot.screenshot_detail = snap_detail
            mirror_status, mirror_detail = self._derive_mirror_status(info.developer_mode, snap_status, snap_detail)
            snapshot.mirror_status = mirror_status
            snapshot.mirror_detail = mirror_detail

        snapshot.issues = self.get_troubleshoot_issues(snapshot)
        snapshot.recommended_actions = self.get_recommended_actions(snapshot.issues)
        snapshot.overall_severity = self._overall_severity(snapshot.issues)
        snapshot.overall_status = self._overall_status(snapshot.overall_severity)
        snapshot.overall_summary = self._overall_summary(snapshot)

        return ServiceResult(success=True, data=snapshot)

    def get_troubleshoot_issues(self, snapshot: TroubleshootSnapshot) -> list[TroubleshootIssue]:
        issues: list[TroubleshootIssue] = []

        if snapshot.critical_tools_missing:
            missing = ", ".join(snapshot.critical_tools_missing)
            issues.append(
                TroubleshootIssue(
                    id="missing_tools",
                    title="Critical tools are missing",
                    severity=TroubleshootSeverity.CRITICAL,
                    summary="The app cannot fully communicate with the iPhone until core tools are available.",
                    details=f"Missing critical tools: {missing}. Configure the tools path in Settings or install libimobiledevice.",
                    recommended_action=TroubleshootAction.OPEN_SETTINGS,
                    action_label="Open Settings",
                    page_target="settings",
                    is_blocking=True,
                )
            )

        if not snapshot.device_detected:
            issues.append(
                TroubleshootIssue(
                    id="no_device",
                    title="No iPhone detected over USB",
                    severity=TroubleshootSeverity.CRITICAL,
                    summary="Connect the iPhone with USB and unlock it so the app can inspect it.",
                    details="Check the cable, unlock the phone, and make sure Apple device drivers are installed.",
                    recommended_action=TroubleshootAction.REFRESH,
                    action_label="Refresh",
                    is_blocking=True,
                )
            )
            return issues

        if snapshot.device_detected and not snapshot.device_info_available:
            issues.append(
                TroubleshootIssue(
                    id="device_info_unavailable",
                    title="Device detected but details could not be read",
                    severity=TroubleshootSeverity.CRITICAL,
                    summary="This usually means the iPhone is locked or waiting for the Trust prompt.",
                    details=snapshot.info_error or "Unlock the iPhone and tap Trust if prompted, then refresh.",
                    recommended_action=TroubleshootAction.OPEN_PASSCODE_RECOVERY,
                    action_label="Open Passcode Recovery",
                    is_blocking=True,
                )
            )
            issues.append(
                TroubleshootIssue(
                    id="trust_unlock",
                    title="Trust / unlock likely required",
                    severity=TroubleshootSeverity.WARNING,
                    summary="USB communication is limited until the device is unlocked and trusted.",
                    details="Look at the iPhone screen for a passcode prompt or a 'Trust This Computer' alert.",
                    recommended_action=TroubleshootAction.OPEN_PASSCODE_RECOVERY,
                    action_label="Open Passcode Recovery",
                    page_target="passcode_recovery",
                )
            )
            return issues

        if snapshot.free_storage_gb is not None:
            if snapshot.free_storage_gb < 5:
                issues.append(
                    TroubleshootIssue(
                        id="critical_storage",
                        title="Very low free storage",
                        severity=TroubleshootSeverity.CRITICAL,
                        summary=f"Only {snapshot.free_storage_gb:.1f} GB is free on the device.",
                        details="Low free space can break backups, app installs, screenshots, and media operations.",
                        recommended_action=TroubleshootAction.OPEN_MEDIA,
                        action_label="Open Photos & Videos",
                        page_target="media",
                    )
                )
            elif snapshot.free_storage_gb < 10:
                issues.append(
                    TroubleshootIssue(
                        id="low_storage",
                        title="Free storage is running low",
                        severity=TroubleshootSeverity.WARNING,
                        summary=f"{snapshot.free_storage_gb:.1f} GB free remains on the device.",
                        details="Consider exporting photos/videos or cleaning accessible files before other maintenance tasks.",
                        recommended_action=TroubleshootAction.OPEN_MEDIA,
                        action_label="Open Photos & Videos",
                        page_target="media",
                    )
                )

            if snapshot.free_storage_gb < 10:
                issues.append(
                    TroubleshootIssue(
                        id="backup_risk",
                        title="Backup risk due to low free space",
                        severity=TroubleshootSeverity.WARNING,
                        summary="Backups and restore preparation may fail or become unstable when storage is very low.",
                        details="Create a backup soon if possible, but prioritize reducing storage pressure first if operations fail.",
                        recommended_action=TroubleshootAction.OPEN_BACKUP,
                        action_label="Open Backup & Restore",
                        page_target="backup",
                    )
                )

        if snapshot.developer_mode is False:
            issues.append(
                TroubleshootIssue(
                    id="developer_mode_off",
                    title="Developer Mode is off or unavailable",
                    severity=TroubleshootSeverity.WARNING,
                    summary="Screenshot and mirror workflows need developer services on modern iOS versions.",
                    details="Enable Developer Mode on the iPhone if you want to use screenshot or screen mirror features.",
                    recommended_action=TroubleshootAction.OPEN_SCREENSHOT,
                    action_label="Open Screenshot",
                    page_target="screenshot",
                )
            )

        if snapshot.screenshot_status != "Ready":
            issues.append(
                TroubleshootIssue(
                    id="screenshot_not_ready",
                    title="Screenshot service is not ready",
                    severity=TroubleshootSeverity.WARNING,
                    summary=snapshot.screenshot_detail or "The screenshot service could not be reached.",
                    details="Developer services may need Developer Mode, a mounted developer image, or a trusted USB session.",
                    recommended_action=TroubleshootAction.OPEN_SCREENSHOT,
                    action_label="Open Screenshot",
                    page_target="screenshot",
                )
            )

        if snapshot.mirror_status != "Ready":
            issues.append(
                TroubleshootIssue(
                    id="mirror_not_ready",
                    title="Screen mirror is not ready",
                    severity=TroubleshootSeverity.WARNING,
                    summary=snapshot.mirror_detail or "Mirror setup is incomplete.",
                    details="The dedicated desktop Screen Mirror page is still pending, so treat this as a setup/readiness check.",
                    recommended_action=TroubleshootAction.OPEN_SETTINGS,
                    action_label="Open Settings",
                    page_target="settings",
                )
            )

        return issues

    def get_recommended_actions(self, issues: list[TroubleshootIssue]) -> list[RecommendedAction]:
        ordered: list[RecommendedAction] = []
        seen: set[TroubleshootAction] = set()

        for issue in issues:
            action = issue.recommended_action
            if action in seen:
                continue
            ordered.append(
                RecommendedAction(
                    id=action,
                    label=issue.action_label,
                    description=issue.title,
                )
            )
            seen.add(action)
            if len(ordered) >= 4:
                break

        if not ordered:
            ordered.append(
                RecommendedAction(
                    id=TroubleshootAction.OPEN_DIAGNOSTICS,
                    label="Open Diagnostics",
                    description="Review detailed device status",
                )
            )

        return ordered

    def _probe_screenshot_service(self, udid: str, developer_mode: bool) -> tuple[str, str]:
        if not developer_mode:
            return "Blocked", "Developer Mode is disabled."

        temp_path = Path(tempfile.gettempdir()) / "iphone_explorer_troubleshoot_probe.png"
        temp_path.unlink(missing_ok=True)
        result = run("idevicescreenshot", str(temp_path), udid=udid, timeout=20)
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
            return "Ready", "Screenshot service is reachable."

        detail = (result.stdout or result.stderr or "").strip()
        lowered = detail.lower()
        if "invalid service" in lowered:
            return "Blocked", "Developer Disk Image or tunnel setup is still missing."
        if "trust" in lowered or "locked" in lowered:
            return "Blocked", "The iPhone may need to be unlocked and trusted again."
        if "not found" in lowered:
            return "Unavailable", "idevicescreenshot is not available in PATH."
        return "Unknown", detail or "Could not probe screenshot service."

    def _derive_mirror_status(self, developer_mode: bool | None, screenshot_status: str, screenshot_detail: str) -> tuple[str, str]:
        if developer_mode is False:
            return "Blocked", "Developer Mode is disabled."
        if screenshot_status == "Ready":
            return "Ready", "Developer services look ready for advanced workflows."
        if screenshot_status == "Blocked":
            return "Blocked", screenshot_detail
        return "Unknown", "Mirror setup is not fully confirmed yet."

    @staticmethod
    def _overall_severity(issues: list[TroubleshootIssue]) -> TroubleshootSeverity:
        if any(issue.severity == TroubleshootSeverity.CRITICAL for issue in issues):
            return TroubleshootSeverity.CRITICAL
        if any(issue.severity == TroubleshootSeverity.WARNING for issue in issues):
            return TroubleshootSeverity.WARNING
        if issues:
            return TroubleshootSeverity.INFO
        return TroubleshootSeverity.HEALTHY

    @staticmethod
    def _overall_status(severity: TroubleshootSeverity) -> str:
        if severity == TroubleshootSeverity.CRITICAL:
            return "Critical Issues"
        if severity == TroubleshootSeverity.WARNING:
            return "Attention Needed"
        if severity == TroubleshootSeverity.INFO:
            return "Check Status"
        return "Healthy"

    @staticmethod
    def _overall_summary(snapshot: TroubleshootSnapshot) -> str:
        if not snapshot.device_detected:
            return "No device is available to diagnose right now."
        if snapshot.device_detected and not snapshot.device_info_available:
            return "A device was detected, but trusted USB access is still blocked."
        if not snapshot.issues:
            return "The connected iPhone looks healthy enough for routine backup, file, and media tasks."
        return f"{len(snapshot.issues)} issue(s) need attention before all desktop features will work reliably."
