"""
Recovery mode assistant page.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.results import ServiceResult
from ...device.info import DeviceInfo
from ...services.recovery_mode_service import (
    RecoveryDetectionSnapshot,
    RecoveryModeService,
)


class _RecoveryWorker(QThread):
    finished: Signal = Signal(object)

    def __init__(self, service: RecoveryModeService, info: DeviceInfo | None) -> None:
        super().__init__()
        self._service = service
        self._info = info

    def run(self) -> None:
        self.finished.emit(self._service.get_recovery_snapshot(self._info))


class _RecoveryStepCard(QFrame):
    def __init__(self, idx: int, title: str, detail: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        n = QLabel(f"STEP {idx}")
        n.setStyleSheet("color: #5f6b7a; font-size: 10px; font-weight: bold;")
        layout.addWidget(n)

        t = QLabel(title)
        t.setStyleSheet("color: #f0f0f0; font-size: 16px; font-weight: bold;")
        layout.addWidget(t)

        d = QLabel(detail)
        d.setWordWrap(True)
        d.setStyleSheet("color: #c7c7c7; font-size: 12px;")
        layout.addWidget(d)


class RecoveryModePage(QWidget):
    action_requested: Signal = Signal(str)
    refresh_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = RecoveryModeService()
        self._worker: _RecoveryWorker | None = None
        self._info: DeviceInfo | None = None
        self._build_ui()
        self.show_no_device()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = QHBoxLayout()
        title_wrap = QVBoxLayout()
        title = QLabel("Recovery Mode Assistant")
        title.setObjectName("PageTitle")
        self._subtitle = QLabel("Use recovery mode safely and understand what Update or Restore will do next.")
        self._subtitle.setStyleSheet("color: #8e8e8e; font-size: 12px;")
        title_wrap.addWidget(title)
        title_wrap.addWidget(self._subtitle)
        header.addLayout(title_wrap, stretch=1)

        refresh_btn = QPushButton("Refresh State")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
        outer.addLayout(header)

        self._banner = QLabel()
        self._banner.setFixedHeight(46)
        self._banner.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        outer.addWidget(self._banner)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(14)
        self._steps_host = QWidget()
        self._steps_layout = QVBoxLayout(self._steps_host)
        self._steps_layout.setContentsMargins(0, 0, 0, 0)
        self._steps_layout.setSpacing(12)
        left.addWidget(self._steps_host, stretch=1)

        right = QVBoxLayout()
        right.setSpacing(14)

        self._state_card = QFrame()
        self._state_card.setObjectName("Card")
        state_layout = QVBoxLayout(self._state_card)
        state_layout.setContentsMargins(16, 14, 16, 14)
        state_layout.setSpacing(8)
        title_lbl = QLabel("Current State")
        title_lbl.setObjectName("SectionLabel")
        state_layout.addWidget(title_lbl)
        self._state_label = QLabel()
        self._state_label.setStyleSheet("color: #f0f0f0; font-size: 16px; font-weight: bold;")
        state_layout.addWidget(self._state_label)
        self._state_detail = QLabel()
        self._state_detail.setWordWrap(True)
        self._state_detail.setStyleSheet("color: #9a9a9a; font-size: 12px;")
        state_layout.addWidget(self._state_detail)
        self._profile_detail = QLabel()
        self._profile_detail.setWordWrap(True)
        self._profile_detail.setStyleSheet("color: #c8c8c8; font-size: 12px;")
        state_layout.addWidget(self._profile_detail)
        right.addWidget(self._state_card)

        self._warnings_card = QFrame()
        self._warnings_card.setObjectName("Card")
        warnings_layout = QVBoxLayout(self._warnings_card)
        warnings_layout.setContentsMargins(16, 14, 16, 14)
        warnings_layout.setSpacing(8)
        warnings_title = QLabel("What Happens Next")
        warnings_title.setObjectName("SectionLabel")
        warnings_layout.addWidget(warnings_title)
        self._warnings_label = QLabel()
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setStyleSheet("color: #d0d0d0; font-size: 12px;")
        warnings_layout.addWidget(self._warnings_label)
        right.addWidget(self._warnings_card)

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
            ("Open Passcode Recovery", "open_passcode_recovery"),
            ("Open Restore Guidance", "open_backup"),
            ("Refresh State", "refresh"),
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
        self._subtitle.setText("Use this assistant to prepare recovery mode even if the iPhone is currently unavailable.")
        self._refresh()

    def show_connecting(self) -> None:
        self._subtitle.setText("Reading the connected iPhone so recovery-mode guidance can be tailored.")
        self._set_loading("Reading connected device context.")

    def show_device(self, info: DeviceInfo) -> None:
        self._info = info
        self._subtitle.setText(f"{info.name} | {info.model} | iOS {info.ios_version}")
        self._refresh()

    def _refresh(self) -> None:
        self.abort_all()
        self._set_loading("Preparing recovery mode guidance.")
        self._worker = _RecoveryWorker(self._service, self._info)
        self._worker.finished.connect(self._on_snapshot)
        self._worker.start()

    def _on_snapshot(self, result: ServiceResult[RecoveryDetectionSnapshot]) -> None:
        self._worker = None
        if not result.success or result.data is None:
            self._set_loading(result.error or "Could not inspect recovery mode guidance.")
            return
        snap = result.data
        self._banner.setText(f"{snap.state_label}   {snap.state_detail}")
        self._banner.setStyleSheet(
            "background: #1d1624; border: 1px solid #8e24aa; color: #e1bee7;"
            "border-radius: 6px; padding: 0 14px; font-size: 13px; font-weight: bold;"
        )
        self._state_label.setText(snap.state_label)
        self._state_detail.setText(snap.state_detail)
        self._profile_detail.setText(
            f"{snap.profile.family}\n{snap.profile.summary}\nButtons: {snap.profile.buttons}"
        )
        self._warnings_label.setText("\n\n".join(snap.restore_warnings))
        self._render_steps(snap)

    def _render_steps(self, snap: RecoveryDetectionSnapshot) -> None:
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for idx, step in enumerate(snap.steps, start=1):
            self._steps_layout.addWidget(_RecoveryStepCard(idx, step.title, step.detail))
        self._steps_layout.addStretch()

    def _set_loading(self, text: str) -> None:
        self._banner.setText(text)
        self._banner.setStyleSheet(
            "background: #141d2a; border: 1px solid #2962ff; color: #90caf9;"
            "border-radius: 6px; padding: 0 14px; font-size: 13px; font-weight: bold;"
        )
        self._state_label.setText("Checking")
        self._state_detail.setText(text)
        self._profile_detail.setText("")
        self._warnings_label.setText("")
        while self._steps_layout.count():
            item = self._steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _emit_action(self, action_id: str) -> None:
        if action_id == "refresh":
            self._refresh()
            return
        self.action_requested.emit(action_id)
