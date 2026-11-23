"""Bộ điều phối chính của ứng dụng ScreenLens Translate."""

from __future__ import annotations

import copy
import sys
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, QRect, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.capture import FrameDiffer, capture_logical_rect
from src.config import APP_NAME, AppConfig, LANG_BADGES
from src.ocr_engine import MultilingualOCREngine
from src.pipeline import PipelineOutput, ScreenTranslatePipeline
from src.translator import TranslationEngine
from src.ui.control_bar import ControlBar
from src.ui.history_panel import HistoryPanel
from src.ui.inplace_overlay import InPlaceOverlay
from src.ui.live_overlay import LiveCaptureFrame, LiveSubtitleWindow
from src.ui.settings_dialog import SettingsDialog
from src.ui.snip_overlay import SnipOverlay
from src.ui.styles import DARK_GLASS_QSS, create_app_icon
from src.win32_utils import GlobalHotkeyManager, MOD_ALT

VK_Q = 0x51
VK_W = 0x57
VK_S = 0x53


class _WorkerSignals(QObject):
    finished = Signal(int, object)
    status = Signal(str)


class _WarmupTask(QRunnable):
    def __init__(self, ocr: MultilingualOCREngine, fast_mode: bool) -> None:
        super().__init__()
        self.ocr = ocr
        self.fast_mode = fast_mode
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            self.ocr.warmup(fast_mode=self.fast_mode)
            self.signals.finished.emit(0, "ready")
        except Exception as exc:
            self.signals.finished.emit(0, f"error:{exc}")


class _PipelineTask(QRunnable):
    def __init__(
        self,
        job_id: int,
        pipeline: ScreenTranslatePipeline,
        image_rgb: np.ndarray,
        config: AppConfig,
        scale_x: float,
        scale_y: float,
    ) -> None:
        super().__init__()
        self.job_id = job_id
        self.pipeline = pipeline
        self.image_rgb = image_rgb
        self.config = config
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.signals = _WorkerSignals()

    def run(self) -> None:
        out = self.pipeline.process_image(
            image_rgb=self.image_rgb,
            config=self.config,
            scale_x=self.scale_x,
            scale_y=self.scale_y,
        )
        self.signals.finished.emit(self.job_id, out)


class _TextTranslateTask(QRunnable):
    def __init__(
        self,
        job_id: int,
        translator: TranslationEngine,
        text: str,
        config: AppConfig,
    ) -> None:
        super().__init__()
        self.job_id = job_id
        self.translator = translator
        self.text = text
        self.config = config
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            res = self.translator.translate(
                text=self.text,
                source_lang=self.config.source_lang,
                target_lang=self.config.target_lang,
                provider=self.config.translator_provider,
                gemini_api_key=self.config.gemini_api_key,
                gemini_model=self.config.gemini_model,
            )
            self.signals.finished.emit(self.job_id, (self.text, res, ""))
        except Exception as exc:
            self.signals.finished.emit(self.job_id, (self.text, None, str(exc)))


