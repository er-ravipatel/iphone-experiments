"""
Recovery mode assistant service.

Provides guidance-first recovery mode information and only best-effort state
inspection. It never attempts bypass-style actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..core.results import ServiceResult
from ..device.info import DeviceInfo
from ..utils.platform import check_tools
from ..utils.runner import run


class RecoveryModeState(str, Enum):
    NORMAL = "normal"
    RECOVERY = "recovery"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryStep:
    title: str
    detail: str


@dataclass(frozen=True)
class DeviceRecoveryProfile:
    family: str
    summary: str
    buttons: str


@dataclass
class RecoveryDetectionSnapshot:
    state: RecoveryModeState = RecoveryModeState.UNKNOWN
    state_label: str = "Unknown"
    state_detail: str = ""
    device_name: str = ""
    device_model: str = ""
    ios_version: str = ""
    profile: DeviceRecoveryProfile = field(
        default_factory=lambda: DeviceRecoveryProfile(
            family="Generic iPhone",
            summary="Recovery steps depend on your button layout.",
            buttons="Unknown",
        )
    )
    steps: list[RecoveryStep] = field(default_factory=list)
    restore_warnings: list[str] = field(default_factory=list)


class RecoveryModeService:
    def get_recovery_snapshot(
        self,
        info: DeviceInfo | None = None,
    ) -> ServiceResult[RecoveryDetectionSnapshot]:
        profile = self.get_recovery_profile(info).data
        detection = self.detect_recovery_mode()
        state = detection.data if detection.success and detection.data else RecoveryModeState.UNKNOWN
        snapshot = RecoveryDetectionSnapshot(
            state=state,
            state_label=self._state_label(state),
            state_detail=self._state_detail(state),
            device_name=info.name if info else "",
            device_model=info.model if info else "",
            ios_version=info.ios_version if info else "",
            profile=profile,
            steps=self.get_recovery_steps(info).data or [],
            restore_warnings=self.get_restore_warnings(info).data or [],
        )
        return ServiceResult(success=True, data=snapshot)

    def get_recovery_profile(self, info: DeviceInfo | None = None) -> ServiceResult[DeviceRecoveryProfile]:
        model = (info.model if info else "").lower()
        if "iphone se" in model or "iphone 8" in model or "iphone 7" in model:
            return ServiceResult(
                success=True,
                data=DeviceRecoveryProfile(
                    family="Home or Touch ID-era iPhone",
                    summary="Use the side/top button and any present Home-style controls to enter recovery mode.",
                    buttons="Home/Touch ID era",
                ),
            )
        if model:
            return ServiceResult(
                success=True,
                data=DeviceRecoveryProfile(
                    family="Face ID iPhone",
                    summary="Use the volume buttons first, then hold the side button until the recovery screen appears.",
                    buttons="Volume Up, Volume Down, then hold Side button",
                ),
            )
        return ServiceResult(
            success=True,
            data=DeviceRecoveryProfile(
                family="Generic iPhone",
                summary="Recovery mode steps differ slightly by button family.",
                buttons="Model-specific",
            ),
        )

    def get_recovery_steps(self, info: DeviceInfo | None = None) -> ServiceResult[list[RecoveryStep]]:
        profile = self.get_recovery_profile(info).data
        if profile.family == "Face ID iPhone":
            steps = [
                RecoveryStep("Turn off the iPhone if possible", "Use the normal power-off flow first if the iPhone still responds."),
                RecoveryStep("Connect the USB cable to the computer", "Keep the cable ready so the device stays connected during recovery."),
                RecoveryStep("Press Volume Up, then Volume Down", "Use a quick press for each button in sequence."),
                RecoveryStep("Hold the Side button", "Keep holding until the recovery-mode screen appears, even if the Apple logo shows first."),
            ]
        else:
            steps = [
                RecoveryStep("Turn off the iPhone if possible", "If the device still responds, power it down first."),
                RecoveryStep("Connect the USB cable to the computer", "Keep the cable connected throughout the process."),
                RecoveryStep("Hold the recovery button combination", "Older/Home-button devices usually rely on the Home or side/top button while connecting."),
                RecoveryStep("Wait for the recovery-mode screen", "Release only when the computer/recovery screen appears."),
            ]
        return ServiceResult(success=True, data=steps)

    def detect_recovery_mode(self) -> ServiceResult[RecoveryModeState]:
        tools = check_tools()
        if tools.get("ideviceinfo") is None:
            return ServiceResult(success=True, data=RecoveryModeState.UNKNOWN)
        try:
            result = run("ideviceinfo", timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return ServiceResult(success=True, data=RecoveryModeState.NORMAL)
            detail = (result.stdout + "\n" + result.stderr).lower()
            if "recovery" in detail:
                return ServiceResult(success=True, data=RecoveryModeState.RECOVERY)
            return ServiceResult(success=True, data=RecoveryModeState.UNKNOWN)
        except Exception:
            return ServiceResult(success=True, data=RecoveryModeState.UNKNOWN)

    def get_restore_warnings(self, info: DeviceInfo | None = None) -> ServiceResult[list[str]]:
        warnings = [
            "Update tries to reinstall iOS without erasing where supported, but it can still fail and require a full restore.",
            "Restore erases the iPhone and removes the forgotten device passcode by resetting the device.",
            "After restore, Activation Lock can still require the Apple Account that was previously signed in.",
            "Use a stable cable, keep the iPhone connected, and avoid interrupting the process once it starts.",
        ]
        if info is not None:
            warnings.insert(
                0,
                f"Prepare recovery for {info.name} ({info.model}) running iOS {info.ios_version}.",
            )
        return ServiceResult(success=True, data=warnings)

    @staticmethod
    def _state_label(state: RecoveryModeState) -> str:
        if state == RecoveryModeState.NORMAL:
            return "Normal Mode"
        if state == RecoveryModeState.RECOVERY:
            return "Recovery Mode"
        return "Unknown"

    @staticmethod
    def _state_detail(state: RecoveryModeState) -> str:
        if state == RecoveryModeState.NORMAL:
            return "The device appears reachable in normal USB mode right now."
        if state == RecoveryModeState.RECOVERY:
            return "The device appears to be in recovery mode or restore preparation state."
        return "Recovery-mode detection is best-effort in this build and may be unavailable on some setups."
