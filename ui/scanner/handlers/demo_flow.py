from __future__ import annotations

import os

from PySide2.QtCore import Qt, Slot
from PySide2.QtWidgets import QProgressDialog, QMessageBox, QFileDialog
from logic.services.tasks.scan_tasks import DemoWorker


class DemoFlowMixin:
    """데모 이미지 폴더 처리 흐름."""

    def run_demo_folder(self):
        if self.current_db_path is None:
            QMessageBox.warning(self, "경고", "먼저 DB파일을 선택(파일 설정)해주세요.")
            return
        form_path = self.cb_form.currentData() if hasattr(self, "cb_form") else None
        if not form_path:
            QMessageBox.warning(self, "경고", "스캔할 OMR 양식을 먼저 선택해주세요.")
            return
        self.pipeline.set_form_path(form_path)
        folder = QFileDialog.getExistingDirectory(self, "이미지 폴더 선택")
        if not folder:
            return

        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]
        files.sort()

        if not files:
            QMessageBox.information(self, "알림", "선택한 폴더에 이미지가 없습니다.")
            return

        # 이미지 불러오기 시 현재 시험실 유지

        # UI 잠금
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_check.setEnabled(False)
        self.control_panel.btn_demo.setEnabled(False)
        self.control_panel.btn_demo.setText("이미지 불러오는 중...")

        current_place = self.cb_place.currentText()
        current_room = self.cb_room.currentText()
        self.current_session_count = 0
        self.session_start_read_num = self.total_read + 1
        self.pending_results = {}
        self.next_emit_read_num = self.session_start_read_num
        self.pending_analyze = 0
        self.auto_next_pending = False
        self.current_summary_row = None
        self.session_start_room_text = self.cb_room.currentText()
        self.last_scan_params = {
            "form_index": self.cb_form.currentIndex(),
            "place_index": self.cb_place.currentIndex(),
            "room_index": self.cb_room.currentIndex(),
        }

        # 진행 표시 다이얼로그
        self.demo_progress = QProgressDialog("이미지 읽기 준비중...", "취소", 0, len(files), self)
        self.demo_progress.setWindowTitle("이미지 불러오기")
        self.demo_progress.setWindowModality(Qt.WindowModal)
        self.demo_progress.setAutoClose(False)
        self.demo_progress.setAutoReset(False)
        self.demo_progress.show()

        # 워커 생성
        start_read_num = self.total_read
        self.demo_worker = DemoWorker(
            controller=self.controller,
            files=files,
            place=current_place,
            room=current_room,
            start_read_num=start_read_num
        )

        # 연결
        self.demo_progress.canceled.connect(self.demo_worker.cancel)
        self.demo_worker.progress.connect(self._on_demo_progress)
        self.demo_worker.result_row.connect(self._on_demo_row)
        self.demo_worker.finished.connect(self._on_demo_finished)
        self.demo_worker.error.connect(self._on_demo_error)

        self.demo_worker.start()

    def _on_demo_progress(self, current, total, filename):
        if hasattr(self, "demo_progress") and self.demo_progress:
            self.demo_progress.setMaximum(total)
            self.demo_progress.setValue(current)
            self.demo_progress.setLabelText(f"이미지 불러오는 중... ({current}/{total})\n{filename}")

    def _on_demo_row(self, row_data):
        # UI에 결과 반영 (메인 스레드)
        self.main_grid.add_row_data(row_data)
        self.total_read = int(row_data[0])  # read_num 諛섏쁺
        self.current_session_count += 1
        if len(row_data) > 7 and hasattr(self.control_panel, "image_viewer"):
            self.control_panel.image_viewer.set_image_path(
                row_data[7], engine=getattr(self, "pipeline", None).engine if hasattr(self, "pipeline") else None, use_warp=True
            )
        self.lbl_total.setText(str(self.total_read))
        self.lbl_cur_cnt.setText(str(self.current_session_count))
        self.control_panel.txt_temp.setText(str(self.total_read))
        self.main_grid.scrollToBottom()

    def _on_demo_finished(self, ok, fail):
        # UI 복원
        if hasattr(self, "demo_progress") and self.demo_progress:
            self.demo_progress.close()

        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_check.setEnabled(True)
        self.control_panel.btn_demo.setEnabled(True)
        self.control_panel.btn_demo.setText("이미지 불러오기")

        try:
            self.reload_grid_from_db()
            self.update_statistics()
            self._schedule_summary_refresh()
        except Exception as e:
            print(f"[DEMO] 그리드/통계 갱신 실패: {e}")

        place = self.cb_place.currentText()
        room = self.cb_room.currentText()
        count = str(self.current_session_count)
        self._upsert_summary_count(place, room, int(count))
        self.reload_grid_from_db(place=place, room=room)

        fail_samples = []
        if hasattr(self, "demo_worker") and getattr(self.demo_worker, "error_samples", None):
            fail_samples = self.demo_worker.error_samples[:3]

        if ok == 0 and fail > 0:
            detail = "\n".join(fail_samples)
            first_error = getattr(self.demo_worker, "first_error", "") if hasattr(self, "demo_worker") else ""
            msg = f"이미지 판독에 모두 실패했습니다. (성공 {ok} / 실패 {fail})"
            if first_error:
                msg += f"\n\n원인: {first_error}"
            if detail:
                msg += f"\n\n실패 예시:\n{detail}"
            self._set_last_error_message(first_error or "이미지 판독 실패")
            self._show_error_popup("이미지 불러오기 실패", msg, critical=True)
            return

        if fail > 0 and fail_samples:
            QMessageBox.warning(
                self,
                "이미지 불러오기 완료(일부 실패)",
                f"성공 {ok} / 실패 {fail}\n\n실패 예시:\n" + "\n".join(fail_samples),
            )
        else:
            QMessageBox.information(self, "이미지 불러오기 완료", f"성공 {ok} / 실패 {fail}")

    def _on_demo_error(self, msg):
        if hasattr(self, "demo_progress") and self.demo_progress:
            self.demo_progress.close()

        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_check.setEnabled(True)
        self.control_panel.btn_demo.setEnabled(True)
        self.control_panel.btn_demo.setText("이미지 불러오기")

        self._set_last_error_message(msg)
        self._show_error_popup("이미지 불러오기 오류", msg, critical=True)

