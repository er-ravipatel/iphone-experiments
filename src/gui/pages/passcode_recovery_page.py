"""
Passcode recovery page.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.results import ServiceResult
from ...device.info import DeviceInfo
from ...services.passcode_recovery_service import (
    PasscodeProblemType,
    PasscodeRecoveryService,
    PasscodeRecoverySnapshot,
)


class _PasscodeWorker(QThread):
    finished: Signal = Signal(object)

    def __init__(
        self,
        service: PasscodeRecoveryService,
        problem_type: PasscodeProblemType,
        info: DeviceInfo | None,
    ) -> None:
        super().__init__()
        self._service = service
        self._problem_type = problem_type
        self._info = info

    def run(self) -> None:
        self.finished.emit(
            self._service.get_passcode_recovery_snapshot(self._problem_type, self._info)
        )


class _StepCard(QFrame):
    def __init__(self, idx: int, title: str, detail: str, emphasis: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        number = QLabel(f"STEP {idx}")
        number.setStyleSheet("color: #5f6b7a; font-size: 10px; font-weight: bold;")
        layout.addWidget(number)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #f0f0f0; font-size: 16px; font-weight: bold;")
        layout.addWidget(title_lbl)

        detail_lbl = QLabel(detail)
        detail_lbl.setWordWrap(True)
        detail_lbl.setStyleSheet("color: #c7c7c7; font-size: 12px;")
        layout.addWidget(detail_lbl)

        if emphasis:
            emphasis_lbl = QLabel(emphasis)
            emphasis_lbl.setWordWrap(True)
            emphasis_lbl.setStyleSheet("color: #ffcc80; font-size: 12px;")
            layout.addWidget(emphasis_lbl)


class PasscodeRecoveryPage(QWidget):
    action_requested: Signal = Signal(str)
    refresh_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = PasscodeRecoveryService()
        self._worker: _PasscodeWorker | None = None
        self._info: DeviceInfo | None = None
        self._problem_type = PasscodeProblemType.DEVICE_PASSCODE
        self._build_ui()
        self.show_no_device()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_wrap = QVBoxLayout()
        title = QLabel("Passcode Recovery")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("Prepare the safest supported recovery path for a passcode problem.")
        self._subtitle.setStyleSheet("color: #8e8e8e; font-size: 12px;")
        title_wrap.addWidget(title)
        title_wrap.addWidget(self._subtitle)
        header.addLayout(title_wrap, stretch=1)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
        outer.addLayout(header)

        self._banner = QLabel()
        self._banner.setFixedHeight(46)
        self._banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        outer.addWidget(self._banner)

        selector_card = QFrame()
        selector_card.setObjectName("Card")
        selector_layout = QVBoxLayout(selector_card)
        selector_layout.setContentsMargins(16, 14, 16, 14)
        selector_layout.setSpacing(10)

        selector_title = QLabel("Problem Type")
        selector_title.setObjectName("SectionLabel")
        selector_layout.addWidget(selector_title)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._problem_group = QButtonGroup(self)
        for label, value in (
            ("Forgot Device Passcode", PasscodeProblemType.DEVICE_PASSCODE),
            ("Forgot Screen Time Passcode", PasscodeProblemType.SCREEN_TIME),
            ("Recently Changed Passcode", PasscodeProblemType.RECENT_CHANGE),
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("problemType", value.value)
            btn.clicked.connect(self._on_problem_changed)
            row.addWidget(btn)
            self._problem_group.addButton(btn)
            if value == self._problem_type:
                btn.setChecked(True)
        selector_layout.addLayout(row)
        outer.addWidget(selector_card)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(14)

        self._backup_card = QFrame()
        self._backup_card.setObjectName("Card")
        backup_layout = QVBoxLayout(self._backup_card)
        backup_layout.setContentsMargins(16, 14, 16, 14)
        backup_layout.setSpacing(8)
        backup_title = QLabel("Backup Safety Check")
        backup_title.setObjectName("SectionLabel")
        backup_layout.addWidget(backup_title)
        self._backup_summary = QLabel()
        self._backup_summary.setWordWrap(True)
        self._backup_summary.setStyleSheet("color: #d0d0d0; font-size: 13px;")
        backup_layout.addWidget(self._backup_summary)
        self._backup_detail = QLabel()
        self._backup_detail.setWordWrap(True)
        self._backup_detail.setStyleSheet("color: #8f8f8f; font-size: 12px;")
        backup_layout.addWidget(self._backup_detail)
        left.addWidget(self._backup_card)

        self._steps_host = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_host)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(12)
        left.addWidget(self._steps_host, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(14)

        self._guidance_card = QFrame()
        self._guidance_card.setObjectName("Card")
        guidance_layout = QVBoxLayout(self._guidance_card)
        guidance_layout.setContentsMargins(16, 14, 16, 14)
        guidance_layout.setSpacing(8)
        guidance_title = QLabel("Guidance")
        guidance_title.setObjectName("SectionLabel")
        guidance_layout.addWidget(guidance_title)
        self._guidance_summary = QLabel()
        self._guidance_summary.setWordWrap(True)
        self._guidance_summary.setStyleSheet("color: #e8e8e8; font-size: 13px;")
        guidance_layout.addWidget(self._guidance_summary)
        self._guidance_warning = QLabel()
        self._guidance_warning.setWordWrap(True)
        self._guidance_warning.setStyleSheet("color: #ffcc80; font-size: 12px;")
        guidance_layout.addWidget(self._guidance_warning)
        self._guidance_notes = QLabel()
        self._guidance_notes.setWordWrap(True)
        self._guidance_notes.setStyleSheet("color: #9a9a9a; font-size: 12px;")
        guidance_layout.addWidget(self._guidance_notes)
        right.addWidget(self._guidance_card)

        self._actions_card = QFrame()
        self._actions_card.setObjectName("Card")
        actions_layout = QVBoxLayout(self._actions_card)
        actions_layout.setContentsMargins(16, 14, 16, 14)
        actions_layout.setSpacing(10)
        actions_title = QLabel("Next Actions")
        actions_title.setObjectName("SectionLabel")
        actions_layout.addWidget(actions_title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        actions = [
            ("Open Backup & Restore", "open_backup"),
            ("Open Recovery Mode Assistant", "open_recovery_mode"),
            ("Refresh", "refresh"),
            ("View Restore Guidance", "open_recovery_mode"),
        ]
        for idx, (label, action_id) in enumerate(actions):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked=False, value=action_id: self._emit_action(value))
            grid.addWidget(btn, idx // 2, idx % 2)
        actions_layout.addLayout(grid)
        right.addWidget(self._actions_card)
        right.addStretch()

        body.addLayout(left, stretch=3)
        body.addLayout(right, stretch=2)
        outer.addLayout(body, stretch=1)

    def abort_all(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(1000)
        self._worker = None

    def show_no_device(self) -> None:
        self._info = None
        self._subtitle.setText("No device is required to inspect local backups and prepare the supported recovery path.")
        self._refresh()

    def show_connecting(self) -> None:
        self._subtitle.setText("Reading the connected iPhone so recovery guidance can be tailored.")
        self._set_loading("Reading connected device context.")

    def show_device(self, info: DeviceInfo) -> None:
        self._info = info
        self._subtitle.setText(f"{info.name} | {info.model} | iOS {info.ios_version}")
        self._refresh()

    def _refresh(self) -> None:
        self.abort_all()
        self._set_loading("Preparing passcode recovery guidance.")
        self._worker = _PasscodeWorker(self._service, self._problem_type, self._info)
        self._worker.finished.connect(self._on_snapshot)
        self._worker.start()

    def _on_problem_changed(self) -> None:
        btn = self.sender()
        if isinstance(btn, QPushButton):
            self._problem_type = PasscodeProblemType(btn.property("problemType"))
            self._refresh()

    def _on_snapshot(self, result: ServiceResult[PasscodeRecoverySnapshot]) -> None:
        self._worker = None
        if not result.success or result.data is None:
            self._set_loading(result.error or "Could not build recovery guidance.")
            return
        snap = result.data
        self._set_banner(snap.summary)
        if snap.backup.has_backup:
            self._backup_summary.setText(
                f"Local backup found ({snap.backup.backup_count} total). Latest backup: {snap.backup.latest_date}."
            )
            self._backup_detail.setText(
                f"Path: {snap.backup.latest_path}\nSize: {snap.backup.latest_size}"
            )
        else:
            self._backup_summary.setText("No local backup was found yet.")
            self._backup_detail.setText(f"Backup folder checked: {snap.backup.backup_root}")
        self._guidance_summary.setText(snap.summary)
        self._guidance_warning.setText(snap.warning)
        self._guidance_notes.setText("\n\n".join(snap.notes))
        self._render_steps(snap)

    def _render_steps(self, snap: PasscodeRecoverySnapshot) -> None:
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for idx, step in enumerate(snap.steps, start=1):
            self._steps_layout.addWidget(_StepCard(idx, step.title, step.detail, step.emphasis))
        self._steps_layout.addStretch()

    def _set_loading(self, text: str) -> None:
        self._set_banner(text)
        self._backup_summary.setText(text)
        self._backup_detail.setText("")
        self._guidance_summary.setText("")
        self._guidance_warning.setText("")
        self._guidance_notes.setText("")
        self._render_steps(
            PasscodeRecoverySnapshot(
                problem_type=self._problem_type,
                recovery_path=self._service._recovery_path(self._problem_type),
            )
        )

    def _set_banner(self, text: str) -> None:
        self._banner.setText(text)
        self._banner.setStyleSheet(
            "background: #141d2a; border: 1px solid #2962ff; color: #90caf9;"
            "border-radius: 6px; padding: 0 14px; font-size: 13px; font-weight: bold;"
        )

    def _emit_action(self, action_id: str) -> None:
        if action_id == "refresh":
            self._refresh()
            return
        self.action_requested.emit(action_id)
