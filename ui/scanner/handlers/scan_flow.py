from __future__ import annotations

import os
import cv2
import numpy as np
from PySide2.QtCore import Qt, Slot, QTimer
from PySide2.QtGui import QImage, QPixmap
from PySide2.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel
from logic.services.tasks.scan_tasks import ScanWorker, AnalyzeTask
from utils.path_utils import data_path
from ui.scanner.components.styles import ERROR_MSG


class ScanFlowMixin:
    """스캔/분석/결과 흐름."""

    def set_error_popups_enabled(self, enabled: bool):
        self.show_error_popups = bool(enabled)

    def _show_error_popup(self, title: str, message: str, critical: bool = False):
        if not self.show_error_popups:
            return
        if critical:
            QMessageBox.critical(self, title, message)
        else:
            QMessageBox.warning(self, title, message)

    def _set_last_error_message(self, message):
        if not hasattr(self, "lbl_last_error_msg"):
            return
        msg = (message or "").strip()
        if not msg:
            msg = "없음"
        self.lbl_last_error_msg.setText(msg)

    def start_scan(self):
        """스캔 버튼 클릭 시"""
        if self.scan_in_progress:
            return
        if self.current_db_path is None:
            QMessageBox.warning(self, "경고", "먼저 '파일 설정' 메뉴에서 사용할 DB 파일을 선택(열기)해주세요.")
            return
        # [추가] DB에서 이미지 저장 경로 불러오기
        default_path = data_path("scan_images")
        save_folder = default_path
        # DB 설정값이 없으면 기본값 사용
        if self.current_db_path:
            save_folder = self.controller.get_setting(self.current_db_path, "image_save_path", default_path)
            
        # 폴더가 없으면 생성
        if not os.path.exists(save_folder):
            try:
                os.makedirs(save_folder)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"폴더 생성 실패: {e}")
                return

        # [추가] 이번 스캔 세션 카운트 초기화
        self.current_session_count = 0
        try:
            self.next_read_num = int(self.controller.get_next_read_num(self.current_db_path))
        except Exception:
            self.next_read_num = int(getattr(self, "next_read_num", 1))
        self.session_start_read_num = self.next_read_num
        self.session_end_read_num = self.session_start_read_num - 1
        self.pending_results = {}
        self.next_emit_read_num = self.session_start_read_num
        self.pending_analyze = 0
        self.auto_next_pending = False
        self.current_summary_row = None
        self.session_start_room_text = self.cb_room.currentText()
        self._stop_requested = False

        # 새 시험실 스캔 시작 시 그리드 UI를 비워서 누적 표시를 방지
        if hasattr(self, "main_grid"):
            self.main_grid.setRowCount(0)

        # 마지막 스캔 설정 저장
        self.last_scan_params = {
            "form_index": self.cb_form.currentIndex(),
            "place_index": self.cb_place.currentIndex(),
            "room_index": self.cb_room.currentIndex(),
        }

        my_hwnd = int(self.winId())
        # [수정] 스캐너 생성 시 save_folder 전달
        dpi = getattr(self.pipeline, "dpi", 150)
        scanner_backend = str(self.controller.get_setting(self.current_db_path, "scanner_backend", "auto") or "auto").strip()
        scanner_source_hint = str(self.controller.get_setting(self.current_db_path, "scanner_source_hint", "") or "").strip()
        scanner_backend_order = str(self.controller.get_setting(self.current_db_path, "scanner_backend_order", "") or "").strip()
        self.worker = ScanWorker(
            my_hwnd,
            save_folder,
            dpi=dpi,
            scanner_backend=scanner_backend,
            scanner_source_hint=scanner_source_hint or None,
            scanner_backend_order=scanner_backend_order or None,
        )
        
        self.worker.image_scanned.connect(self.on_image_received)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_scan.setText("스캔중...")
        self.control_panel.btn_next.setEnabled(False)
        self.control_panel.btn_stop.setEnabled(True)
        self.control_panel.btn_retry.setEnabled(False)
        self.scan_in_progress = True
        self.worker.start()

    @Slot(str)
    def on_image_received(self, image_path):
        if getattr(self, "_stop_requested", False):
            return
        read_num = int(getattr(self, "next_read_num", 1))
        self.next_read_num = read_num + 1
        self.session_end_read_num = read_num
        self.total_read += 1
        self.current_session_count += 1  # 현재 세션 카운트

        if hasattr(self.control_panel, "image_viewer"):
            self.control_panel.image_viewer.set_image_path(
                image_path, engine=getattr(self, "pipeline", None).engine if hasattr(self, "pipeline") else None, use_warp=True
            )

        task = AnalyzeTask(
            controller=self.controller,
            image_path=image_path,
            read_num=read_num,
            place=self.cb_place.currentText(),
            room=self.cb_room.currentText(),
        )
        self.pending_analyze += 1
        task.signals.result.connect(self._on_analyze_result)
        task.signals.error.connect(self._on_analyze_error)
        self.thread_pool.start(task)

    def _on_analyze_result(self, row_data):
        self.pending_analyze = max(self.pending_analyze - 1, 0)
        if not isinstance(row_data, (list, tuple)):
            self._set_last_error_message("분석 결과 형식이 잘못되어 건너뜀")
            if self.pending_analyze == 0:
                self._maybe_start_auto_review()
            return
        try:
            read_num = int(row_data[0])
        except Exception:
            read_num = None

        # 이전 시험실의 지연된 결과는 현재 그리드에 섞지 않음
        if read_num is not None and hasattr(self, "session_start_read_num"):
            if read_num < self.session_start_read_num:
                if self.pending_analyze == 0:
                    self._maybe_start_auto_review()
                return

        if read_num is None:
            self._append_row(row_data)
        else:
            self.pending_results[read_num] = row_data
            self._flush_pending_results()

        if self.pending_analyze == 0:
            self._maybe_start_auto_review()

    def _on_analyze_error(self, msg):
        self.pending_analyze = max(self.pending_analyze - 1, 0)
        self._set_last_error_message(msg)
        self._show_error_popup("오류", msg)
        if self.pending_analyze == 0:
            self._maybe_start_auto_review()

    def _flush_pending_results(self):
        while self.next_emit_read_num in self.pending_results:
            row_data = self.pending_results.pop(self.next_emit_read_num)
            self._append_row(row_data)
            self.next_emit_read_num += 1

    def _append_row(self, row_data):
        if not isinstance(row_data, (list, tuple)):
            return
        if len(row_data) > 5 and row_data[5] == "타이밍 마크 오류":
            self._show_timing_mark_error(row_data[7], row_data[5])
        if len(row_data) > 5 and row_data[5] != "완료":
            err_msg = row_data[5] if len(row_data) > 5 else "오류"
            self._set_last_error_message(err_msg)
        self.main_grid.add_row_data(row_data)
        self.lbl_total.setText(str(self.total_read))        # 전체 누적
        self.lbl_cur_cnt.setText(str(self.current_session_count))  # 현재 세션만
        self._update_summary_count()
        self.main_grid.scrollToBottom()

    def _show_timing_mark_error(self, image_path, message):
        dlg = QDialog(self)
        dlg.setWindowTitle("타이밍 마크 오류")
        layout = QVBoxLayout(dlg)

        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet(ERROR_MSG)
        layout.addWidget(lbl_msg)

        img = None
        try:
            img_array = np.fromfile(image_path, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception:
            img = None

        if img is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            bytes_per_line = w * 3
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
            pixmap = QPixmap.fromImage(qimg)
            max_w = 900
            if pixmap.width() > max_w:
                pixmap = pixmap.scaledToWidth(max_w, Qt.SmoothTransformation)
            lbl_img = QLabel()
            lbl_img.setPixmap(pixmap)
            lbl_img.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl_img)

        dlg.resize(920, 600)
        dlg.exec_()
    


    def on_finished(self):
        if getattr(self, "_stop_requested", False):
            self._stop_requested = False
            self.reset_ui_state()
            self.control_panel.btn_retry.setEnabled(False)
            self.update_review_summary()
            QMessageBox.information(self, "중단", "스캔이 중단되었습니다.")
            return

        # [수정] 요약 테이블 갱신
        place = self.cb_place.currentText()
        room = self.cb_room.currentText()
        count = str(self.current_session_count)
        self._upsert_summary_count(place, room, int(count))
        self.current_summary_row = None
        self.reload_grid_from_db(place=place, room=room)
        
        if self.control_panel.chk_next.isChecked():
            QMessageBox.information(self, "완료", f"{place} - {room} 시험실 스캔 완료\n(총 {count}매)")
            self.reset_ui_state()
            self.control_panel.btn_retry.setEnabled(False)
            self.update_review_summary()
            self.auto_next_pending = True
            self._maybe_start_auto_review()
        else:
            QMessageBox.information(self, "완료", f"{place} - {room} 시험실 스캔 완료\n(총 {count}매)")
            self.reset_ui_state()
            self.control_panel.btn_retry.setEnabled(False)
            self.update_review_summary()
    @Slot(str)
    def on_error(self, msg):
        self._stop_requested = False
        code, retryable, auto_retry, user_msg = self._parse_scan_error(msg)
        self.last_error_code = code

        if user_msg:
            self._set_last_error_message(user_msg)
            self._show_error_popup("오류", user_msg)
        else:
            self._set_last_error_message(msg)
            self._show_error_popup("오류", msg)

        if retryable:
            self.control_panel.btn_retry.setEnabled(True)

        self.reset_ui_state()
        if auto_retry and self.control_panel.chk_auto_retry.isChecked():
            QTimer.singleShot(500, self.retry_last_scan)

    def reset_ui_state(self):
        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_scan.setText("현재시험실 스캔(R)")
        self.control_panel.btn_next.setEnabled(True)
        self.control_panel.btn_stop.setEnabled(False)
        self.scan_in_progress = False

    def scan_next_room(self):
        if self.scan_in_progress:
            return
        self._advance_room()
        self.start_scan()

    def stop_scan(self):
        if not self.scan_in_progress:
            return
        self._stop_requested = True
        self.control_panel.btn_stop.setEnabled(False)
        if self.worker:
            try:
                self.worker.stop()
            except Exception as e:
                print(f"[SCAN] 중단 실패: {e}")

    def retry_last_scan(self):
        if self.scan_in_progress:
            return
        if not self.last_scan_params:
            QMessageBox.information(self, "재시도", "이전 스캔 정보가 없습니다.")
            return
        try:
            self.cb_form.setCurrentIndex(self.last_scan_params.get("form_index", 0))
            self.cb_place.setCurrentIndex(self.last_scan_params.get("place_index", 0))
            self.cb_room.setCurrentIndex(self.last_scan_params.get("room_index", 0))
        except Exception as e:
            print(f"[SCAN] 마지막 스캔 파라미터 복원 실패: {e}")
        self.control_panel.btn_retry.setEnabled(False)
        self.start_scan()

    def _parse_scan_error(self, msg):
        if not msg or not isinstance(msg, str):
            return "", False, False, ""
        if not msg.startswith("SCAN_ERR|"):
            return "", False, False, ""
        try:
            _, code, retryable, auto_retry, user_msg = msg.split("|", 4)
            return code, retryable == "1", auto_retry == "1", user_msg
        except Exception:
            return "", False, False, ""

    def _maybe_start_auto_review(self):
        if self.auto_next_pending and self.pending_analyze == 0:
            self.auto_next_pending = False
            self.open_error_check(auto_next=True)

    def _advance_room(self):
        current_idx = self.cb_room.currentIndex()
        if current_idx < self.cb_room.count() - 1:
            self.cb_room.setCurrentIndex(current_idx + 1)
            # currentTextChanged 시 레이블 자동 갱신
            self.lbl_cur_room.setText(self.cb_room.currentText())




