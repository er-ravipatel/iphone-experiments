"""
PreviewPanel — self-contained photo/video preview widget.

Public API:
    load(f, row, udid, cache)  — show preview for a media file
    clear()                    — hide panel and reset state
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QSlider, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import QPixmap, QImage

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

from .workers import PhotoDecodeWorker, DownloadOpenWorker
from .widgets import PhotoPopout, RENDERABLE
from ._utils import fmt_size, open_system
from ....terminal.features.media import VIDEO_EXTENSIONS


class PreviewPanel(QWidget):
    """
    Right-hand preview pane for the media page.
    Shows photo (full-res) or video (in-app player) for the selected file.
    Emits result_message(text, color) so the parent can show status text.
    """
    result_message = Signal(str, str)   # text, css color

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._udid: str | None = None
        self._cache: Path | None = None
        self._preview_local: str | None = None
        self._live_workers: set = set()
        self._preview_worker: DownloadOpenWorker | None = None
        self._popout_win: PhotoPopout | None = None
        self._media_files: list[dict] = []
        self._current_row: int = 0

        self._build_ui()

        if _HAS_MULTIMEDIA:
            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.setVideoOutput(self._video_widget)
            self._player.playbackStateChanged.connect(self._on_player_state)
            self._player.positionChanged.connect(self._on_video_pos)
            self._player.durationChanged.connect(self._on_video_dur)
        else:
            self._player = None

    # ── Public API ─────────────────────────────────────────────────────────

    def set_context(self, udid: str, cache: Path) -> None:
        """Called by MediaPage when a device connects."""
        self._udid = udid
        self._cache = cache

    def load(self, f: dict, row: int, media_files: list[dict] | None = None) -> None:
        """Show preview for file f at grid row."""
        if not self._udid or not self._cache:
            log.warning("PreviewPanel.load called but no udid/cache set")
            return
        log.debug("PreviewPanel.load: row=%d file=%s", row, f.get("name"))
        self._current_row = row
        if media_files is not None:
            self._media_files = media_files
        ext   = Path(f["name"]).suffix.lower()
        local = str(self._cache / f["name"])

        self._prev_name_lbl.setText(f["name"])
        self._prev_open_btn.setEnabled(False)
        self._popout_btn.setEnabled(False)

        if ext not in VIDEO_EXTENSIONS:
            if self._player:
                self._player.stop()
                self._player.setSource(QUrl())
            if Path(local).exists():
                self._preview_local = local
                self._prev_open_btn.setEnabled(True)
                self._popout_btn.setEnabled(True)
            self._show_photo(row, f)
        else:
            if Path(local).exists():
                self._preview_local = local
                self._prev_open_btn.setEnabled(True)
                self._popout_btn.setEnabled(True)
                self._show_video(local, ext)
            else:
                self._stack.setCurrentIndex(0)
                self.result_message.emit(f"Downloading {f['name']} for preview…", "#9e9e9e")
                self._start_download(f["path"], local, row, ext)

    def clear(self) -> None:
        """Hide panel and reset all preview state."""
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())
        self._stack.setCurrentIndex(0)
        self._prev_name_lbl.setText("")
        self._prev_open_btn.setEnabled(False)
        self._popout_btn.setEnabled(False)
        self._photo_img_lbl.setPixmap(QPixmap())
        self._photo_meta_lbl.setText("")
        self._preview_local = None

    def abort(self) -> None:
        """Cancel any running workers."""
        if self._player:
            self._player.stop()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        hdr = QLabel("PREVIEW")
        hdr.setObjectName("SectionLabel")
        vbox.addWidget(hdr)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet(
            "QStackedWidget { background: #111; border: 1px solid #272727; border-radius: 6px; }"
        )

        # 0 — placeholder
        ph = QLabel("Select a file\nto preview")
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet("color: #383838; font-size: 13px; background: transparent;")
        self._stack.addWidget(ph)

        # 1 — video
        if _HAS_MULTIMEDIA:
            video_container = QWidget()
            video_container.setStyleSheet("background: transparent;")
            vc_vbox = QVBoxLayout(video_container)
            vc_vbox.setContentsMargins(0, 0, 0, 0)
            vc_vbox.setSpacing(4)

            self._video_widget = QVideoWidget()
            self._video_widget.setMinimumHeight(200)
            vc_vbox.addWidget(self._video_widget, stretch=1)

            ctrl = QHBoxLayout()
            self._play_btn = QPushButton("▶")
            self._play_btn.setFixedWidth(36)
            self._play_btn.clicked.connect(self._on_play_pause)
            ctrl.addWidget(self._play_btn)

            self._stop_btn = QPushButton("■")
            self._stop_btn.setFixedWidth(36)
            self._stop_btn.clicked.connect(self._on_stop_video)
            ctrl.addWidget(self._stop_btn)

            self._seek_slider = QSlider(Qt.Horizontal)
            self._seek_slider.setRange(0, 0)
            self._seek_slider.sliderMoved.connect(self._on_seek)
            ctrl.addWidget(self._seek_slider, stretch=1)

            self._time_lbl = QLabel("0:00")
            self._time_lbl.setObjectName("StatusLabel")
            self._time_lbl.setFixedWidth(40)
            ctrl.addWidget(self._time_lbl)

            vc_vbox.addLayout(ctrl)
            self._stack.addWidget(video_container)
        else:
            no_vid = QLabel("QtMultimedia\nnot available")
            no_vid.setAlignment(Qt.AlignCenter)
            no_vid.setStyleSheet("color: #555; font-size: 11px; background: transparent;")
            self._stack.addWidget(no_vid)

        # 2 — photo
        photo_w = QWidget()
        photo_w.setStyleSheet("background: transparent;")
        photo_vbox = QVBoxLayout(photo_w)
        photo_vbox.setContentsMargins(4, 4, 4, 4)
        photo_vbox.setSpacing(6)
        self._photo_img_lbl = QLabel()
        self._photo_img_lbl.setAlignment(Qt.AlignCenter)
        self._photo_img_lbl.setMinimumHeight(160)
        self._photo_img_lbl.setStyleSheet("background: transparent;")
        photo_vbox.addWidget(self._photo_img_lbl, stretch=1)
        self._photo_meta_lbl = QLabel()
        self._photo_meta_lbl.setWordWrap(True)
        self._photo_meta_lbl.setTextFormat(Qt.RichText)
        self._photo_meta_lbl.setStyleSheet("color: #757575; font-size: 11px; background: transparent;")
        photo_vbox.addWidget(self._photo_meta_lbl)
        self._stack.addWidget(photo_w)   # index 2

        vbox.addWidget(self._stack, stretch=1)

        self._prev_name_lbl = QLabel()
        self._prev_name_lbl.setObjectName("StatusLabel")
        self._prev_name_lbl.setWordWrap(True)
        vbox.addWidget(self._prev_name_lbl)

        btn_row = QHBoxLayout()
        self._prev_open_btn = QPushButton("Open in System App")
        self._prev_open_btn.setEnabled(False)
        self._prev_open_btn.clicked.connect(self._on_open_sys)
        btn_row.addWidget(self._prev_open_btn)

        self._popout_btn = QPushButton("⤢ Pop Out")
        self._popout_btn.setEnabled(False)
        self._popout_btn.setToolTip("Open in floating window")
        self._popout_btn.clicked.connect(self._on_pop_out)
        btn_row.addWidget(self._popout_btn)

        vbox.addLayout(btn_row)

    # ── Photo preview ──────────────────────────────────────────────────────

    def _show_photo(self, row: int, f: dict) -> None:
        ext       = Path(f["name"]).suffix.lower()
        full_path = self._cache / f["name"]
        thumb_path = self._cache / ("_thumb_" + Path(f["name"]).stem + ".jpg")
        local     = str(full_path)

        self._stack.setCurrentIndex(2)
        self._photo_img_lbl.setPixmap(QPixmap())

        size_str = fmt_size(f.get("size", 0))
        self._photo_meta_lbl.setText(
            f"<b>{f['name']}</b><br>"
            f"<font color='#555'>Path:</font> {f['path']}<br>"
            f"<font color='#555'>Size:</font> {size_str}"
        )

        if full_path.exists():
            self._decode_and_show(local, ext, f, size_str)
        else:
            if thumb_path.exists():
                img = QImage(str(thumb_path))
                if not img.isNull():
                    pw = max(self.width() - 16, 280)
                    self._photo_img_lbl.setPixmap(
                        QPixmap.fromImage(img.scaled(pw, pw, Qt.KeepAspectRatio,
                                                     Qt.SmoothTransformation))
                    )
            self._photo_img_lbl.setText("Downloading…")
            self.result_message.emit(f"Downloading {f['name']}…", "#9e9e9e")
            self._start_download(f["path"], local, row, ext)

    def _decode_and_show(self, local: str, ext: str, f: dict, size_str: str) -> None:
        log.debug("PreviewPanel._decode_and_show: %s (ext=%s)", local, ext)
        pw = max(self.width() - 16, 280)
        if ext in RENDERABLE:
            img = QImage(local)
            if not img.isNull():
                self._photo_img_lbl.setText("")
                self._photo_img_lbl.setPixmap(
                    QPixmap.fromImage(img.scaled(pw, pw, Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation))
                )
            else:
                self._photo_img_lbl.setText("Cannot render preview")
            threading.Thread(
                target=self._fetch_meta,
                args=(local, ext, f, size_str),
                daemon=True,
            ).start()
        else:
            self._photo_img_lbl.setText("Decoding…")
            w = PhotoDecodeWorker(local, ext, pw)
            w.ready.connect(
                lambda px, fw=f, ss=size_str, ex=ext: self._apply_pixmap(px, fw, ss, ex)
            )
            self._track(w)
            w.start()

    def _apply_pixmap(self, px: QPixmap, f: dict, size_str: str, ext: str) -> None:
        self._photo_img_lbl.setText("")
        if px.isNull():
            self._photo_img_lbl.setText("Cannot render preview")
        else:
            self._photo_img_lbl.setPixmap(px)
        full_path = self._cache / f["name"]
        threading.Thread(
            target=self._fetch_meta,
            args=(str(full_path), ext, f, size_str),
            daemon=True,
        ).start()

    def _fetch_meta(self, img_src: str, ext: str, f: dict, size_str: str) -> None:
        log.debug("PreviewPanel._fetch_meta: %s", img_src)
        width = height = 0
        date_str = ""
        try:
            from PIL import Image as PilImage
            if ext in {'.heic', '.heif'}:
                import pillow_heif
                pillow_heif.register_heif_opener()
            with PilImage.open(img_src) as im:
                width, height = im.size
                exif = im._getexif() if hasattr(im, '_getexif') else None
                if exif:
                    date_str = str(exif.get(36867) or exif.get(306) or "")
        except Exception:
            log.exception("PreviewPanel._fetch_meta failed for %s", img_src)

        dim_str = f"{width} × {height} px" if width else ""
        meta_html = (
            f"<b>{f['name']}</b><br>"
            f"<font color='#555'>Path:</font> {f['path']}<br>"
            f"<font color='#555'>Size:</font> {size_str}"
            + (f"<br><font color='#555'>Dimensions:</font> {dim_str}" if dim_str else "")
            + (f"<br><font color='#555'>Date:</font> {date_str}" if date_str else "")
        )
        QTimer.singleShot(0, lambda html=meta_html: self._photo_meta_lbl.setText(html))

    # ── Video preview ──────────────────────────────────────────────────────

    def _show_video(self, local: str, ext: str) -> None:
        if not _HAS_MULTIMEDIA or not self._player:
            return
        self._player.stop()
        self._stack.setCurrentIndex(1)
        self._play_btn.setText("▶")
        self._seek_slider.setValue(0)
        self._time_lbl.setText("0:00")
        self._player.setSource(QUrl.fromLocalFile(local))
        self._player.play()
        self._play_btn.setText("⏸")

    def _on_play_pause(self) -> None:
        if not self._player:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_stop_video(self) -> None:
        if self._player:
            self._player.stop()

    def _on_seek(self, pos_ms: int) -> None:
        if self._player:
            self._player.setPosition(pos_ms)

    def _on_player_state(self, state) -> None:
        if not _HAS_MULTIMEDIA:
            return
        self._play_btn.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_video_pos(self, pos_ms: int) -> None:
        self._seek_slider.blockSignals(True)
        self._seek_slider.setValue(pos_ms)
        self._seek_slider.blockSignals(False)
        secs = pos_ms // 1000
        self._time_lbl.setText(f"{secs // 60}:{secs % 60:02d}")

    def _on_video_dur(self, dur_ms: int) -> None:
        self._seek_slider.setRange(0, dur_ms)

    # ── Download helper ────────────────────────────────────────────────────

    def _start_download(self, remote: str, local: str, row: int, ext: str) -> None:
        self._preview_worker = DownloadOpenWorker(self._udid, remote, local)
        self._preview_worker.ready.connect(
            lambda p, r=row, e=ext: self._on_download_ready(p, e, r)
        )
        self._preview_worker.failed.connect(
            lambda err: (
                self.result_message.emit(f"Download failed: {err}", "#ef5350"),
                self._photo_img_lbl.setText("Download failed"),
            )
        )
        self._track(self._preview_worker)
        self._preview_worker.start()

    def _on_download_ready(self, local: str, ext: str, row: int) -> None:
        self.result_message.emit("", "#9e9e9e")
        self._preview_local = local
        self._prev_open_btn.setEnabled(True)
        self._popout_btn.setEnabled(True)
        if ext in VIDEO_EXTENSIONS:
            self._show_video(local, ext)
        else:
            # Re-trigger photo show now that file exists — MediaPage must pass f again
            # We reconstruct f from what we know; meta is re-read anyway
            self._decode_and_show(local, ext, {"name": Path(local).name,
                                               "path": local,
                                               "size": Path(local).stat().st_size},
                                   fmt_size(Path(local).stat().st_size))

    # ── Action buttons ─────────────────────────────────────────────────────

    def _on_open_sys(self) -> None:
        if self._preview_local and Path(self._preview_local).exists():
            open_system(self._preview_local)

    def _on_pop_out(self) -> None:
        if self._stack.currentIndex() == 2 and self._preview_local:
            ext  = Path(self._preview_local).suffix.lower()
            name = Path(self._preview_local).name
            self._popout_win = PhotoPopout(
                self._preview_local, ext, name,
                media_files=self._media_files,
                cache=self._cache,
                current_row=self._current_row,
            )
        elif self._stack.currentIndex() == 1 and self._preview_local:
            open_system(self._preview_local)

    # ── Worker lifecycle ───────────────────────────────────────────────────

    def _track(self, worker: QThread) -> None:
        self._live_workers.add(worker)
        worker.finished.connect(lambda: self._live_workers.discard(worker))
