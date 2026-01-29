from __future__ import annotations

import os

from logic.pipeline import ScanPipeline
from logic.services.db_repository import DBRepository


class ScanService:
    """파이프라인+DB를 묶는 서비스 계층(UI는 여기만 호출)."""

    def __init__(self, db_repo: DBRepository | None = None):
        self.db = db_repo or DBRepository()
        self.pipeline = ScanPipeline(db_repo=self.db)

    def set_project(self, db_path: str | None):
        self.pipeline.set_project(db_path)

    def set_form_path(self, form_path: str | None):
        self.pipeline.set_form_path(form_path)

    def set_debug_options(self, save_on_error: bool, debug_dir: str | None = None):
        self.pipeline.set_debug_options(save_on_error, debug_dir)

    def set_candidate_enabled(self, enabled: bool):
        self.pipeline.set_candidate_enabled(enabled)

    def set_dpi(self, dpi: int):
        self.pipeline.set_dpi(dpi)

    def set_auto_scale_dpi(self, enabled: bool):
        self.pipeline.set_auto_scale_dpi(enabled)

    def set_warp_enabled(self, enabled: bool):
        self.pipeline.warp_enabled = bool(enabled)

    def process_image(self, image_path: str, read_num: int, place: str, room: str, warp_enabled: bool | None = None):
        """이미지 분석 후 결과 저장까지 수행."""
        row_data, save_data = self.pipeline.analyze_image(
            image_path=image_path,
            read_num=read_num,
            place=place,
            room=room,
            warp_enabled=warp_enabled,
        )
        if self.pipeline.current_db_path and save_data:
            self.db.insert_scan_result(self.pipeline.current_db_path, save_data)
        return row_data

    def build_error_queue(self, db_path: str, check_blank: bool, check_etc: bool):
        """점검 대상 오류만 필터링."""
        rows = self.db.get_all_scans(db_path)
        queue = []
        for row in rows:
            is_valid = row[7]
            mark_result = row[6]
            if is_valid == 1:
                continue
            is_blank_paper = (mark_result.replace("0", "") == "")
            if is_blank_paper and check_blank:
                queue.append(row)
            elif not is_blank_paper and check_etc:
                queue.append(row)
        return queue

    def get_summary_rows(self, db_path: str):
        """스캐너/시험실 요약 테이블용 데이터."""
        return self.db.get_summary_by_scanner(db_path)

    def get_statistics(self, db_path: str):
        """총/정상/오류 건수."""
        return self.db.get_statistics(db_path)

    def get_grid_rows(self, db_path: str, place: str | None = None, room: str | None = None):
        """메인 그리드용 데이터(고사장/시험실 필터 가능)."""
        if place is not None and room is not None:
            return self.db.get_scans_by_place_room(db_path, place, room)
        return self.db.get_all_scans(db_path)

    def get_all_scans(self, db_path: str):
        return self.db.get_all_scans(db_path)

    def recalc_error_messages(self, db_path: str):
        if not db_path:
            return 0
        self.pipeline.set_project(db_path)
        rows = self.db.get_all_scans(db_path)
        updated = 0
        for row in rows:
            read_num = row[1]
            place = row[2]
            room = row[3]
            image_path = row[4]
            if not image_path or not os.path.exists(image_path):
                continue
            try:
                _, save_data = self.pipeline.analyze_image(
                    image_path=image_path,
                    read_num=read_num,
                    place=place,
                    room=room,
                )
            except Exception as e:
                print(f"[RECALC] read_num={read_num} 실패: {e}")
                continue
            if not save_data:
                continue
            self.db.update_scan_result_detail(
                db_path,
                read_num,
                save_data.get("mark_result"),
                save_data.get("is_valid", 0),
                save_data.get("error_message"),
                save_data.get("sheet_code"),
                save_data.get("exam_no"),
                save_data.get("birth"),
                save_data.get("subject"),
            )
            updated += 1
        return updated

    def renumber_read_nums(self, db_path: str, ordered_read_nums):
        return self.db.renumber_read_nums(db_path, ordered_read_nums)

    def get_setting(self, db_path: str, key: str, default=""):
        return self.db.get_setting(db_path, key, default)

    def get_scan_by_read_num(self, db_path: str, read_num: int):
        return self.db.get_scan_by_read_num(db_path, read_num)

    def update_review_done(self, db_path: str, read_num: int, done: int):
        return self.db.update_review_done(db_path, read_num, done)

    def update_scan_meta(self, db_path: str, read_num: int, scanner_name=None, room_no=None, image_path=None):
        return self.db.update_scan_meta(db_path, read_num, scanner_name, room_no, image_path)

    def delete_scan_result(self, db_path: str, read_num: int):
        return self.db.delete_scan_result(db_path, read_num)

    def save_corrected_data(self, db_path: str, original_row, modified_results):
        """수정 결과를 DB에 저장하고 오류 상태를 정리."""
        new_result_str = ""
        for r in modified_results:
            val = "0"
            if len(r['marked']) == 0:
                val = "0"
            elif len(r['marked']) > 1:
                val = "3"
            elif 0 in r['marked']:
                val = "1"
            elif 1 in r['marked']:
                val = "2"
            new_result_str += val

        read_num = original_row[1]
        image_path = original_row[4]
        before_str = original_row[6]

        self.db.insert_manual_edit(
            db_path,
            read_num=read_num,
            image_path=image_path,
            before_result=before_str,
            after_result=new_result_str,
            reason="오류수정(수동수정)"
        )

        self.db.update_scan_result(db_path, read_num, new_result_str, 1)
        self.db.update_scan_meta(db_path, read_num, scanner_name=None, room_no=None, image_path=None)
        try:
            with self.db.connect(db_path) as conn:
                cur = conn.cursor()
                cur.execute("UPDATE tblScanData SET error_message = ? WHERE read_num = ?", ("", read_num))
                conn.commit()
        except Exception:
            pass
        self.db.update_review_done(db_path, read_num, 1)
        return new_result_str
