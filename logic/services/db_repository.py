from __future__ import annotations

from database import DBManager


class DBRepository:
    """DB 접근을 한 곳으로 모으는 래퍼 (UI 로직 단순화용)."""

    def __init__(self, db: DBManager | None = None):
        self._db = db or DBManager()

    def __getattr__(self, name):
        # 명시되지 않은 메서드는 DBManager에서 바로 찾음
        return getattr(self._db, name)

    # Explicit pass-throughs for clarity/typing
    def connect(self, db_path):
        return self._db.connect(db_path)

    def create_project_tables(self, db_path):
        return self._db.create_project_tables(db_path)

    def insert_scan_result(self, db_path, data: dict):
        return self._db.insert_scan_result(db_path, data)

    def get_all_scans(self, db_path):
        return self._db.get_all_scans(db_path)

    def get_scan_by_read_num(self, db_path, read_num):
        return self._db.get_scan_by_read_num(db_path, read_num)

    def get_scans_by_place_room(self, db_path, place, room):
        return self._db.get_scans_by_place_room(db_path, place, room)

    def update_scan_result(self, db_path, read_num, mark_result, is_valid):
        return self._db.update_scan_result(db_path, read_num, mark_result, is_valid)

    def update_scan_meta(self, db_path, read_num, scanner_name=None, room_no=None, image_path=None):
        return self._db.update_scan_meta(db_path, read_num, scanner_name, room_no, image_path)

    def update_review_done(self, db_path, read_num, done: int):
        return self._db.update_review_done(db_path, read_num, done)

    # [수정] 들여쓰기 오류 수정: 이 메서드가 위 메서드 안으로 들어가 있었습니다.
    def update_scan_result_detail(self, db_path, read_num, mark_result, is_valid, error_message=None, sheet_code=None, exam_no=None, birth=None, subject=None):
        return self._db.update_scan_result_detail(db_path, read_num, mark_result, is_valid, error_message, sheet_code, exam_no, birth, subject)

    def insert_manual_edit(self, db_path, **kwargs):
        return self._db.insert_manual_edit(db_path, **kwargs)

    def get_statistics(self, db_path):
        return self._db.get_statistics(db_path)

    def get_summary_by_scanner(self, db_path):
        return self._db.get_summary_by_scanner(db_path)

    def get_vote_counts(self, db_path, q_count=5):
        return self._db.get_vote_counts(db_path, q_count=q_count)

    def get_raw_data_for_grid(self, db_path):
        return self._db.get_raw_data_for_grid(db_path)

    def get_setting(self, db_path, key, default_value=""):
        return self._db.get_setting(db_path, key, default_value)

    def save_setting(self, db_path, key, value):
        return self._db.save_setting(db_path, key, value)