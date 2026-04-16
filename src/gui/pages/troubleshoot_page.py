"""
TroubleshootPage - guided issue detection and recovery routing.

This page stays presentation-focused. Snapshot collection and issue derivation
live in TroubleshootService so the logic remains reusable and testable.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.results import ServiceResult
from ...device.info import DeviceInfo
from ...services.troubleshoot_service import (
    RecommendedAction,
    TroubleshootIssue,
    TroubleshootService,
    TroubleshootSeverity,
    TroubleshootSnapshot,
)


class _TroubleshootWorker(QThread):
    finished: Signal = Signal(object)  # ServiceResult[TroubleshootSnapshot]

    def __init__(
        self,
        service: TroubleshootService,
        *,
        info: DeviceInfo | None = None,
        device_detected: bool = False,
        info_error: str = "",
    ) -> None:
        super().__init__()
        self._service = service
        self._info = info
        self._device_detected = device_detected
        self._info_error = info_error

    def run(self) -> None:
        result = self._service.get_troubleshoot_snapshot(
            info=self._info,
            device_detected=self._device_detected,
            info_error=self._info_error,
        )
        self.finished.emit(result)


class _SeverityBadge(QLabel):
    _STYLES = {
        TroubleshootSeverity.HEALTHY: ("Healthy", "#0b1f14", "#43a047", "#81c784"),
        TroubleshootSeverity.INFO: ("Info", "#131c24", "#2962ff", "#90caf9"),
        TroubleshootSeverity.WARNING: ("Warning", "#241700", "#fb8c00", "#ffcc80"),
        TroubleshootSeverity.CRITICAL: ("Critical", "#2a1111", "#e53935", "#ef9a9a"),
    }

    def __init__(self, severity: TroubleshootSeverity, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(76)
        self.set_severity(severity)

    def set_severity(self, severity: TroubleshootSeverity) -> None:
        label, bg, border, color = self._STYLES[severity]
        self.setText(label.upper())
        self.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; color: {color};"
            "border-radius: 10px; padding: 4px 10px; font-size: 10px; font-weight: bold;"
        )


class _IssueCard(QFrame):
    action_requested: Signal = Signal(str)

    def __init__(self, issue: TroubleshootIssue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._issue = issue
        self.setObjectName("Card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(4)

        title = QLabel(issue.title)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f0f0f0;")
        title_wrap.addWidget(title)

        summary = QLabel(issue.summary)
        summary.setWordWrap(True)
        summary.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        title_wrap.addWidget(summary)

        top.addLayout(title_wrap, stretch=1)
        top.addWidget(_SeverityBadge(issue.severity), alignment=Qt.AlignTop)
        outer.addLayout(top)

        if issue.details:
            details = QLabel(issue.details)
            details.setWordWrap(True)
            details.setStyleSheet("color: #8f8f8f; font-size: 12px; line-height: 1.4;")
            outer.addWidget(details)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addStretch()

        action_btn = QPushButton(issue.action_label)
        action_btn.setMinimumWidth(160)
        action_btn.clicked.connect(self._emit_action)
        bottom.addWidget(action_btn)
        outer.addLayout(bottom)

    def _emit_action(self) -> None:
        self.action_requested.emit(self._issue.recommended_action.value)


class _RecommendedActionsPanel(QFrame):
    action_requested: Signal = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._buttons: list[QPushButton] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        title = QLabel("Recommended Actions")
        title.setObjectName("SectionLabel")
        outer.addWidget(title)

        self._desc = QLabel("Next steps will appear here once the app has inspected the connected iPhone.")
        self._desc.setWordWrap(True)
        self._desc.setStyleSheet("color: #9a9a9a; font-size: 12px;")
        outer.addWidget(self._desc)

        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 4, 0, 0)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        outer.addLayout(self._grid)

    def set_actions(self, actions: list[RecommendedAction]) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._buttons.clear()

        if not actions:
            self._desc.setText("No action is needed right now.")
            return

        self._desc.setText("Use one of these shortcuts to move straight into the most relevant recovery flow.")
        for idx, action in enumerate(actions):
            btn = QPushButton(action.label)
            btn.setToolTip(action.description or action.label)
            btn.clicked.connect(lambda _checked=False, value=action.id.value: self.action_requested.emit(value))
            row, col = divmod(idx, 2)
            self._grid.addWidget(btn, row, col)
            self._buttons.append(btn)


class TroubleshootPage(QWidget):
    refresh_requested: Signal = Signal()
    action_requested: Signal = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = TroubleshootService()
        self._worker: _TroubleshootWorker | None = None
        self._current_snapshot: TroubleshootSnapshot | None = None
        self._build_ui()
        self.show_no_device()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(4)

        title = QLabel("Troubleshoot")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)

        self._subtitle = QLabel("Inspecting the current connection and device readiness.")
        self._subtitle.setStyleSheet("color: #8e8e8e; font-size: 12px;")
        title_wrap.addWidget(self._subtitle)

        header.addLayout(title_wrap, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        header.addWidget(refresh_btn, alignment=Qt.AlignRight | Qt.AlignTop)
        outer.addLayout(header)

        self._banner = QLabel()
        self._banner.setFixedHeight(44)
        self._banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        outer.addWidget(self._banner)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(14)

        self._issue_scroll = QScrollArea()
        self._issue_scroll.setWidgetResizable(True)
        self._issue_scroll.setFrameShape(QFrame.NoFrame)
        self._issue_wrap = QWidget()
        self._issue_layout = QVBoxLayout(self._issue_wrap)
        self._issue_layout.setContentsMargins(0, 0, 0, 0)
        self._issue_layout.setSpacing(12)
        self._issue_layout.addStretch()
        self._issue_scroll.setWidget(self._issue_wrap)
        left.addWidget(self._issue_scroll, stretch=1)

        self._actions_panel = _RecommendedActionsPanel()
        self._actions_panel.action_requested.connect(self.action_requested.emit)
        left.addWidget(self._actions_panel)

        right = QVBoxLayout()
        right.setSpacing(14)

        self._status_card = QFrame()
        self._status_card.setObjectName("Card")
        status_layout = QVBoxLayout(self._status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(10)

        status_title = QLabel("Technical Status")
        status_title.setObjectName("SectionLabel")
        status_layout.addWidget(status_title)

        self._status_grid = QGridLayout()
        self._status_grid.setHorizontalSpacing(14)
        self._status_grid.setVerticalSpacing(10)
        status_layout.addLayout(self._status_grid)
        right.addWidget(self._status_card)

        self._help_card = QFrame()
        self._help_card.setObjectName("Card")
        help_layout = QVBoxLayout(self._help_card)
        help_layout.setContentsMargins(16, 14, 16, 14)
        help_layout.setSpacing(8)

        help_title = QLabel("Troubleshooting Notes")
        help_title.setObjectName("SectionLabel")
        help_layout.addWidget(help_title)

        self._help_text = QLabel()
        self._help_text.setWordWrap(True)
        self._help_text.setStyleSheet("color: #9a9a9a; font-size: 12px; line-height: 1.45;")
        help_layout.addWidget(self._help_text)
        right.addWidget(self._help_card)
        right.addStretch()

        body.addLayout(left, stretch=3)
        body.addLayout(right, stretch=2)
        outer.addLayout(body, stretch=1)

    def abort_all(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.quit()
            self._worker.wait(1000)
        self._worker = None

    def show_no_device(self) -> None:
        self._subtitle.setText("No device connected. Plug in an iPhone over USB to begin diagnosis.")
        self._start_snapshot(device_detected=False)

    def show_connecting(self) -> None:
        self._subtitle.setText("A device was found. Reading device details and service readiness now.")
        self._render_loading("Connecting", "Reading device info and building a troubleshooting snapshot.")

    def show_device(self, info: DeviceInfo) -> None:
        self._subtitle.setText(f"{info.name} | {info.model} | iOS {info.ios_version}")
        self._start_snapshot(info=info, device_detected=True)

    def show_device_problem(self, error: str) -> None:
        self._subtitle.setText("A device was detected, but full access is still blocked.")
        self._start_snapshot(device_detected=True, info_error=error)

    def _start_snapshot(
        self,
        *,
        info: DeviceInfo | None = None,
        device_detected: bool = False,
        info_error: str = "",
    ) -> None:
        self.abort_all()
        self._render_loading("Inspecting", "Collecting the latest connection, storage, and developer-service checks.")
        self._worker = _TroubleshootWorker(
            self._service,
            info=info,
            device_detected=device_detected,
            info_error=info_error,
        )
        self._worker.finished.connect(self._on_snapshot_ready)
        self._worker.start()

    def _on_snapshot_ready(self, result: ServiceResult[TroubleshootSnapshot]) -> None:
        self._worker = None
        if not result.success or result.data is None:
            self._render_loading("Unavailable", result.error or "Could not prepare troubleshooting data.")
            return
        self._current_snapshot = result.data
        self._render_snapshot(result.data)

    def _render_loading(self, status: str, summary: str) -> None:
        self._set_banner(TroubleshootSeverity.INFO, status, summary)
        self._clear_issues()
        placeholder = QLabel(summary)
        placeholder.setWordWrap(True)
        placeholder.setStyleSheet("color: #8f8f8f; font-size: 13px; padding: 8px 2px;")
        self._issue_layout.insertWidget(0, placeholder)
        self._actions_panel.set_actions([])
        self._render_status_rows(
            [
                ("Connection", "Checking"),
                ("Battery", "Unknown"),
                ("Free Storage", "Unknown"),
                ("Screenshot", "Unknown"),
                ("Mirror", "Unknown"),
            ]
        )
        self._help_text.setText("Once the snapshot finishes, this page will explain the most important blockers and point you to the right recovery flow.")

    def _render_snapshot(self, snapshot: TroubleshootSnapshot) -> None:
        self._set_banner(snapshot.overall_severity, snapshot.overall_status, snapshot.overall_summary)
        self._clear_issues()

        if snapshot.issues:
            for issue in snapshot.issues:
                card = _IssueCard(issue)
                card.action_requested.connect(self.action_requested.emit)
                self._issue_layout.insertWidget(self._issue_layout.count() - 1, card)
        else:
            healthy = QLabel("No major issues detected. The connected iPhone looks ready for routine maintenance tasks.")
            healthy.setWordWrap(True)
            healthy.setStyleSheet("color: #9fd39f; font-size: 13px; padding: 8px 2px;")
            self._issue_layout.insertWidget(0, healthy)

        self._actions_panel.set_actions(snapshot.recommended_actions)
        self._render_status_rows(
            [
                ("Connection", "Connected" if snapshot.device_detected else "Disconnected"),
                ("Device", snapshot.device_name or "Unknown"),
                ("Battery", f"{snapshot.battery_level}%" if snapshot.battery_level is not None else "Unknown"),
                (
                    "Free Storage",
                    f"{snapshot.free_storage_gb:.1f} GB"
                    if snapshot.free_storage_gb is not None else "Unknown",
                ),
                ("Developer Mode", self._bool_state(snapshot.developer_mode)),
                ("Screenshot", snapshot.screenshot_status),
                ("Mirror", snapshot.mirror_status),
            ]
        )

        notes: list[str] = []
        if snapshot.critical_tools_missing:
            notes.append(
                "Core libimobiledevice tools are missing. Open Settings to point the app at the correct tools folder."
            )
        if snapshot.device_detected and not snapshot.device_info_available:
            notes.append(
                "The phone was detected, but trusted device info could not be read. Unlock the iPhone and accept any Trust prompt."
            )
        if snapshot.free_storage_gb is not None and snapshot.free_storage_gb < 10:
            notes.append(
                "Low free storage is one of the most common causes of unstable backups, exports, and app-management tasks."
            )
        if snapshot.screenshot_status != "Ready":
            notes.append(snapshot.screenshot_detail or "Screenshot checks were not ready.")
        if snapshot.mirror_status != "Ready":
            notes.append(snapshot.mirror_detail or "Mirror readiness is still incomplete.")
        if not notes:
            notes.append("This device is in a healthy state. Use Diagnostics if you want a deeper technical view.")
        self._help_text.setText("\n\n".join(notes))

    def _set_banner(self, severity: TroubleshootSeverity, title: str, summary: str) -> None:
        palette = {
            TroubleshootSeverity.HEALTHY: ("#0b1f14", "#2e7d32", "#81c784"),
            TroubleshootSeverity.INFO: ("#131c24", "#1565c0", "#90caf9"),
            TroubleshootSeverity.WARNING: ("#241700", "#fb8c00", "#ffcc80"),
            TroubleshootSeverity.CRITICAL: ("#2a1111", "#c62828", "#ef9a9a"),
        }[severity]
        bg, border, text = palette
        self._banner.setText(f"{title}   {summary}")
        self._banner.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; color: {text};"
            "border-radius: 6px; padding: 0 14px; font-size: 13px; font-weight: bold;"
        )

    def _clear_issues(self) -> None:
        while self._issue_layout.count() > 1:
            item = self._issue_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _render_status_rows(self, rows: list[tuple[str, str]]) -> None:
        while self._status_grid.count():
            item = self._status_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for row_idx, (label_text, value_text) in enumerate(rows):
            label = QLabel(label_text.upper())
            label.setStyleSheet("color: #6f6f6f; font-size: 10px; font-weight: bold;")
            value = QLabel(value_text)
            value.setWordWrap(True)
            value.setStyleSheet("color: #ededed; font-size: 13px;")
            self._status_grid.addWidget(label, row_idx, 0, alignment=Qt.AlignTop)
            self._status_grid.addWidget(value, row_idx, 1)
        self._status_grid.setColumnStretch(1, 1)

    @staticmethod
    def _bool_state(value: bool | None) -> str:
        if value is True:
            return "On"
        if value is False:
            return "Off"
        return "Unknown"
