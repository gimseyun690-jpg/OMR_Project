from __future__ import annotations

import os
import cv2
import numpy as np
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMessageBox
from ui.scanner.popups.error_editor import ErrorCorrectionDialog
from logic.services.tasks.summary_tasks import ReviewSummaryTask


class ReviewFlowMixin:
    """오류 검토/수정 흐름."""

    def open_error_check(self, auto_next: bool = False):
        """오류 검사 버튼 클릭 시 실행 (필터 조건은 서비스에서 처리)."""
        if not self.current_db_path: 
            return

        # 1. DB에서 오류 큐 필터링
        check_blank = self.chk_all_blank.isChecked()
        check_etc = self.chk_etc_error.isChecked()
        self.error_queue = self.controller.build_error_queue(
            self.current_db_path, check_blank=check_blank, check_etc=check_etc
        )

        if not self.error_queue:
            QMessageBox.information(self, "완료", "검토할 오류가 없습니다.\n(설정 조건에 맞는 오류가 없음)")
            return

        # 3. 검토 루프 시작 (첫 오류부터)
        completed_all = self.run_review_loop(0)
        if completed_all:
            if auto_next and self.control_panel.chk_next.isChecked():
                QMessageBox.information(self, "검토 완료", "검토가 완료되었습니다. 다음 시험실로 이동합니다.")
                self._advance_room()
                self.start_scan()
            else:
                QMessageBox.information(self, "검토 완료", "검토가 완료되었습니다.")

    def run_review_loop(self, start_idx):
        """오류를 순회하며 검토하는 다이얼로그 루프."""
        current_idx = start_idx
        
        while 0 <= current_idx < len(self.error_queue):
            row = self.error_queue[current_idx]
            
            # (1) 데이터 준비
            read_num = row[1]
            image_path = row[4]
            result_str = row[6]
            
            # "103" -> [{"q_num":1, "marked":[0]}, ...] 변환
            scan_results = self.parse_result_string(result_str)

            # (2) 이미지 로드 (경로 직접)
            image_cv = None
            try:
                # numpy로 cv2 이미지 로드 (한글 경로 대응)
                img_array = np.fromfile(image_path, np.uint8)
                image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"이미지 로드 실패: {e}")

            # (3) 다이얼로그 실행
            dlg = ErrorCorrectionDialog(self, image_cv, scan_results, image_path)
            session_total = max(0, self.total_read - self.session_start_read_num + 1)
            dlg.lbl_idx.setText(f"{current_idx + 1}/{session_total}")  # 오류 순번/세션 총 검사 수
            
            # exec_() 호출 시 창을 닫을 때까지 대기
            dlg.exec_() 

            # (4) 종료 코드 확인 (Dialog에서 exit_code 설정 필요)
            exit_code = getattr(dlg, 'exit_code', 0)

            if exit_code == 0:  # 그냥 종료 (X버튼) -> 루프 종료
                break
            
            elif exit_code == 1:  # 저장(S) -> 다음으로
                self.save_corrected_data(row, dlg.scan_results)
                self.controller.update_review_done(self.current_db_path, read_num, 1)
                self._refresh_grid_row_by_read_num(read_num)
                next_idx = self._find_next_unreviewed_index(current_idx + 1, 1)
                if next_idx is None:
                    break
                current_idx = next_idx  # 미점검 다음 순번으로 이동

            elif exit_code == 2:  # 이전(<) -> 저장하지 않고 이전으로
                self.controller.update_review_done(self.current_db_path, read_num, 1)
                self._refresh_grid_row_by_read_num(read_num)
                current_idx -= 1
                if current_idx < 0:
                    QMessageBox.information(self, "알림", "첫 건입니다.")
                    current_idx = 0

            elif exit_code == 3:  # 다음(>) -> 저장하지 않고 다음으로
                self.controller.update_review_done(self.current_db_path, read_num, 1)
                self._refresh_grid_row_by_read_num(read_num)
                current_idx += 1

        # 루프 종료 후 통계 갱신
        self.update_statistics()
        if current_idx >= len(self.error_queue):
             return True
        return False

    def _find_next_unreviewed_index(self, start_idx: int, direction: int = 1):
        idx = start_idx
        while 0 <= idx < len(self.error_queue):
            row = self.error_queue[idx]
            read_num = row[1]
            db_row = self.controller.get_scan_by_read_num(self.current_db_path, read_num)
            review_done = db_row[13] if db_row and len(db_row) > 13 else 0
            if not review_done:
                return idx
            idx += direction
        return None

    def parse_result_string(self, result_str):
        """결과 문자열 "103"을 검사용 리스트로 변환."""
        parsed = []
        for i, char in enumerate(result_str):
            marked = []
            status = "정상"
            
            if char == '1': marked = [0]       # 찬성
            elif char == '2': marked = [1]     # 반대
            elif char == '3':                  # 중복
                marked = [0, 1]
                status = "중복"
            elif char == '0':                  # 공백
                marked = []
                status = "공백"
            
            parsed.append({'q_num': i+1, 'marked': marked, 'status': status})
        return parsed

    def save_corrected_data(self, original_row, modified_results):
        """수정된 결과를 서비스로 저장."""
        if not self.current_db_path:
            return
        self.controller.save_corrected_data(self.current_db_path, original_row, modified_results)

    def _open_review_for_row(self, row_data):
        if not row_data:
            return
        read_num = row_data[1]
        image_path = row_data[4]
        result_str = row_data[6]
        scan_results = self.parse_result_string(result_str)

        image_cv = None
        try:
            img_array = np.fromfile(image_path, np.uint8)
            image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"이미지 로드 실패: {e}")

        dlg = ErrorCorrectionDialog(self, image_cv, scan_results, image_path)
        dlg.lbl_idx.setText(str(read_num))
        dlg.exec_()

        exit_code = getattr(dlg, 'exit_code', 0)
        if exit_code == 1:
            self.save_corrected_data(row_data, dlg.scan_results)
            self.update_statistics()
            self._schedule_summary_refresh()
            self.controller.update_review_done(self.current_db_path, read_num, 1)
            self._refresh_grid_row_by_read_num(read_num)
        elif exit_code in (2, 3):
            self.controller.update_review_done(self.current_db_path, read_num, 1)
            self._refresh_grid_row_by_read_num(read_num)

    def update_review_summary(self):
        if not self.current_db_path:
            return
        task = ReviewSummaryTask(
            self.db,
            self.current_db_path,
            self.session_start_read_num,
            self.total_read,
        )
        task.signals.result.connect(self._apply_review_summary)
        task.signals.error.connect(self._on_summary_error)
        self.thread_pool.start(task)

    def _apply_review_summary(self, total_in_session, review_count, blank_cnt, dup_cnt, invalid_cnt, roster_missing_cnt, absent_cnt):
        if total_in_session > 0:
            self.lbl_check.setText(f"{review_count}/{total_in_session}")
            self.lbl_review_detail.setText(
                f"오류:{invalid_cnt}  중복:{dup_cnt}  공백:{blank_cnt}  "
                f"명단미등록{roster_missing_cnt}  결시:{absent_cnt}"
            )

    def _update_review_status_in_grid(self, read_num: int, status: str):
        for r in range(self.main_grid.rowCount()):
            item = self.main_grid.item(r, 0)
            if item and item.text() == str(read_num):
                cell = self.main_grid.item(r, 5)
                if cell:
                    cell.setText(status)
                    if status == "미점검":
                        cell.setForeground(Qt.red)
                    elif status == "완료":
                        cell.setForeground(Qt.blue)
                break

    def _refresh_grid_row_by_read_num(self, read_num: int):
        if not self.current_db_path:
            return
        row = self.controller.get_scan_by_read_num(self.current_db_path, read_num)
        if not row:
            return
        row_place = row[2]
        row_room = row[3]
        image_path = row[4]
        sheet_code = row[5]
        result_str = row[6]
        is_valid = row[7]
        error_message = row[9] if len(row) > 9 else ""
        review_done = row[13] if len(row) > 13 else 0

        if is_valid == 1:
            ui_status = ""
            review_status = "완료" if review_done else ""
            display_detail = ""
        else:
            ui_status = error_message if error_message else "오류"
            review_status = "완료" if review_done else "미점검"
            display_detail = result_str

        for r in range(self.main_grid.rowCount()):
            item = self.main_grid.item(r, 0)
            if item and item.text() == str(read_num):
                values = [
                    str(read_num),
                    str(sheet_code),
                    str(row_place),
                    str(row_room),
                    ui_status,
                    review_status,
                    str(display_detail),
                    str(image_path),
                    os.path.basename(image_path) if image_path else "",
                ]
                for c, value in enumerate(values):
                    cell = self.main_grid.item(r, c)
                    if not cell:
                        cell = self._item("")
                        self.main_grid.setItem(r, c, cell)
                    cell.setText(value)
                status_cell = self.main_grid.item(r, 5)
                if status_cell:
                    if review_status == "미점검":
                        status_cell.setForeground(Qt.red)
                    elif review_status == "완료":
                        status_cell.setForeground(Qt.blue)
                break





