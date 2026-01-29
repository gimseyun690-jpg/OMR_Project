import os
import traceback
import cv2
import numpy as np
from utils.text_io import read_json

from logic.omr_engine import OMREngine
from database import DBManager

# 기존 로직 유지를 위한 헬퍼 함수들 (폼 로더에서 가져옴)
from logic.form_loader import build_rois_from_form

DEFAULT_SCAN_DIR = os.path.join(os.getcwd(), "data", "scan_images")


class ScanPipeline:
    """
    패치 포인트
    - engine.configure()에 들어가는 thresh/ratio 타입 강제(int/float)
    - side_marker: 마커 cy 기준 정렬 + ROI 경계 클램프 + ratio threshold 의미 통일
    - ROI가 이미지 밖이면 안전 처리(공란/오류로 반영)
    - status 내부 통일(OK/ERR) -> UI 반환에서 한글 표시
    - (옵션) 에러 시 debug 이미지 저장 가능
    """

    def __init__(self):
        self.db = DBManager()
        self.engine = OMREngine()

        self.current_db_path = None
        self.scan_dir = DEFAULT_SCAN_DIR

        self.form_path = None
        self.form_data = None

        # 디버그 이미지 저장 옵션
        self.debug_save_on_error = False
        self.debug_dir = os.path.join(os.getcwd(), "data", "scan_debug")
        os.makedirs(self.debug_dir, exist_ok=True)
        self.candidate_enabled = False
        self.warp_enabled = True

    # ====== 외부 설정 ======
    def set_project(self, db_path: str | None):
        self.current_db_path = db_path

    def set_scan_dir(self, scan_dir: str):
        self.scan_dir = scan_dir

    def set_debug_options(self, save_on_error: bool, debug_dir: str | None = None):
        self.debug_save_on_error = bool(save_on_error)
        if debug_dir:
            self.debug_dir = debug_dir
        os.makedirs(self.debug_dir, exist_ok=True)

    def _safe_int(self, v, default: int):
        try:
            return int(float(v))
        except Exception:
            return default

    def _safe_float(self, v, default: float):
        try:
            return float(v)
        except Exception:
            return default

    def _status_to_code(self, status: str | None) -> str:
        """엔진/내부에서 들어오는 다양한 status를 OK/ERR로 통일"""
        if not status:
            return "ERR"
        s = str(status).strip().lower()
        if s in ("정상", "normal", "ok", "success", "good"):
            return "OK"
        if s in ("오류", "error", "fail", "failed", "ng"):
            return "ERR"
        # 애매하면 ERR로 보수적으로
        return "ERR"

    def _code_to_ui_status(self, code: str) -> str:
        return "정상" if code == "OK" else "오류"

    def set_form_path(self, form_path: str | None):
        """콤보박스에서 폼 선택 시 호출"""
        self.form_path = form_path
        self.form_data = None

        if form_path and os.path.exists(form_path):
            try:
                self.form_data = read_json(form_path)

                # 폼의 OMR 파라미터 즉시 적용 (타입 강제)
                omr_settings = self.form_data.get("omr", {}) if isinstance(self.form_data, dict) else {}
                thresh = self._safe_int(omr_settings.get("threshold", 140), 140)
                ratio = self._safe_float(omr_settings.get("pixel_ratio", 0.05), 0.05)
                self.engine.configure(thresh, ratio)

            except Exception as e:
                print(f"폼 로드 오류: {e}")
                print(traceback.format_exc())

    def set_candidate_enabled(self, enabled: bool):
        """수험정보 판독 사용 여부"""
        self.candidate_enabled = bool(enabled)

    # ====== [복구됨] 내부 유틸: DB에서 설정 가져오기 ======
    def _get_params_from_db(self):
        """JSON 폼이 없을 때 DB 설정값 사용 (기존 기능 복구)"""
        if not self.current_db_path:
            return [], None, "Unknown"

        # 좌표 설정 불러오기
        start_y = self._safe_int(self.db.get_setting(self.current_db_path, "roi_start_y", "515"), 515)
        gap_y = self._safe_int(self.db.get_setting(self.current_db_path, "roi_gap_y", "90"), 90)
        w = self._safe_int(self.db.get_setting(self.current_db_path, "roi_w", "35"), 35)
        h = self._safe_int(self.db.get_setting(self.current_db_path, "roi_h", "35"), 35)
        x_agree = self._safe_int(self.db.get_setting(self.current_db_path, "roi_agree_x", "1130"), 1130)
        x_disagree = self._safe_int(self.db.get_setting(self.current_db_path, "roi_disagree_x", "1275"), 1275)

        rois = []
        for i in range(5):
            y = start_y + (i * gap_y)
            rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])

        # 기타 설정 (타입 강제!)
        thresh = self._safe_int(self.db.get_setting(self.current_db_path, "omr_threshold", "140"), 140)
        ratio = self._safe_float(self.db.get_setting(self.current_db_path, "omr_pixel_ratio", "0.05"), 0.05)
        self.engine.configure(thresh, ratio)

        sheet_code = self.db.get_setting(self.current_db_path, "sheet_code", "OMR_V1")
        return rois, None, sheet_code

    def _result_to_string(self, results):
        """결과 리스트 -> '01231' 문자열 변환"""
        s = ""
        for r in results:
            marked = r.get("marked", []) if isinstance(r, dict) else []
            if len(marked) == 0:
                val = "0"
            elif len(marked) > 1:
                val = "3"
            elif 0 in marked:
                val = "1"
            elif 1 in marked:
                val = "2"
            else:
                val = "0"
            s += val
        return s

    def _clamp_roi(self, img, x, y, w, h):
        """ROI를 이미지 경계로 클램프. 유효하지 않으면 None."""
        if img is None or w <= 0 or h <= 0:
            return None
        H, W = img.shape[:2]
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(W, int(x) + int(w))
        y2 = min(H, int(y) + int(h))
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2 - x1, y2 - y1)

    def _get_effective_ratio_threshold(self) -> float:
        """
        side_marker에서 사용할 '비율 기준' 임계값.
        - JSON 폼이 있으면 폼의 omr.pixel_ratio 우선
        - 없으면 engine의 설정값(이름이 다를 수 있어 fallbacks)
        """
        # 폼 우선
        if isinstance(self.form_data, dict):
            omr_settings = self.form_data.get("omr", {})
            if isinstance(omr_settings, dict) and "pixel_ratio" in omr_settings:
                return self._safe_float(omr_settings.get("pixel_ratio", 0.05), 0.05)

        # 엔진 fallback: 가능한 속성명을 최대한 흡수
        for attr in ("pixel_ratio", "pixel_threshold", "mark_ratio_threshold", "ratio_threshold"):
            if hasattr(self.engine, attr):
                try:
                    v = float(getattr(self.engine, attr))
                    # 비율이라고 가정: 0~1 범위를 벗어나면 기본값으로
                    if 0.0 <= v <= 1.0:
                        return v
                except Exception:
                    pass

        return 0.05

    def _save_debug_if_needed(self, debug_img, image_path: str, reason: str):
        if not self.debug_save_on_error:
            return None
        if debug_img is None:
            return None

        base = os.path.splitext(os.path.basename(image_path))[0]
        out = os.path.join(self.debug_dir, f"{base}__{reason}.jpg")
        try:
            cv2.imwrite(out, debug_img)
            return out
        except Exception:
            return None

    # ====== 메인 프로세스 ======
    def process_image(self, image_path: str, read_num: int, place: str, room: str, warp_enabled: bool | None = None) -> list[str]:
        # 1) 이미지 로드 (Engine이 한글 경로 처리)
        img = self.engine.load_image(image_path)
        if img is None:
            return self._create_error_result(read_num, place, room, image_path, "이미지 로드 실패")

        # 2) 이미지 정렬 (Auto-Deskew / 투영 변환)
        use_warp = self.warp_enabled if warp_enabled is None else bool(warp_enabled)
        if use_warp:
            aligned_img, align_ok, align_reason = self.engine.align_image(img, self.form_data)
        else:
            aligned_img, align_ok, align_reason = img, True, "warp_disabled"
        if aligned_img is None:
            reason = f"이미지 정렬 실패({align_reason})"
            self._save_debug_if_needed(img, image_path, "ALIGN_FAIL")
            return self._create_error_result(read_num, place, room, image_path, reason)
        if not align_ok and align_reason != "fallback_original":
            reason = f"이미지 정렬 실패({align_reason})"
            self._save_debug_if_needed(aligned_img or img, image_path, "ALIGN_FAIL")
            return self._create_error_result(read_num, place, room, image_path, reason)

        # 3) 판독 모드 결정 및 실행
        sheet_code = "Unknown"
        status_code = "ERR"
        results = []
        debug_img = aligned_img.copy()
        error_reason = ""
        candidate_msg = ""
        candidate_info = {}

        try:
            # [CASE A] JSON 폼이 선택된 경우
            if isinstance(self.form_data, dict):
                # 시트코드는 폼 번호(form_no) 우선, 없으면 sheet_code/form_id 순
                sheet_code = (
                    self.form_data.get("form_no")
                    or self.form_data.get("sheet_code")
                    or self.form_data.get("form_id")
                    or "Unknown"
                )
                layout_mode = self.form_data.get("layout_mode", "fixed")

                if layout_mode == "side_marker":
                    status_code, results, debug_img, error_reason = self._process_side_marker_mode(aligned_img)
                else:
                    status_code, results, debug_img = self._process_json_fixed_mode(aligned_img)

            # [CASE B] JSON 폼이 없는 경우 -> DB 설정 사용 (Legacy Mode)
            else:
                rois, _, db_sheet_code = self._get_params_from_db()
                sheet_code = db_sheet_code
                status, results, debug_img = self.engine.analyze_sheet_cv(aligned_img, rois, ref_anchor=None)
                status_code = self._status_to_code(status)

        except Exception as e:
            print(f"Processing Error: {e}")
            print(traceback.format_exc())
            status_code = "ERR"

        # 4) 수험정보 판독/비교 (선택)
        cand_ok = True
        cand_reason = ""
        cand_info = {}
        if self.candidate_enabled:
            cand_ok, cand_reason, cand_info = self._process_candidate_fields(aligned_img)
            candidate_info = cand_info or {}
            if not cand_ok:
                status_code = "ERR"
                if not error_reason:
                    error_reason = "CANDIDATE"
                    candidate_msg = cand_reason

        # 5) 결과/저장
        result_str = self._result_to_string(results)
        ui_status = self._code_to_ui_status(status_code)
        is_valid = 1 if status_code == "OK" else 0

        if status_code != "OK" and error_reason == "TIMING_MARK":
            ui_message = "타이밍 마크 오류입니다."
        elif status_code != "OK" and error_reason == "CANDIDATE":
            ui_message = candidate_msg or "수험정보 불일치"
        elif status_code != "OK":
            ui_message = "판독 오류"
        else:
            ui_message = "완료"

        # 에러 시 debug 이미지 저장(옵션)
        if status_code != "OK":
            self._save_debug_if_needed(debug_img, image_path, "ERR")

        if self.current_db_path:
            save_data = {
                "read_num": read_num,
                "place": place,
                "room": room,
                "path": image_path,
                "sheet_code": sheet_code,
                "mark_result": result_str,
                "is_valid": is_valid,
                "error_message": ui_message if is_valid == 0 else None,
                "exam_no": candidate_info.get("exam_no"),
                "birth": candidate_info.get("birth"),
                "subject": candidate_info.get("subject"),
                "review_done": 0,
            }
            self.db.insert_scan_result(self.current_db_path, save_data)

        # 6) UI 반환 데이터
        return [
            str(read_num),
            sheet_code,
            place,
            room,
            ui_status,
            ui_message,
            result_str,
            image_path,
            os.path.basename(image_path),
        ]

    # --- 내부 로직: 사이드 마크 모드 ---
    def _process_side_marker_mode(self, img):
        """
        status_code(OK/ERR), sheet_results(list), debug_img, error_reason 반환
        """
        debug_img = img.copy()

        markers = self.engine.find_side_markers(img) or []
        if not isinstance(markers, list):
            markers = []

        # ✅ 마커는 cy 기준 정렬 (문항 매칭 안정화)
        try:
            markers = sorted(markers, key=lambda m: m.get("cy", 0))
        except Exception:
            pass

        questions = self.form_data.get("questions", []) if isinstance(self.form_data, dict) else []
        if not isinstance(questions, list) or len(questions) == 0:
            # 질문이 없으면 의미가 없으므로 ERR 처리
            return "ERR", [], debug_img, ""

        # 타이밍 마크(사이드 마크) 부족 시 즉시 오류 처리
        if len(markers) < len(questions):
            return "ERR", [], debug_img, "TIMING_MARK"

        roi_params = self.form_data.get("roi_params", {}) if isinstance(self.form_data, dict) else {}
        if not isinstance(roi_params, dict):
            roi_params = {}

        box_w = self._safe_int(roi_params.get("box_w", 40), 40)
        box_h = self._safe_int(roi_params.get("box_h", 40), 40)
        dist_agree = self._safe_int(roi_params.get("marker_to_agree_dist", 600), 600)
        dist_disagree = self._safe_int(roi_params.get("marker_to_disagree_dist", 750), 750)

        ratio_th = self._get_effective_ratio_threshold()

        sheet_results = []
        has_error = False

        for i, q in enumerate(questions):
            q_num = (q.get("no") if isinstance(q, dict) else None) or (i + 1)

            # 마커 부족
            if i >= len(markers):
                sheet_results.append({"q_num": q_num, "marked": [], "status": "마커없음"})
                has_error = True
                continue

            base_cx = self._safe_int(markers[i].get("cx", 0), 0)
            base_cy = self._safe_int(markers[i].get("cy", 0), 0)
            start_y = base_cy - (box_h // 2)

            rois = [
                (base_cx + dist_agree, start_y, box_w, box_h),      # 찬성(0)
                (base_cx + dist_disagree, start_y, box_w, box_h),   # 반대(1)
            ]

            marked_indices = []
            for idx, (rx, ry, rw, rh) in enumerate(rois):
                clamped = self._clamp_roi(img, rx, ry, rw, rh)
                if clamped is None:
                    # ROI 자체가 이미지 밖이면 오류로 간주 (해당 문항은 공란 처리)
                    has_error = True
                    continue

                cx, cy, cw, ch = clamped

                # 엔진 점수 계산
                score = self.engine.get_marking_score(img, cx, cy, cw, ch)

                area = cw * ch
                ratio = (score / area) if area > 0 else 0.0
                is_marked = ratio > ratio_th

                # 그리기
                color = (0, 255, 0) if is_marked else (0, 0, 255)
                cv2.rectangle(debug_img, (cx, cy), (cx + cw, cy + ch), color, 2)
                cv2.putText(
                    debug_img,
                    f"{ratio:.3f}",
                    (cx, max(0, cy - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    1,
                    cv2.LINE_AA,
                )

                if is_marked:
                    marked_indices.append(idx)

            # 상태 판정
            if len(marked_indices) == 0:
                q_status = "공란"
                has_error = True
            elif len(marked_indices) > 1:
                q_status = "중복"
                has_error = True
            else:
                q_status = "정상"

            sheet_results.append({"q_num": q_num, "marked": marked_indices, "status": q_status})

        return ("ERR" if has_error else "OK"), sheet_results, debug_img, ""

    # --- 수험정보 판독/비교 ---
    def _process_candidate_fields(self, img):
        if not isinstance(self.form_data, dict):
            return True, "", {}
        cand = self.form_data.get("candidate_fields")
        if not isinstance(cand, dict):
            return True, "", {}

        debug_overlay = cand.get("debug_overlay", False)
        if debug_overlay:
            try:
                dbg = self._draw_candidate_overlay(img, cand)
                self._save_debug_if_needed(dbg, "candidate_overlay", "CANDIDATE")
            except Exception:
                pass

        cand_info, cand_ok, cand_err = self._read_candidate_info(img, cand)
        if not cand_ok:
            return False, cand_err or "수험정보 판독 오류", cand_info

        if not self.current_db_path:
            return True, "", cand_info

        try:
            roster_rows = self.db.load_roster(self.current_db_path)
        except Exception:
            roster_rows = []

        roster_by_exam = {str(r[0]).strip(): r for r in roster_rows if r and len(r) > 0}
        roster = roster_by_exam.get(cand_info.get("exam_no", ""))
        if roster is None:
            return False, "수험정보 불일치", cand_info

        birth = str(roster[2]).strip() if len(roster) > 2 else ""
        subject = str(roster[3]).strip() if len(roster) > 3 else ""

        if birth and cand_info.get("birth") and birth != cand_info.get("birth"):
            return False, "수험정보 불일치", cand_info
        if subject and cand_info.get("subject") and subject != cand_info.get("subject"):
            return False, "수험정보 불일치", cand_info

        return True, "", cand_info

    def _read_candidate_info(self, img, cand):
        info = {}
        # 수험번호
        exam_cfg = cand.get("exam_no")
        if isinstance(exam_cfg, dict):
            ok, val = self._decode_digit_grid(img, exam_cfg)
            if not ok:
                return {}, False, "수험번호 판독 오류"
            info["exam_no"] = val

        # 출생월일
        birth_cfg = cand.get("birth")
        if isinstance(birth_cfg, dict):
            ok, val = self._decode_digit_grid(img, birth_cfg)
            if not ok:
                return {}, False, "출생월일 판독 오류"
            info["birth"] = val

        # 선택과목
        subj_cfg = cand.get("subject")
        if isinstance(subj_cfg, dict):
            ok, val = self._decode_single_choice(img, subj_cfg)
            if not ok:
                return {}, False, "선택과목 판독 오류"
            info["subject"] = val

        return info, True, ""

    def _decode_digit_grid(self, img, cfg):
        grid = cfg.get("grid", {})
        x = self._safe_int(grid.get("x", 0), 0)
        y = self._safe_int(grid.get("y", 0), 0)
        col_w = self._safe_int(grid.get("col_w", 20), 20)
        row_h = self._safe_int(grid.get("row_h", 20), 20)
        cols = self._safe_int(grid.get("cols", 0), 0)
        rows = self._safe_int(grid.get("rows", 10), 10)
        digits = self._safe_int(cfg.get("digits", cols), cols)

        if img is None or digits <= 0 or rows <= 0 or col_w <= 0 or row_h <= 0:
            return False, ""
        H, W = img.shape[:2]
        grid_w = digits * col_w
        grid_h = rows * row_h
        # 좌표가 이미지 밖으로 크게 벗어나면 즉시 실패
        if x < 0 or y < 0 or x + grid_w > W or y + grid_h > H:
            return False, ""

        ratio_th = self._get_effective_ratio_threshold()
        out = ""
        for c in range(digits):
            best = (-1, 0.0)  # (digit, ratio)
            hits = 0
            for r in range(rows):
                rx = x + (c * col_w)
                ry = y + (r * row_h)
                score = self.engine.get_marking_score(img, rx, ry, col_w, row_h)
                area = col_w * row_h
                ratio = (score / area) if area > 0 else 0.0
                if ratio > ratio_th:
                    hits += 1
                if ratio > best[1]:
                    best = (r, ratio)
            if hits != 1:
                return False, ""
            out += str(best[0])
        return True, out

    def _decode_single_choice(self, img, cfg):
        choices = cfg.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return False, ""
        if img is None:
            return False, ""
        H, W = img.shape[:2]
        ratio_th = self._get_effective_ratio_threshold()
        picked = None
        hits = 0
        for ch in choices:
            label = ch.get("label", "")
            x = self._safe_int(ch.get("x", 0), 0)
            y = self._safe_int(ch.get("y", 0), 0)
            w = self._safe_int(ch.get("w", 20), 20)
            h = self._safe_int(ch.get("h", 20), 20)
            if x < 0 or y < 0 or x + w > W or y + h > H:
                return False, ""
            score = self.engine.get_marking_score(img, x, y, w, h)
            area = w * h
            ratio = (score / area) if area > 0 else 0.0
            if ratio > ratio_th:
                hits += 1
                picked = label
        if hits != 1:
            return False, ""
        return True, picked

    def _draw_candidate_overlay(self, img, cand):
        dbg = img.copy()
        exam_cfg = cand.get("exam_no", {})
        birth_cfg = cand.get("birth", {})
        subj_cfg = cand.get("subject", {})

        for cfg, color in ((exam_cfg, (0, 255, 255)), (birth_cfg, (0, 200, 255))):
            grid = cfg.get("grid", {})
            x = self._safe_int(grid.get("x", 0), 0)
            y = self._safe_int(grid.get("y", 0), 0)
            col_w = self._safe_int(grid.get("col_w", 20), 20)
            row_h = self._safe_int(grid.get("row_h", 20), 20)
            cols = self._safe_int(grid.get("cols", 0), 0)
            rows = self._safe_int(grid.get("rows", 10), 10)
            for c in range(cols):
                for r in range(rows):
                    rx = x + (c * col_w)
                    ry = y + (r * row_h)
                    cv2.rectangle(dbg, (rx, ry), (rx + col_w, ry + row_h), color, 1)

        choices = subj_cfg.get("choices", [])
        for ch in choices:
            x = self._safe_int(ch.get("x", 0), 0)
            y = self._safe_int(ch.get("y", 0), 0)
            w = self._safe_int(ch.get("w", 20), 20)
            h = self._safe_int(ch.get("h", 20), 20)
            cv2.rectangle(dbg, (x, y), (x + w, y + h), (255, 0, 255), 2)
        return dbg

    # --- 내부 로직: JSON 고정 좌표 모드 ---
    def _process_json_fixed_mode(self, img):
        """
        status_code(OK/ERR), results, debug_img 반환
        """
        debug_img = img.copy()
        try:
            rois = build_rois_from_form(self.form_data)
            if not rois:
                return "ERR", [], debug_img

            status, results, debug_img = self.engine.analyze_sheet_cv(img, rois, ref_anchor=None)
            return self._status_to_code(status), results, debug_img
        except Exception as e:
            print(f"JSON fixed mode error: {e}")
            print(traceback.format_exc())
            return "ERR", [], debug_img

    def _create_error_result(self, read_num, place, room, path, msg):
        """에러 발생 시 반환할 더미 데이터"""
        return [
            str(read_num),
            "Error",
            place,
            room,
            "오류",
            msg,
            "00000",
            path,
            os.path.basename(path),
        ]

