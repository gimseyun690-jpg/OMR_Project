# logic/pipeline.py
import os
import cv2
import numpy as np

from logic.vision.grid_detector import find_timing_mark
from logic.vision.preprocessor import rotate_image_keep_size
from logic.vision.preprocessor import warp_to_form
from logic.form_loader import get_timing_marks

from logic.omr_engine import OMREngine
from database import DBManager
from logic.form_loader import(
    load_form, build_rois_from_form, get_anchor_from_form, get_omr_params, get_sheet_code
)

DEFAULT_SCAN_DIR = os.path.join(os.getcwd(), "data", "scan_images")


class ScanPipeline:
    def __init__(self):
        self.db = DBManager()
        self.engine = OMREngine()

        self.current_db_path = None
        self.scan_dir = DEFAULT_SCAN_DIR

        self.form_path = None
        self.form_data = None

    # ====== 외부에서 설정 ======
    def set_project(self, db_path: str | None):
        self.current_db_path = db_path

    def set_scan_dir(self, scan_dir: str):
        self.scan_dir = scan_dir

    def set_form_path(self, form_path: str | None):
        """cb_form 선택 변경 때 호출"""
        self.form_path = form_path
        self.form_data = None
        if form_path and os.path.exists(form_path):
            self.form_data = load_form(form_path)

            # 폼의 omr 파라미터 즉시 적용
            thresh, ratio = get_omr_params(self.form_data)
            self.engine.configure(thresh, ratio)

    # ====== 내부 유틸 ======
    def _get_params_from_db(self):
        """폼 없을 때 fallback: DB settings"""
        ref_x = int(self.db.get_setting(self.current_db_path, "ref_x", "100"))
        ref_y = int(self.db.get_setting(self.current_db_path, "ref_y", "500"))
        anchor = (ref_x, ref_y)

        thresh = self.db.get_setting(self.current_db_path, "omr_threshold", "140")
        ratio = self.db.get_setting(self.current_db_path, "omr_pixel_ratio", "0.25")
        self.engine.configure(thresh, ratio)

        # roi 생성 (네 기존 get_rois 로직과 동일)
        start_y = int(self.db.get_setting(self.current_db_path, "roi_start_y", "515"))
        gap_y = int(self.db.get_setting(self.current_db_path, "roi_gap_y", "90"))
        w = int(self.db.get_setting(self.current_db_path, "roi_w", "35"))
        h = int(self.db.get_setting(self.current_db_path, "roi_h", "35"))
        x_agree = int(self.db.get_setting(self.current_db_path, "roi_agree_x", "1130"))
        x_disagree = int(self.db.get_setting(self.current_db_path, "roi_disagree_x", "1275"))

        rois = []
        for i in range(5):
            y = start_y + (i * gap_y)
            rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])

        sheet_code = self.db.get_setting(self.current_db_path, "sheet_code", "OMR_V1")
        return rois, anchor, sheet_code

    def _result_to_string(self, results):
        """results -> '01231' 규칙(네 코드와 동일)"""
        s = ""
        for r in results:
            if len(r["marked"]) == 0:
                val = "0"
            elif len(r["marked"]) > 1:
                val = "3"
            elif 0 in r["marked"]:
                val = "1"
            elif 1 in r["marked"]:
                val = "2"
            else:
                val = "0"
            s += val
        return s

    # ====== 메인 ======
    def process_image(self, image_path: str, read_num: int, place: str, room: str) -> list[str]:
        # 0) 폼/DB 파라미터 준비
        if self.form_data:
            rois = build_rois_from_form(self.form_data)
            anchor = get_anchor_from_form(self.form_data)
            sheet_code = get_sheet_code(self.form_data)

            thresh, ratio = get_omr_params(self.form_data)
            self.engine.configure(thresh, ratio)

            # =========================================================
            # ✅ [여기부터] 이미지 1번 로드 + 타이밍마크 dx/dy + deskew
            # =========================================================
            img = None
            try:
                arr = np.fromfile(image_path, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception:
                img = None

            if img is None:
                # 이미지 로드 실패
                status, results, debug_img = "ERROR", [], None
            else:
                dx = 0
                dy = 0

                marks = get_timing_marks(self.form_data)

                # ===== Step C: 원근보정(warp) 먼저 시도 =====
                warped_ok = False
                img_to_read = img  # 기본은 원본

                mark_map = {m.get("name"): m for m in marks} if marks else {}
                need = ["TL", "TR", "BL", "BR"]

                if all(k in mark_map for k in need):
                    found_pts = {}
                    for k in need:
                        m = mark_map[k]
                        rect = (
                            int(m["x"]),
                            int(m["y"]),
                            int(m.get("w", 80)),
                            int(m.get("h", 80)),
                        )
                        pt = find_timing_mark(img, rect)
                        if pt:
                            found_pts[k] = pt

                    if all(k in found_pts for k in need):
                        src_pts = [
                            found_pts["TL"],
                            found_pts["TR"],
                            found_pts["BR"],
                            found_pts["BL"],
                        ]
                        dst_pts = [
                            (int(mark_map["TL"]["x"]), int(mark_map["TL"]["y"])),
                            (int(mark_map["TR"]["x"]), int(mark_map["TR"]["y"])),
                            (int(mark_map["BR"]["x"]), int(mark_map["BR"]["y"])),
                            (int(mark_map["BL"]["x"]), int(mark_map["BL"]["y"])),
                        ]

                        h, w = img.shape[:2]
                        img_to_read, _ = warp_to_form(img, src_pts, dst_pts, (w, h))
                        warped_ok = True

                # ===== fallback: warp 실패시에만 dx/dy + deskew 수행 =====
                if not warped_ok:
                    # --- dx/dy 계산 (오프셋 보정) ---
                    if marks:
                        diffs = []
                        for m in marks:
                            rect = (
                                int(m["x"]),
                                int(m["y"]),
                                int(m.get("w", 60)),
                                int(m.get("h", 60))
                            )
                            found = find_timing_mark(img, rect)
                            if found:
                                fx, fy = found
                                diffs.append((fx - int(m["x"]), fy - int(m["y"])))

                        if diffs:
                            dx = int(sum(d[0] for d in diffs) / len(diffs))
                            dy = int(sum(d[1] for d in diffs) / len(diffs))

                    # rois/anchor에 오프셋 적용
                    if dx != 0 or dy != 0:
                        shifted = []
                        for pair in rois:
                            (ax, ay, aw, ah), (bx, by, bw, bh) = pair
                            shifted.append([
                                (ax + dx, ay + dy, aw, ah),
                                (bx + dx, by + dy, bw, bh)
                            ])
                        rois = shifted
                        anchor = (anchor[0] + dx, anchor[1] + dy)

                    # --- deskew (회전) ---
                    angle_deg = 0.0
                    tl = mark_map.get("TL")
                    tr = mark_map.get("TR")

                    if tl and tr:
                        tl_rect = (int(tl["x"]) + dx, int(tl["y"]) + dy, int(tl.get("w", 60)), int(tl.get("h", 60)))
                        tr_rect = (int(tr["x"]) + dx, int(tr["y"]) + dy, int(tr.get("w", 60)), int(tr.get("h", 60)))

                        tl_found = find_timing_mark(img, tl_rect)
                        tr_found = find_timing_mark(img, tr_rect)

                        if tl_found and tr_found:
                            x1, y1 = tl_found
                            x2, y2 = tr_found

                            import math
                            angle_rad = math.atan2((y2 - y1), (x2 - x1))
                            angle_deg = angle_rad * 180.0 / math.pi

                            if abs(angle_deg) > 15:
                                angle_deg = 0.0

                    img_to_read = img
                    if abs(angle_deg) > 0.01:
                        img_to_read, _ = rotate_image_keep_size(img, -angle_deg)
                
                print(f"[WARP] {'OK' if warped_ok else 'FAIL'} | dx={dx} dy={dy}")

                # ✅ 핵심: 엔진을 cv 이미지로 호출
                status, results, debug_img = self.engine.analyze_sheet_cv(img_to_read, rois, anchor)
            # =========================================================
            # ✅ [여기까지] 이미지 보정 + analyze_sheet_cv 호출
            # =========================================================

        else:
            # DB 기반 기존 로직 유지
            rois, anchor, sheet_code = self._get_params_from_db()

            # DB 기반은 기존처럼 path로 호출해도 되지만, 통일하려면 cv로 로드해도 됨
            status, results, debug_img = self.engine.analyze_sheet(image_path, rois, anchor)

        # 2) 결과 문자열 생성 (네 기존 규칙 유지)
        result_str = self._result_to_string(results) if results else ""

        # 3) DB 저장 (db_path 있을 때만)
        if self.current_db_path:
            save_data = {
                "read_num": read_num,
                "place": place,
                "room": room,
                "path": image_path,
                "sheet_code": sheet_code,
                "mark_result": result_str,
                "is_valid": 1 if status == "정상" else 0,
            }
            self.db.insert_scan_result(self.current_db_path, save_data)

        # 4) UI row_data 반환
        row_data = [
            str(read_num),
            sheet_code,
            place,
            room,
            status,
            "완료",
            result_str,
            image_path,
            os.path.basename(image_path),
        ]
        return row_data
