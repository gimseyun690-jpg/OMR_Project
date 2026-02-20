from __future__ import annotations

import os
import traceback
import cv2
import numpy as np
from PySide2.QtCore import Qt
from PySide2.QtWidgets import QMessageBox
from ui.scanner.popups.error_editor_score import ScoreErrorCorrectionDialog
from ui.scanner.popups.error_editor_church import ChurchErrorCorrectionDialog
from ui.scanner.popups.error_editor_rebuild import RebuildErrorCorrectionDialog
from logic.services.tasks.summary_tasks import ReviewSummaryTask


class ReviewFlowMixin:
    """오류 검토/수정 흐름."""

    def _extract_review_row_fields(self, row):
        if not isinstance(row, (list, tuple)):
            raise ValueError(f"잘못된 데이터 형식: {type(row)}")
        if len(row) <= 6:
            raise ValueError(f"DB 행 컬럼 수 부족: {len(row)}")
        try:
            read_num = int(row[1])
        except Exception as e:
            raise ValueError(f"판독번호 파싱 실패: {row[1]}") from e
        image_path = str(row[4] or "").strip()
        result_str = str(row[6] or "")
        return read_num, image_path, result_str

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
            if auto_next and self.control_panel.chk_next.isChecked():
                self.scan_next_room()
            return

        # 3. 검토 루프 시작 (첫 오류부터)
        completed_all = self.run_review_loop(0)
        if completed_all:
            QMessageBox.information(self, "검토 완료", "검토가 완료되었습니다.")
            if auto_next and self.control_panel.chk_next.isChecked():
                self.scan_next_room()

    def run_review_loop(self, start_idx):
        """오류를 순회하며 검토하는 다이얼로그 루프."""
        current_idx = start_idx

        while 0 <= current_idx < len(self.error_queue):
            row = self.error_queue[current_idx]

            # (1) 데이터 준비
            try:
                read_num, image_path, result_str = self._extract_review_row_fields(row)
            except Exception as e:
                print(f"[REVIEW] 행 데이터 파싱 실패: {e}")
                self._set_last_error_message(str(e))
                current_idx += 1
                continue

            # "103" -> [{"q_num":1, "marked":[0]}, ...] 변환
            scan_results = self.parse_result_string(result_str)

            if not image_path or not os.path.exists(image_path):
                msg = f"이미지 경로를 찾을 수 없어 검토를 건너뜁니다. (판독번호 {read_num})"
                print(f"[REVIEW] {msg}: {image_path}")
                self._set_last_error_message(msg)
                current_idx += 1
                continue

            # (2) 이미지 로드 (경로 직접)
            image_cv = None
            try:
                # numpy로 cv2 이미지 로드 (한글 경로 대응)
                img_array = np.fromfile(image_path, np.uint8)
                image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"이미지 로드 실패: {e}")
                self._set_last_error_message(str(e))
            if image_cv is None:
                msg = f"이미지 디코드 실패로 검토를 건너뜁니다. (판독번호 {read_num})"
                print(f"[REVIEW] {msg}")
                self._set_last_error_message(msg)
                current_idx += 1
                continue

            # (3) 다이얼로그 실행 (정렬+디버그 오버레이)
            debug_img = image_cv
            try:
                if image_cv is not None and hasattr(self, "pipeline"):
                    aligned_img, _, _ = self.pipeline.engine.align_image_warp(image_cv)
                    if aligned_img is not None:
                        layout_mode = self.pipeline.form_manager.get_layout_mode()
                        scale = self.pipeline._get_scale_factor()
                        if self.pipeline._is_new_marker_schema():
                            questions = (
                                self.pipeline.engine.parse_config(self.pipeline.form_data)
                                if "question_groups" in self.pipeline.form_data
                                else self.pipeline.form_data.get("questions", [])
                            )
                            question_layout = self.pipeline.form_data.get("question_layout", {}) or {}
                            marker_location = self.pipeline.form_data.get("marker_location", "left")
                            _, _, debug_img, _ = self.pipeline.engine.analyze_marker_questions(
                                aligned_img,
                                questions,
                                question_layout,
                                scale=scale,
                                marker_location=marker_location,
                            )
                        elif layout_mode == "side_marker":
                            questions, question_layout, marker_location = self.pipeline._build_legacy_side_marker_schema()
                            _, _, debug_img, _ = self.pipeline.engine.analyze_marker_questions(
                                aligned_img,
                                questions,
                                question_layout,
                                scale=scale,
                                marker_location=marker_location,
                            )
                        elif layout_mode == "timing_mark":
                            debug_img = aligned_img
                        else:
                            rois = self.pipeline.form_manager.get_fixed_rois(scale=scale)
                            _, _, debug_img = self.pipeline.engine.analyze_sheet_cv(aligned_img, rois)
                        debug_img = self._blend_custom_fields_debug(debug_img, aligned_img, scale)
            except Exception as e:
                print(f"[REVIEW] debug overlay 실패: {e}")

            try:
                dlg = self._create_error_editor_dialog(debug_img, scan_results, image_path)
            except Exception as e:
                print(f"[REVIEW] 다이얼로그 생성 실패: {e}")
                print(traceback.format_exc())
                self._set_last_error_message(str(e))
                break
            session_total = max(
                0,
                int(getattr(self, "session_end_read_num", 0)) - int(getattr(self, "session_start_read_num", 1)) + 1,
            )
            dlg.lbl_idx.setText(f"{current_idx + 1}/{session_total}")  # 오류 순번/세션 총 검사 수

            # exec_() 호출 시 창을 닫을 때까지 대기
            try:
                dlg.exec_()
            except Exception as e:
                print(f"[REVIEW] 다이얼로그 실행 실패: {e}")
                print(traceback.format_exc())
                self._set_last_error_message(str(e))
                break

            # (4) 종료 코드 확인 (Dialog에서 exit_code 설정 필요)
            exit_code = getattr(dlg, "exit_code", 0)

            if exit_code == 0:  # 그냥 종료 (X버튼) -> 루프 종료
                break

            elif exit_code == 1:  # 저장(S) -> 다음으로
                try:
                    self.save_corrected_data(row, dlg.scan_results)
                    self.controller.update_review_done(self.current_db_path, read_num, 1)
                    self._refresh_grid_row_by_read_num(read_num)
                except Exception as e:
                    print(f"[REVIEW] 저장 처리 실패: {e}")
                    print(traceback.format_exc())
                    self._set_last_error_message(str(e))
                    break
                next_idx = self._find_next_unreviewed_index(current_idx + 1, 1)
                if next_idx is None:
                    break
                current_idx = next_idx  # 미점검 다음 순번으로 이동

            elif exit_code == 2:  # 이전(<) -> 저장하지 않고 이전으로
                try:
                    self.controller.update_review_done(self.current_db_path, read_num, 1)
                    self._refresh_grid_row_by_read_num(read_num)
                except Exception as e:
                    print(f"[REVIEW] 이전 이동 처리 실패: {e}")
                    print(traceback.format_exc())
                    self._set_last_error_message(str(e))
                    break
                current_idx -= 1
                if current_idx < 0:
                    QMessageBox.information(self, "알림", "첫 건입니다.")
                    current_idx = 0

            elif exit_code == 3:  # 다음(>) -> 저장하지 않고 다음으로
                try:
                    self.controller.update_review_done(self.current_db_path, read_num, 1)
                    self._refresh_grid_row_by_read_num(read_num)
                except Exception as e:
                    print(f"[REVIEW] 다음 이동 처리 실패: {e}")
                    print(traceback.format_exc())
                    self._set_last_error_message(str(e))
                    break
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
            try:
                read_num, _, _ = self._extract_review_row_fields(row)
            except Exception:
                idx += direction
                continue
            db_row = self.controller.get_scan_by_read_num(self.current_db_path, read_num)
            review_done = db_row[13] if db_row and len(db_row) > 13 else 0
            if not review_done:
                return idx
            idx += direction
        return None

    def parse_result_string(self, result_str):
        """결과 문자열 "103"을 검사용 리스트로 변환."""
        parsed = []
        normalized = str(result_str or "")
        profile = self._resolve_error_editor_profile()
        # Legacy 2-choice encodings used "3" as duplicate in church/rebuild mode.
        allow_legacy_three_duplicate = profile in ("church", "rebuild")
        is_legacy_binary = set(normalized).issubset({"0", "1", "2", "3"})
        duplicate_marked = [0, 1] if profile in ("church", "rebuild") else []
        for i, char in enumerate(normalized):
            marked = []
            status = "정상"

            if char in ("X", "x"):
                marked = list(duplicate_marked)
                status = "중복"
            elif allow_legacy_three_duplicate and char == "3" and is_legacy_binary:
                marked = [0, 1]
                status = "중복"
            elif char == "0":
                marked = []
                status = "공백"
            elif char.isdigit() and char != "0":
                marked = [int(char) - 1]

            parsed.append({"q_num": i + 1, "marked": marked, "status": status})
        return parsed

    def _resolve_error_editor_profile(self) -> str:
        profile = str(getattr(self, "error_editor_profile", "")).strip().lower()
        if profile in ("score", "church", "rebuild"):
            return profile
        if hasattr(self, "pipeline") and bool(getattr(self.pipeline, "candidate_enabled", False)):
            return "score"
        return "church"

    def _create_error_editor_dialog(self, debug_img, scan_results, image_path):
        profile = self._resolve_error_editor_profile()
        if profile == "score":
            dialog_cls = ScoreErrorCorrectionDialog
        elif profile == "rebuild":
            dialog_cls = RebuildErrorCorrectionDialog
        else:
            dialog_cls = ChurchErrorCorrectionDialog
        return dialog_cls(self, debug_img, scan_results, image_path)

    def _blend_custom_fields_debug(self, debug_img, aligned_img, scale: float):
        if debug_img is None or aligned_img is None:
            return debug_img
        if not hasattr(self, "pipeline"):
            return debug_img

        form_data = getattr(self.pipeline, "form_data", None)
        if not isinstance(form_data, dict):
            return debug_img

        fields = form_data.get("fields", [])
        if not isinstance(fields, list) or not fields:
            return debug_img

        base_img = aligned_img
        try:
            marker_location = form_data.get("marker_location", "left")
            if self.pipeline._is_new_marker_schema():
                oriented_img, _ = self.pipeline.engine.normalize_orientation(
                    aligned_img,
                    expected_location=marker_location,
                    min_count=3,
                )
                if oriented_img is not None:
                    base_img = oriented_img
        except Exception:
            pass

        try:
            _, _, fields_debug = self.pipeline.engine.analyze_custom_fields(
                base_img,
                fields,
                scale=scale,
                layout=form_data,
            )
            if fields_debug is None:
                return debug_img
            if debug_img.shape[:2] != fields_debug.shape[:2]:
                return debug_img

            # fields_debug has a black background, so blend only where it drew overlays.
            overlay_mask = np.any(fields_debug > 0, axis=2)
            if not np.any(overlay_mask):
                return debug_img

            mixed = cv2.addWeighted(debug_img, 0.40, fields_debug, 0.95, 0)
            out = debug_img.copy()
            out[overlay_mask] = mixed[overlay_mask]
            return out
        except Exception as e:
            print(f"[REVIEW] fields overlay 실패: {e}")
            return debug_img

    def save_corrected_data(self, original_row, modified_results):
        """수정된 결과를 서비스로 저장."""
        if not self.current_db_path:
            return
        self.controller.save_corrected_data(self.current_db_path, original_row, modified_results)

    def _open_review_for_row(self, row_data):
        if not row_data:
            return
        try:
            read_num, image_path, result_str = self._extract_review_row_fields(row_data)
        except Exception as e:
            self._set_last_error_message(str(e))
            QMessageBox.warning(self, "오류", f"선택 데이터가 손상되어 열 수 없습니다.\n{e}")
            return
        if not image_path or not os.path.exists(image_path):
            msg = f"이미지 파일을 찾을 수 없습니다.\n{image_path}"
            self._set_last_error_message(msg)
            QMessageBox.warning(self, "오류", msg)
            return
        scan_results = self.parse_result_string(result_str)

        image_cv = None
        try:
            img_array = np.fromfile(image_path, np.uint8)
            image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"이미지 로드 실패: {e}")
            self._set_last_error_message(str(e))
        if image_cv is None:
            msg = "이미지를 읽지 못해 판독결과 창을 열 수 없습니다."
            self._set_last_error_message(msg)
            QMessageBox.warning(self, "오류", msg)
            return

        debug_img = image_cv
        try:
            if image_cv is not None and hasattr(self, "pipeline") and isinstance(self.pipeline.form_data, dict):
                aligned_img, _, _ = self.pipeline.engine.align_image_warp(image_cv)
                if aligned_img is not None:
                    scale = self.pipeline._get_scale_factor()
                    layout_mode = self.pipeline.form_manager.get_layout_mode()
                    if self.pipeline._is_new_marker_schema():
                        questions = (
                            self.pipeline.engine.parse_config(self.pipeline.form_data)
                            if "question_groups" in self.pipeline.form_data
                            else self.pipeline.form_data.get("questions", [])
                        )
                        question_layout = self.pipeline.form_data.get("question_layout", {}) or {}
                        marker_location = self.pipeline.form_data.get("marker_location", "left")
                        _, _, debug_img, _ = self.pipeline.engine.analyze_marker_questions(
                            aligned_img,
                            questions,
                            question_layout,
                            scale=scale,
                            marker_location=marker_location,
                        )
                    elif layout_mode == "side_marker":
                        questions, question_layout, marker_location = self.pipeline._build_legacy_side_marker_schema()
                        _, _, debug_img, _ = self.pipeline.engine.analyze_marker_questions(
                            aligned_img,
                            questions,
                            question_layout,
                            scale=scale,
                            marker_location=marker_location,
                        )
                    elif layout_mode == "timing_mark":
                        debug_img = aligned_img
                    else:
                        rois = self.pipeline.form_manager.get_fixed_rois(scale=scale)
                        _, _, debug_img = self.pipeline.engine.analyze_sheet_cv(aligned_img, rois)
                    debug_img = self._blend_custom_fields_debug(debug_img, aligned_img, scale)
        except Exception as e:
            print(f"[REVIEW] debug overlay 실패: {e}")

        try:
            dlg = self._create_error_editor_dialog(debug_img, scan_results, image_path)
            dlg.lbl_idx.setText(str(read_num))
            dlg.exec_()
        except Exception as e:
            print(f"[REVIEW] 단건 검토 다이얼로그 실행 실패: {e}")
            print(traceback.format_exc())
            self._set_last_error_message(str(e))
            QMessageBox.critical(self, "오류", f"판독결과 조회/수정 창 실행 중 오류가 발생했습니다.\n{e}")
            return

        exit_code = getattr(dlg, "exit_code", 0)
        if exit_code == 1:
            try:
                self.save_corrected_data(row_data, dlg.scan_results)
                self.update_statistics()
                self._schedule_summary_refresh()
                self.controller.update_review_done(self.current_db_path, read_num, 1)
                self._refresh_grid_row_by_read_num(read_num)
            except Exception as e:
                print(f"[REVIEW] 단건 저장 실패: {e}")
                print(traceback.format_exc())
                self._set_last_error_message(str(e))
                QMessageBox.critical(self, "오류", f"저장 중 오류가 발생했습니다.\n{e}")
        elif exit_code in (2, 3):
            try:
                self.controller.update_review_done(self.current_db_path, read_num, 1)
                self._refresh_grid_row_by_read_num(read_num)
            except Exception as e:
                print(f"[REVIEW] 단건 상태 반영 실패: {e}")
                print(traceback.format_exc())
                self._set_last_error_message(str(e))

    def update_review_summary(self):
        if not self.current_db_path:
            return
        start_read_num = int(getattr(self, "session_start_read_num", 1))
        end_read_num = int(getattr(self, "session_end_read_num", start_read_num - 1))
        if end_read_num < start_read_num:
            return
        task = ReviewSummaryTask(
            self.db,
            self.current_db_path,
            start_read_num,
            end_read_num,
            profile=self._resolve_error_editor_profile(),
        )
        task.signals.result.connect(self._apply_review_summary)
        task.signals.error.connect(self._on_summary_error)
        self.thread_pool.start(task)

    def _apply_review_summary(
        self,
        total_in_session,
        review_count,
        blank_cnt,
        dup_cnt,
        invalid_cnt,
        roster_missing_cnt,
        absent_cnt,
    ):
        if total_in_session > 0:
            self.lbl_check.setText(f"{review_count}/{total_in_session}")
            self.lbl_review_detail.setText(
                f"오류:{invalid_cnt}  중복:{dup_cnt}  공백:{blank_cnt}  "
                f"명단미등록:{roster_missing_cnt}  결시:{absent_cnt}"
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
        if not isinstance(row, (list, tuple)) or len(row) < 8:
            self._set_last_error_message(f"DB 행 구조가 예상과 다릅니다. (read_num={read_num})")
            return
        row_place = row[2] if len(row) > 2 else ""
        row_room = row[3] if len(row) > 3 else ""
        image_path = row[4] if len(row) > 4 else ""
        sheet_code = row[5] if len(row) > 5 else ""
        result_str = row[6] if len(row) > 6 else ""
        is_valid = row[7] if len(row) > 7 else 0
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

        prev_block = bool(getattr(self, "_grid_block_changes", False))
        self._grid_block_changes = True
        self.main_grid.setUpdatesEnabled(False)
        try:
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
                            self.main_grid.setItem(r, c, self._item(str(value)))
                        else:
                            cell.setText(str(value))
                    status_cell = self.main_grid.item(r, 5)
                    if status_cell:
                        if review_status == "미점검":
                            status_cell.setForeground(Qt.red)
                        elif review_status == "완료":
                            status_cell.setForeground(Qt.blue)
                    break
        finally:
            self.main_grid.setUpdatesEnabled(True)
            self._grid_block_changes = prev_block