class ScreenTranslatorApp(QObject):
    """Ứng dụng dịch trực tiếp trên màn hình (Anh - Việt - Trung & mở rộng)."""

    _ocr_status_signal = Signal(str)

    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.qt_app.setApplicationName(APP_NAME)
        self.qt_app.setWindowIcon(create_app_icon(64))
        self.qt_app.setStyleSheet(DARK_GLASS_QSS)

        self.config = AppConfig.load()
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(4)
        self._active_workers: set = set()

        self._ocr_status_signal.connect(self._on_status_message)
        self.ocr = MultilingualOCREngine(status_cb=lambda msg: self._ocr_status_signal.emit(msg))
        self.translator = TranslationEngine()
        self.pipeline = ScreenTranslatePipeline(self.ocr, self.translator)

        # Trạng thái công việc
        self._snip_job_id = 0
        self._snip_rect = QRect()
        self._live_active = False
        self._live_busy = False
        self._live_job_id = 0
        self._live_force_refresh = True
        self._differ = FrameDiffer()
        self._manual_job_id = 0

        # Khởi tạo các cửa sổ UI
        self.control_bar = ControlBar(self.config)
        self.snip_overlay = SnipOverlay()
        self.inplace_overlay = InPlaceOverlay()
        self.live_frame = LiveCaptureFrame()
        self.live_subtitle = LiveSubtitleWindow()
        self.history_panel = HistoryPanel()

        self._restore_positions()
        self._wire_signals()
        self._setup_tray()
        self._setup_hotkeys()

        # Bộ đếm thời gian cho Live Mode
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._on_live_tick)

        self.qt_app.aboutToQuit.connect(self._cleanup)

    def _dispatch_worker(self, task, slot) -> None:
        """Chạy QRunnable an toàn trên QThreadPool và giữ tham chiếu signals cho đến khi slot hoàn tất."""
        task.setAutoDelete(False)
        self._active_workers.add(task)

        def _done(job_id: int, payload: object) -> None:
            self._active_workers.discard(task)
            slot(job_id, payload)

        task.signals.finished.connect(_done)
        self.pool.start(task)

    def start(self) -> None:
        self.control_bar.show()
        self.control_bar.set_status("Đang nạp mô hình nhận diện chữ (Anh / Việt / Trung)...", "#38BDF8")

        # Nạp sẵn OCR ở luồng nền để lần dịch đầu tiên phản hồi ngay lập tức
        task = _WarmupTask(self.ocr, fast_mode=self.config.ocr_fast_mode)
        self._dispatch_worker(task, self._on_warmup_done)

    def _restore_positions(self) -> None:
        primary = QGuiApplication.primaryScreen()
        geo = primary.availableGeometry() if primary else QRect(0, 0, 1920, 1080)

        if self.config.bar_x >= 0 and self.config.bar_y >= 0:
            x = max(geo.left(), min(self.config.bar_x, geo.right() - self.control_bar.width()))
            y = max(geo.top(), min(self.config.bar_y, geo.bottom() - self.control_bar.height()))
            self.control_bar.move(x, y)
        else:
            cx = geo.left() + (geo.width() - self.control_bar.width()) // 2
            cy = geo.top() + 22
            self.control_bar.move(cx, cy)

        lr = self.config.live_region
        if len(lr) == 4:
            self.live_frame.set_capture_rect(QRect(lr[0], lr[1], max(200, lr[2]), max(70, lr[3])))
        else:
            self.live_frame.set_capture_rect(QRect(geo.left() + 260, geo.bottom() - 320, 720, 150))

        sp = self.config.subtitle_pos
        if len(sp) == 4:
            self.live_subtitle.setGeometry(sp[0], sp[1], max(320, sp[2]), max(95, sp[3]))
        else:
            self.live_subtitle.setGeometry(geo.left() + 260, geo.bottom() - 155, 720, 130)

        self.live_subtitle.apply_appearance(
            self.config.live_overlay_opacity,
            self.config.live_font_size,
            self.config.live_show_original,
        )

    def _wire_signals(self) -> None:
        self.control_bar.snip_requested.connect(self._start_snip)
        self.control_bar.live_toggled.connect(self._toggle_live)
        self.control_bar.history_toggled.connect(self._toggle_history)
        self.control_bar.settings_requested.connect(self._open_settings)
        self.control_bar.languages_changed.connect(self._on_languages_changed)
        self.control_bar.minimize_to_tray_requested.connect(self._minimize_to_tray)
        self.control_bar.quit_requested.connect(self.qt_app.quit)
        self.control_bar.position_changed.connect(self._on_bar_moved)

        self.snip_overlay.region_selected.connect(self._on_snip_selected)
        self.snip_overlay.cancelled.connect(self._on_snip_cancelled)

        self.live_frame.region_changed.connect(self._on_live_region_changed)
        self.live_frame.pause_toggled.connect(self._on_live_pause_toggled)
        self.live_frame.direct_mode_toggled.connect(self._on_live_direct_toggled)
        self.live_frame.closed.connect(self._stop_live)

        self.live_subtitle.geometry_changed.connect(self._on_subtitle_moved)
        self.history_panel.retranslate_requested.connect(self._on_manual_translate)

    def _setup_tray(self) -> None:
        self.tray = QSystemTrayIcon(create_app_icon(64), self.qt_app)
        self.tray.setToolTip(f"{APP_NAME} — Alt+Q: Quét dịch | Alt+W: Dịch trực tiếp")

        menu = QMenu()
        act_show = QAction("Hiện thanh điều khiển", menu)
        act_show.triggered.connect(self._show_control_bar)
        act_snip = QAction("Quét vùng & dịch (Alt+Q)", menu)
        act_snip.triggered.connect(self._start_snip)
        act_live = QAction("Bật / Tắt Dịch trực tiếp (Alt+W)", menu)
        act_live.triggered.connect(self._toggle_live)
        act_hist = QAction("Bảng kết quả & Lịch sử", menu)
        act_hist.triggered.connect(self._toggle_history)
        act_settings = QAction("Cài đặt...", menu)
        act_settings.triggered.connect(self._open_settings)
        act_quit = QAction("Thoát phần mềm", menu)
        act_quit.triggered.connect(self.qt_app.quit)

        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_snip)
        menu.addAction(act_live)
        menu.addAction(act_hist)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _setup_hotkeys(self) -> None:
        self.hotkeys = GlobalHotkeyManager()
        self.qt_app.installNativeEventFilter(self.hotkeys)
        ok_q = self.hotkeys.register(MOD_ALT, VK_Q, self._start_snip)
        ok_w = self.hotkeys.register(MOD_ALT, VK_W, self._toggle_live)
        ok_s = self.hotkeys.register(MOD_ALT, VK_S, self._toggle_overlay_or_unlock)
        if not ok_q or not ok_w or not ok_s:
            self._on_status_message(
                "Lưu ý: Một số phím tắt Alt+Q/W/S đang được ứng dụng khác dùng; bạn vẫn có thể bấm nút trực tiếp."
            )

    def _on_status_message(self, msg: str) -> None:
        self.control_bar.set_status(msg, "#38BDF8")

    def _on_warmup_done(self, _id: int, status: object) -> None:
        s = str(status)
        if s == "ready":
            self.control_bar.set_status(
                "Sẵn sàng (Anh / Việt / Trung)  •  Alt+Q: Quét dịch  |  Alt+W: Dịch trực tiếp  |  Alt+S: Mở khóa/Ẩn",
                "#6EE7B7",
            )
        else:
            self.control_bar.set_status(f"Cảnh báo khởi tạo OCR: {s}", "#FBBF24")

    # ---------------- Chế độ 1: Quét vùng & Dịch đè trực tiếp ----------------

    def _start_snip(self) -> None:
        self.inplace_overlay.hide()
        self.control_bar.set_status("Kéo chuột chọn vùng chữ trên màn hình (nhấn Esc để hủy)...", "#38BDF8")
        QTimer.singleShot(40, self.snip_overlay.start_snip)

    def _on_snip_cancelled(self) -> None:
        self.control_bar.set_status("Đã hủy chọn vùng.", "#94A3B8")

    def _on_snip_selected(self, rect: QRect, image_rgb: object, scale_x: float, scale_y: float) -> None:
        if not isinstance(image_rgb, np.ndarray):
            return
        self._snip_job_id += 1
        job_id = self._snip_job_id
        self._snip_rect = QRect(rect)

        if self.config.snip_display_mode in ("inplace", "both"):
            self.inplace_overlay.show_loading(rect, "⏳ Đang nhận diện & dịch...")

        self.control_bar.set_status("Đang nhận diện chữ và dịch...", "#38BDF8")
        cfg_snap = copy.deepcopy(self.config)
        task = _PipelineTask(job_id, self.pipeline, image_rgb, cfg_snap, scale_x, scale_y)
        self._dispatch_worker(task, self._on_snip_finished)

    def _on_snip_finished(self, job_id: int, out: object) -> None:
        if job_id != self._snip_job_id or not isinstance(out, PipelineOutput):
            return

        if out.error:
            self.inplace_overlay.hide()
            self.control_bar.set_status(out.error, "#FB7185")
            return

        if not out.blocks:
            if self.config.snip_display_mode in ("inplace", "both"):
                self.inplace_overlay.show_blocks(self._snip_rect, [], "Không thấy chữ")
            self.control_bar.set_status("Không phát hiện chữ trong vùng đã chọn.", "#FBBF24")
            return

        src_badge = LANG_BADGES.get(out.detected_lang, out.detected_lang.upper() or "AUTO")
        tgt_badge = LANG_BADGES.get(self.config.target_lang, self.config.target_lang.upper())
        pair_label = f"{src_badge} → {tgt_badge}"
        total_sec = (out.ocr_ms + out.translate_ms) / 1000.0
        info = f"{pair_label}  •  {total_sec:.2f}s"

        if self.config.snip_display_mode in ("inplace", "both"):
            self.inplace_overlay.show_blocks(self._snip_rect, out.blocks, info)

        self.history_panel.add_result(
            original=out.full_original,
            translated=out.full_translated,
            lang_pair=pair_label,
            info_text=info,
            record_history=True,
        )

        if self.config.snip_display_mode in ("panel", "both"):
            self._show_history_near_bar()

        if self.config.auto_copy and out.full_translated.strip():
            QApplication.clipboard().setText(out.full_translated)
            self.control_bar.set_status(f"Đã dịch ({info}) & sao chép vào Clipboard.", "#6EE7B7")
        else:
            self.control_bar.set_status(
                f"Đã dịch xong ({info})  •  Nhấn vào đoạn dịch để sao chép hoặc Esc để đóng.",
                "#6EE7B7",
            )

    # ---------------- Chế độ 2: Dịch trực tiếp liên tục (Live Mode) ----------------

    def _toggle_live(self) -> None:
        if self._live_active:
            self._stop_live()
        else:
            self._start_live()

    def _start_live(self) -> None:
        self._live_active = True
        self._live_force_refresh = True
        self._differ.reset()
        self.control_bar.set_live_active(True)
        self.live_frame.show()
        self.live_frame.raise_()
        if not self.live_frame.is_direct_overlay():
            self.live_subtitle.show()
            self.live_subtitle.raise_()
        self._live_timer.start(self.config.live_interval_ms)
        self.control_bar.set_status(
            "Dịch trực tiếp đang bật  •  Kéo khung xanh lên phụ đề/game/văn bản để tự động dịch!",
            "#6EE7B7",
        )
        QTimer.singleShot(120, self._on_live_tick)

    def _stop_live(self) -> None:
        self._live_active = False
        self._live_timer.stop()
        self.live_frame.hide()
        self.live_subtitle.hide()
        self.control_bar.set_live_active(False)
        self.control_bar.set_status("Đã tắt chế độ Dịch trực tiếp.", "#94A3B8")

    def _on_live_region_changed(self, rect: QRect) -> None:
        self.config.live_region = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.config.save()
        self._live_force_refresh = True
        self._differ.reset()

    def _on_subtitle_moved(self, rect: QRect) -> None:
        self.config.subtitle_pos = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.config.save()

    def _on_live_pause_toggled(self, paused: bool) -> None:
        if not paused:
            self._live_force_refresh = True
            self._differ.reset()
            QTimer.singleShot(80, self._on_live_tick)

    def _on_live_direct_toggled(self, direct_mode: bool) -> None:
        if direct_mode:
            self.live_subtitle.hide()
            self.control_bar.set_status(
                "Đang hiển thị bản dịch đè trực tiếp trong khung quét!", "#38BDF8"
            )
        else:
            if self._live_active:
                self.live_subtitle.show()
            self.control_bar.set_status(
                "Đang hiển thị bản dịch trên khung phụ đề nổi.", "#6EE7B7"
            )
        self._live_force_refresh = True

    def _on_live_tick(self) -> None:
        if not self._live_active or self._live_busy or self.live_frame.is_paused():
            return
        if not self.live_frame.isVisible():
            return

        rect = self.live_frame.get_capture_rect()
        cap = capture_logical_rect(rect)
        if cap is None:
            return

        if not self._live_force_refresh and not self._differ.has_changed(cap.image_rgb):
            return

        self._live_force_refresh = False
        self._live_busy = True
        self._live_job_id += 1
        job_id = self._live_job_id

        cfg_snap = copy.deepcopy(self.config)
        task = _PipelineTask(job_id, self.pipeline, cap.image_rgb, cfg_snap, cap.scale_x, cap.scale_y)
        self._dispatch_worker(task, self._on_live_finished)

    def _on_live_finished(self, job_id: int, out: object) -> None:
        self._live_busy = False
        if not self._live_active or job_id != self._live_job_id or not isinstance(out, PipelineOutput):
            return

        if out.error:
            self.live_subtitle.update_translation("", f"⚠ {out.error}", "Lỗi dịch trực tiếp")
            return

        if not out.blocks:
            self.live_frame.set_blocks([])
            self.live_subtitle.update_translation("", "", "Dịch trực tiếp • Không thấy chữ trong khung")
            return

        src_badge = LANG_BADGES.get(out.detected_lang, out.detected_lang.upper() or "AUTO")
        tgt_badge = LANG_BADGES.get(self.config.target_lang, self.config.target_lang.upper())
        pair = f"{src_badge} → {tgt_badge}"
        total_sec = (out.ocr_ms + out.translate_ms) / 1000.0
        meta = f"● Trực tiếp  •  {pair}  •  {total_sec:.2f}s"

        self.live_frame.set_blocks(out.blocks)
        self.live_subtitle.update_translation(out.full_original, out.full_translated, meta)
        self.history_panel.add_result(
            original=out.full_original,
            translated=out.full_translated,
            lang_pair=pair,
            info_text=meta,
            record_history=True,
        )

    # ---------------- Dịch nhập tay / Cài đặt / Khay hệ thống ----------------

    def _on_manual_translate(self, text: str) -> None:
        self._manual_job_id += 1
        job_id = self._manual_job_id
        self.control_bar.set_status("Đang dịch văn bản...", "#38BDF8")
        task = _TextTranslateTask(job_id, self.translator, text, copy.deepcopy(self.config))
        self._dispatch_worker(task, self._on_manual_finished)

    def _on_manual_finished(self, job_id: int, payload: object) -> None:
        if job_id != self._manual_job_id or not isinstance(payload, tuple):
            return
        orig, res, err = payload
        if err or res is None:
            self.control_bar.set_status(f"Lỗi dịch thuật: {err}", "#FB7185")
            return
        src_badge = LANG_BADGES.get(res.detected_lang, res.detected_lang.upper() or "AUTO")
        tgt_badge = LANG_BADGES.get(self.config.target_lang, self.config.target_lang.upper())
        pair = f"{src_badge} → {tgt_badge}"
        self.history_panel.add_result(orig, res.translated_text, pair, pair, record_history=True)
        self.control_bar.set_status(f"Đã dịch ({pair}).", "#6EE7B7")

    def _on_languages_changed(self, src: str, tgt: str) -> None:
        self.config.source_lang = src
        self.config.target_lang = tgt
        self.config.save()
        self._live_force_refresh = True
        self._differ.reset()
        src_b = LANG_BADGES.get(src, src)
        tgt_b = LANG_BADGES.get(tgt, tgt)
        self.control_bar.set_status(f"Đã chuyển hướng dịch: {src_b} → {tgt_b}", "#38BDF8")

    def _toggle_history(self) -> None:
        if self.history_panel.isVisible():
            self.history_panel.hide()
        else:
            self._show_history_near_bar()

    def _show_history_near_bar(self) -> None:
        if not self.history_panel.isVisible():
            bx = self.control_bar.x()
            by = self.control_bar.y() + self.control_bar.height() + 10
            screen = QGuiApplication.screenAt(self.control_bar.pos()) or QGuiApplication.primaryScreen()
            s_geo = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
            if by + self.history_panel.height() > s_geo.bottom():
                by = max(s_geo.top() + 10, self.control_bar.y() - self.history_panel.height() - 10)
            bx = max(s_geo.left() + 10, min(bx, s_geo.right() - self.history_panel.width() - 10))
            self.history_panel.move(bx, by)
            self.history_panel.show()
        self.history_panel.raise_()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.control_bar)
        if dlg.exec():
            self._live_timer.setInterval(self.config.live_interval_ms)
            self.live_subtitle.apply_appearance(
                self.config.live_overlay_opacity,
                self.config.live_font_size,
                self.config.live_show_original,
            )
            self._live_force_refresh = True
            self.control_bar.set_status("Đã lưu cài đặt mới.", "#6EE7B7")

    def _toggle_overlay_or_unlock(self) -> None:
        if self.live_subtitle.is_click_through():
            self.live_subtitle.set_click_through_mode(False)
            self.control_bar.set_status("Đã mở khóa chuột cho khung phụ đề.", "#6EE7B7")
            return
        if self.inplace_overlay.isVisible():
            self.inplace_overlay.dismiss()
            return
        if self.control_bar.isVisible():
            self._minimize_to_tray()
        else:
            self._show_control_bar()

    def _minimize_to_tray(self) -> None:
        self.control_bar.hide()
        self.tray.showMessage(
            APP_NAME,
            "Phần mềm đang chạy ngầm ở khay hệ thống. Nhấn Alt+Q để quét dịch hoặc Alt+W để dịch trực tiếp!",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    def _show_control_bar(self) -> None:
        self.control_bar.show()
        self.control_bar.raise_()
        self.control_bar.activateWindow()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_control_bar()

    def _on_bar_moved(self, x: int, y: int) -> None:
        self.config.bar_x = x
        self.config.bar_y = y
        self.config.save()

    def _cleanup(self) -> None:
        self._live_timer.stop()
        self.hotkeys.unregister_all()
        self.translator.close()
        self.tray.hide()
        for widget in (
            self.snip_overlay,
            self.inplace_overlay,
            self.live_frame,
            self.live_subtitle,
            self.history_panel,
            self.control_bar,
        ):
            try:
                widget.close()
                widget.deleteLater()
            except Exception:
                pass
        self.config.save()


def run_app() -> int:
    qt_app = QApplication(sys.argv)
    controller = ScreenTranslatorApp(qt_app)
    controller.start()
    code = qt_app.exec()
    # Đảm bảo hủy mọi QWidget trước khi QApplication kết thúc
    del controller
    qt_app.processEvents()
    return code
