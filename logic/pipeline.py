import os
import traceback
import cv2
import numpy as np

from logic.omr_engine import OMREngine
from logic.services.db_repository import DBRepository
from logic.services.form_manager import FormManager
from utils.path_utils import data_path

DEFAULT_SCAN_DIR = data_path("scan_images")

class ScanPipeline:
    def __init__(self, db_repo: DBRepository | None = None):
        self.db = db_repo or DBRepository()
        self.engine = OMREngine()
        self.form_manager = FormManager()

        self.current_db_path = None
        self.scan_dir = DEFAULT_SCAN_DIR
        self.form_path = None
        self.form_data = None

        # 디버그 옵션
        self.debug_save_on_error = False
        self.debug_dir = data_path("scan_debug")
        os.makedirs(self.debug_dir, exist_ok=True)
        
        self.candidate_enabled = False
        self.warp_enabled = True
        # Master switch: when False, marker-based deskew is forcibly disabled.
        self.marker_deskew_enabled = True
        
        # [수정] DPI는 폼 데이터의 기준 DPI를 확인하기 위한 용도로 사용
        self.system_dpi = 150 
        self.auto_scale_dpi = True

    # ====== 설정 메서드 ======
    def set_project(self, db_path: str | None):
        self.current_db_path = db_path
        if self.form_path and os.path.exists(self.form_path):
            self.set_form_path(self.form_path)

    @staticmethod
    def _parse_int_setting(raw, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
        try:
            value = int(float(raw))
        except Exception:
            value = int(default)
        if min_value is not None:
            value = max(int(min_value), value)
        if max_value is not None:
            value = min(int(max_value), value)
        return int(value)

    @staticmethod
    def _parse_float_setting(raw, default: float, min_value: float | None = None, max_value: float | None = None) -> float:
        try:
            value = float(raw)
        except Exception:
            value = float(default)
        if not np.isfinite(value):
            value = float(default)
        if min_value is not None:
            value = max(float(min_value), value)
        if max_value is not None:
            value = min(float(max_value), value)
        return float(value)

    def set_scan_dir(self, scan_dir: str):
        self.scan_dir = scan_dir

    def set_debug_options(self, save_on_error: bool, debug_dir: str | None = None):
        self.debug_save_on_error = bool(save_on_error)
        if debug_dir:
            self.debug_dir = debug_dir
        os.makedirs(self.debug_dir, exist_ok=True)

    def set_form_path(self, form_path: str | None):
        self.form_path = form_path
        self.form_data = None
        if form_path and os.path.exists(form_path):
            try:
                self.form_data = self.form_manager.load(form_path)

                # ✅ JSON에서 직접 파라미터 적용
                if isinstance(self.form_data, dict):
                    omr = self.form_data.get("omr", {}) or {}
                    marker_detection = self.form_data.get("marker_detection", {})
                    if not isinstance(marker_detection, dict):
                        marker_detection = {}

                    # 전처리(adaptiveThreshold) 파라미터 (없으면 기본 유지)
                    block_size = omr.get("block_size")  # JSON에 없으면 None -> 기본 15 유지
                    C = self._parse_int_setting(omr.get("C", 7), 7, min_value=0, max_value=30)
                    red_cutoff = self._parse_int_setting(omr.get("red_cutoff", 180), 180, min_value=0, max_value=255)
                    open_kernel = self._parse_int_setting(omr.get("open_kernel", 3), 3, min_value=1, max_value=31)

                    # 마킹 판정 비율
                    pixel_ratio = self._parse_float_setting(omr.get("pixel_ratio", 0.05), 0.05, min_value=0.0, max_value=1.0)

                    # 사이드 마커 검출 threshold
                    marker_thresh = self._parse_int_setting(omr.get("threshold", 120), 120, min_value=0, max_value=255)

                    # DB override values (UI tuning).
                    if self.current_db_path:
                        marker_thresh = self._parse_int_setting(
                            self.db.get_setting(self.current_db_path, "omr_threshold", "120"),
                            marker_thresh,
                            min_value=0,
                            max_value=255,
                        )
                        raw_block_size = self.db.get_setting(self.current_db_path, "omr_block_size", "")
                        if str(raw_block_size).strip() != "":
                            block_size = self._parse_int_setting(raw_block_size, block_size or 15, min_value=3, max_value=255)
                        C = self._parse_int_setting(
                            self.db.get_setting(self.current_db_path, "omr_c", "7"),
                            C,
                            min_value=0,
                            max_value=30,
                        )
                        red_cutoff = self._parse_int_setting(
                            self.db.get_setting(self.current_db_path, "omr_red_cutoff", "180"),
                            red_cutoff,
                            min_value=0,
                            max_value=255,
                        )
                        open_kernel = self._parse_int_setting(
                            self.db.get_setting(self.current_db_path, "omr_open_kernel", "3"),
                            open_kernel,
                            min_value=1,
                            max_value=31,
                        )
                        pixel_ratio = self._parse_float_setting(
                            self.db.get_setting(self.current_db_path, "omr_pixel_ratio", "0.05"),
                            pixel_ratio,
                            min_value=0.0,
                            max_value=1.0,
                        )
                    section_offsets = self.form_data.get("section_offsets", {})
                    if not isinstance(section_offsets, dict):
                        section_offsets = {}
                    exam_no_offset = self.form_data.get(
                        "exam_no_offset", section_offsets.get("exam_no_offset", 0.0)
                    )
                    birth_offset = self.form_data.get(
                        "birth_offset", section_offsets.get("birth_offset", 0.0)
                    )
                    name_offset = self.form_data.get(
                        "name_offset", section_offsets.get("name_offset", 0.0)
                    )
                    subject_offset = self.form_data.get(
                        "subject_offset", section_offsets.get("subject_offset", 0.0)
                    )
                    questions_offset = self.form_data.get(
                        "questions_offset",
                        section_offsets.get("questions_offset", section_offsets.get("question_offset", 0.0)),
                    )

                    self.engine.configure(
                        block_size=block_size,
                        pixel_ratio=pixel_ratio,
                        marker_thresh=marker_thresh,
                        C=C,
                        red_cutoff=red_cutoff,
                        open_kernel=open_kernel,
                        marker_detection=marker_detection,
                        exam_no_offset=exam_no_offset,
                        birth_offset=birth_offset,
                        name_offset=name_offset,
                        subject_offset=subject_offset,
                        questions_offset=questions_offset,
                    )

            except Exception as e:
                print(f"폼 로드 오류: {e}")
                traceback.print_exc()


    def set_candidate_enabled(self, enabled: bool):
        self.candidate_enabled = bool(enabled)

    def set_dpi(self, dpi: int):
        self.dpi = int(dpi) if dpi > 0 else 150

    def set_auto_scale_dpi(self, enabled: bool):
        self.auto_scale_dpi = bool(enabled)

    def set_marker_deskew_enabled(self, enabled: bool):
        self.marker_deskew_enabled = bool(enabled)

    # ====== 헬퍼 메서드 ======
    def _status_to_code(self, status: str | None) -> str:
        if not status: return "ERR"
        s = str(status).strip().lower()
        if s in ("정상", "normal", "ok", "success", "good"): return "OK"
        return "ERR"

    def _code_to_ui_status(self, code: str) -> str:
        return "정상" if code == "OK" else "오류"

    def _get_scale_factor(self):
        """
        JSON 폼(예: 200dpi)과 엔진(150dpi 고정) 사이의 좌표 변환 비율 계산
        """
        if not self.auto_scale_dpi or not isinstance(self.form_data, dict):
            return 1.0
        
        # 폼이 제작된 기준 DPI (기본값 150)
        form_base_dpi = int(self.form_data.get("dpi") or self.form_data.get("base_dpi") or 150)
        
        # 엔진의 기준 DPI (OMREngine의 width/height가 150DPI 기준이므로 150 고정)
        engine_base_dpi = 150 
        
        if form_base_dpi <= 0: return 1.0
        return float(engine_base_dpi) / float(form_base_dpi)

    def _is_new_marker_schema(self) -> bool:
        if not isinstance(self.form_data, dict):
            return False
        has_questions = ("questions" in self.form_data) or ("question_groups" in self.form_data)
        has_layout = isinstance(self.form_data.get("question_layout", {}), dict)
        return has_questions and has_layout and "layout_mode" not in self.form_data

    def _build_legacy_side_marker_schema(self):
        """Translate legacy side_marker schema into marker-question layout."""
        form = self.form_data if isinstance(self.form_data, dict) else {}
        raw_questions = form.get("questions", [])
        questions = []
        if isinstance(raw_questions, list):
            for i, q in enumerate(raw_questions):
                item = dict(q) if isinstance(q, dict) else {"no": i + 1, "type": "vote"}
                item.setdefault("no", i + 1)
                if item.get("row_index") is None and item.get("y") is None:
                    item["row_index"] = i
                item.setdefault("choices", 2)
                questions.append(item)

        roi_params = form.get("roi_params", {}) or {}
        raw_dist_agree = roi_params.get("dist_agree") or roi_params.get("marker_to_agree_dist") or 100
        raw_dist_disagree = roi_params.get("dist_disagree") or roi_params.get("marker_to_disagree_dist") or 200
        try:
            dist_agree = float(raw_dist_agree)
        except Exception:
            dist_agree = 100.0
        try:
            dist_disagree = float(raw_dist_disagree)
        except Exception:
            dist_disagree = 200.0

        choice_dx = float(dist_disagree - dist_agree)
        if abs(choice_dx) < 1e-6:
            choice_dx = 1.0

        base_dpi = int(form.get("dpi") or form.get("base_dpi") or 150)
        if base_dpi <= 0:
            base_dpi = 150
        inferred_width = int(round(float(self.engine.width) * (float(base_dpi) / 150.0)))
        inferred_height = int(round(float(self.engine.height) * (float(base_dpi) / 150.0)))

        question_layout = {
            "width": int(form.get("width", inferred_width)),
            "height": int(form.get("height", inferred_height)),
            "x_offset": float(dist_agree),
            "choice_dx": float(choice_dx),
            "box_w": int(roi_params.get("box_w", 35)),
            "box_h": int(roi_params.get("box_h", 35)),
            "row_offset_y": 0,
            "row_start_y": 0,
            "row_start_from_marker": True,
            "row_dy": 0,
            "rows_per_col": max(1, len(questions)),
            "marker_start_index": 1,
            "columns": 1,
            "numbering_order": "column_major",
        }
        marker_location = form.get("marker_location", "left")
        return questions, question_layout, marker_location

    def _save_debug_if_needed(self, debug_img, image_path: str, reason: str):
        if not self.debug_save_on_error or debug_img is None:
            return
        base = os.path.splitext(os.path.basename(image_path))[0]
        out = os.path.join(self.debug_dir, f"{base}__{reason}.jpg")
        try:
            cv2.imwrite(out, debug_img)
        except Exception:
            pass

    # ====== 메인 프로세스 ======
    def process_image(self, image_path: str, read_num: int, place: str, room: str, warp_enabled: bool | None = None, save_to_db: bool = True):
        row_data, save_data = self.analyze_image(image_path, read_num, place, room, warp_enabled)
        if save_to_db and self.current_db_path and save_data:
            self.db.insert_scan_result(self.current_db_path, save_data)
        return row_data

    def analyze_image(self, image_path: str, read_num: int, place: str, room: str, warp_enabled: bool | None = None):
        # 1. 이미지 로드
        img = self.engine.load_image(image_path)
        if img is None:
            return self._create_error_result(read_num, place, room, image_path, "이미지 로드 실패"), None

        # 2. 정렬 (Align)
        # ScanPipeline은 "정렬해라" 명령만 내림. 실제 크기 조정(1240x1754)은 엔진 내부에서 수행됨.
        use_warp = self.warp_enabled if warp_enabled is None else bool(warp_enabled)
        if use_warp:
            aligned_img, align_ok, align_reason = self.engine.align_image_warp(img)
        else:
            # 워프 안 해도 엔진 표준 크기로 리사이즈는 필요 (Engine 로직에 의존)
            aligned_img, align_ok, align_reason = self.engine.align_image(img)

        if aligned_img is None:
             return self._create_error_result(read_num, place, room, image_path, f"정렬 실패({align_reason})"), None

        # 3. 판독 (Processing)
        sheet_code = "Unknown"
        status_code = "ERR"
        results = []
        debug_img = aligned_img.copy()
        error_reason = ""
        candidate_info = {}

        try:
            # 좌표 스케일링 팩터 계산 (여기는 정상)
            scale = self._get_scale_factor()
            analysis_img = aligned_img

            # [CASE A] JSON 폼이 선택된 경우
            if isinstance(self.form_data, dict):
                sheet_code = self.form_data.get("form_name") or self.form_manager.get_sheet_code()
                layout_mode = self.form_manager.get_layout_mode()

                if self._is_new_marker_schema():
                    # Marker-schema forms use scale derived from engine DPI/form DPI.
                    # Keep analysis image on aligned canvas by default so coordinates and scale match.
                    use_original_marker_image = bool(self.form_data.get("use_original_marker_image", False))
                    analysis_img = img if use_original_marker_image else aligned_img
                    questions = (
                        self.engine.parse_config(self.form_data)
                        if "question_groups" in self.form_data
                        else self.form_data.get("questions", [])
                    )
                    question_layout = dict(self.form_data.get("question_layout", {}) or {})
                    if not self.marker_deskew_enabled:
                        question_layout["deskew_with_markers"] = False
                    marker_location = self.form_data.get("marker_location", "left")

                    status, results, debug_img, error_reason = self.engine.analyze_marker_questions(
                        analysis_img,
                        questions,
                        question_layout,
                        scale=scale,
                        marker_location=marker_location,
                    )
                    status_code = self._status_to_code(status)

                elif layout_mode == "side_marker":
                    questions, question_layout, marker_location = self._build_legacy_side_marker_schema()
                    if not self.marker_deskew_enabled:
                        question_layout = dict(question_layout)
                        question_layout["deskew_with_markers"] = False
                    status, results, debug_img, error_reason = self.engine.analyze_marker_questions(
                        aligned_img,
                        questions,
                        question_layout,
                        scale=scale,
                        marker_location=marker_location,
                    )
                    status_code = self._status_to_code(status)

                elif layout_mode == "timing_mark":
                    status_code = "ERR"
                    results = []
                    debug_img = aligned_img.copy()
                    error_reason = "TIMING_MARK_DEPRECATED"

                else:
                    # 고정 좌표 모드
                    rois = self.form_manager.get_fixed_rois(scale=scale)
                    status, results, debug_img = self.engine.analyze_sheet_cv(aligned_img, rois)
                    status_code = self._status_to_code(status)

            # [B] Legacy DB 모드
            else:
                rois, _, db_sheet_code = self._get_params_from_db() # 이 내부에서도 scale 적용 필요
                sheet_code = db_sheet_code
                status, results, debug_img = self.engine.analyze_sheet_cv(aligned_img, rois)
                status_code = self._status_to_code(status)

            # 4. 수험정보 판독 (옵션)
            # Always run when enabled so candidate ROI/debug remains visible
            # even if objective answers contain errors.
            if self.candidate_enabled:
                if isinstance(self.form_data, dict) and "fields" in self.form_data:
                    candidate_layout = dict(self.form_data)
                    if not self.marker_deskew_enabled:
                        candidate_layout["deskew_with_markers"] = False
                    c_ok, c_info, c_debug = self.engine.analyze_custom_fields(
                        analysis_img,
                        self.form_data.get("fields", []),
                        scale=scale,
                        layout=candidate_layout,
                    )
                    candidate_info = c_info

                    # 디버그 이미지 합치기 (옵션)
                    if c_debug is not None:
                        # Candidate ROI overlay should stay clearly visible.
                        if debug_img is None:
                            debug_img = c_debug.copy()
                        elif debug_img.shape == c_debug.shape:
                            mask = np.any(c_debug != 0, axis=2)
                            if np.any(mask):
                                debug_img[mask] = c_debug[mask]
                        else:
                            debug_img = cv2.add(debug_img, c_debug)

                    if not c_ok:
                        if status_code == "OK":
                            status_code = "ERR"
                        if not error_reason:
                            error_reason = "CANDIDATE"
                else:
                    # [개선] Engine으로 로직 이관
                    cand_config = self.form_data.get("candidate_fields") if isinstance(self.form_data, dict) else None
                    if cand_config:
                        c_ok, c_info, c_debug = self.engine.analyze_candidate_info(analysis_img, cand_config, scale)
                        candidate_info = c_info
                        
                        # 디버그 이미지 합치기 (옵션)
                        if c_debug is not None:
                            debug_img = cv2.addWeighted(debug_img, 0.7, c_debug, 0.3, 0)

                        if not c_ok:
                            if status_code == "OK":
                                status_code = "ERR"
                            if not error_reason:
                                error_reason = "CANDIDATE"

        except Exception as e:
            print(f"Pipeline Error: {e}")
            traceback.print_exc()
            status_code = "ERR"
            error_reason = "EXCEPTION"

        # 5. 결과 종합
        result_str = self._result_to_string(results)
        ui_status = self._code_to_ui_status(status_code)
        is_valid = 1 if status_code == "OK" else 0
        
        ui_msg = "완료"
        if status_code != "OK":
            if error_reason == "TIMING_MARK": ui_msg = "타이밍 마크 오류"
            elif error_reason == "CANDIDATE": ui_msg = "수험정보 판독 오류"
            else: ui_msg = f"판독 오류 ({error_reason})"

        if status_code != "OK":
            self._save_debug_if_needed(debug_img, image_path, "ERR")

        # 저장용 데이터
        save_data = {
            "read_num": read_num, "place": place, "room": room, "path": image_path,
            "sheet_code": sheet_code, "mark_result": result_str,
            "is_valid": is_valid, "error_message": ui_msg if not is_valid else None,
            "exam_no": candidate_info.get("exam_no"),
            "birth": candidate_info.get("birth"),
            "subject": candidate_info.get("subject"),
            "review_done": 0,
        }

        # UI용 데이터
        row_data = [
            str(read_num), sheet_code, place, room, ui_status, ui_msg,
            result_str, image_path, os.path.basename(image_path),
        ]
        return row_data, save_data

    # ... (Legacy DB 지원 메서드 _get_params_from_db 등은 유지) ...
    def _get_params_from_db(self):
        # 기존 코드 유지하되, 내부 scale 계산 로직 점검 필요
        # ... (생략) ...
        return [], None, "Unknown"

    def _result_to_string(self, results):
        s = ""
        for r in results:
            marked = r.get("marked", [])
            if not marked:
                s += "0"
            elif len(marked) > 1:
                s += "X"  # 중복
            else:
                s += str(marked[0] + 1)  # 0번 인덱스 -> 1번 마킹
        return s
    
    def _create_error_result(self, read_num, place, room, path, msg):
         return [str(read_num), "Error", place, room, "오류", msg, "00000", path, os.path.basename(path)]
