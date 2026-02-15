from __future__ import annotations

from logic.services.scan_service import ScanService


class ScanSessionController:
    """세션 단위 스캔/DB 작업을 관리하는 컨트롤러."""

    def __init__(self, service: ScanService):
        self.service = service
        self.db = service.db
        self.pipeline = service.pipeline

    def set_project(self, db_path: str | None):
        self.pipeline.set_project(db_path)

    def set_form_path(self, form_path: str | None):
        self.pipeline.set_form_path(form_path)

    def set_candidate_enabled(self, enabled: bool):
        self.service.set_candidate_enabled(enabled)

    def set_debug_options(self, save_on_error: bool, debug_dir: str | None = None):
        self.service.set_debug_options(save_on_error, debug_dir)

    def set_dpi(self, dpi: int):
        self.service.set_dpi(dpi)

    def set_auto_scale_dpi(self, enabled: bool):
        self.service.set_auto_scale_dpi(enabled)

    def set_warp_enabled(self, enabled: bool):
        self.service.set_warp_enabled(enabled)

    # ---- DB/로직 호출 래핑 ----
    def process_image(self, image_path: str, read_num: int, place: str, room: str, warp_enabled: bool | None = None):
        return self.service.process_image(image_path, read_num, place, room, warp_enabled=warp_enabled)

    def build_error_queue(self, db_path: str, check_blank: bool, check_etc: bool):
        return self.service.build_error_queue(db_path, check_blank, check_etc)

    def save_corrected_data(self, db_path: str, original_row, modified_results):
        return self.service.save_corrected_data(db_path, original_row, modified_results)

    def get_summary_rows(self, db_path: str):
        return self.service.get_summary_rows(db_path)

    def get_statistics(self, db_path: str):
        return self.service.get_statistics(db_path)

    def get_grid_rows(self, db_path: str, place: str | None = None, room: str | None = None):
        return self.service.get_grid_rows(db_path, place, room)

    def get_setting(self, db_path: str, key: str, default=""):
        return self.service.get_setting(db_path, key, default)

    def get_all_scans(self, db_path: str):
        return self.service.get_all_scans(db_path)

    def get_next_read_num(self, db_path: str) -> int:
        return self.service.get_next_read_num(db_path)

    def recalc_error_messages(self, db_path: str):
        return self.service.recalc_error_messages(db_path)

    def renumber_read_nums(self, db_path: str, ordered_read_nums):
        return self.service.renumber_read_nums(db_path, ordered_read_nums)

    def get_scan_by_read_num(self, db_path: str, read_num: int):
        return self.service.get_scan_by_read_num(db_path, read_num)

    def update_review_done(self, db_path: str, read_num: int, done: int):
        return self.service.update_review_done(db_path, read_num, done)

    def update_scan_meta(self, db_path: str, read_num: int, scanner_name=None, room_no=None, image_path=None):
        return self.service.update_scan_meta(db_path, read_num, scanner_name, room_no, image_path)

    def delete_scan_result(self, db_path: str, read_num: int):
        return self.service.delete_scan_result(db_path, read_num)
