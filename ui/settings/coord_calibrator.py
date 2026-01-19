import os
import json
import cv2
import numpy as np
from typing import Dict, Tuple, Optional, List

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QComboBox, QTextEdit, QMessageBox, QCheckBox, QGroupBox, QFormLayout,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QPixmap, QImage

# ---- Project imports (existing in your project) ----
from logic.form_loader import (
    list_forms, load_form,
    build_rois_from_form, get_anchor_from_form,
    get_omr_params, get_sheet_code, get_timing_marks
)
from logic.vision.grid_detector import find_timing_mark
from logic.vision.preprocessor import warp_to_form

# If you want to save to DB settings:
try:
    from database import DBManager
except Exception:
    DBManager = None


def _cv_imread_unicode(path: str) -> Optional[np.ndarray]:
    """Windows/Unicode-safe image load."""
    try:
        arr = np.fromfile(path, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _cv_to_qpixmap(img_bgr: np.ndarray) -> QPixmap:
    if img_bgr is None:
        return QPixmap()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    qimg = QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


def _overlay_rois(img_bgr, rois, max_boxes=250):
    """
    ROI를 너무 많이 그리면 UI가 멈춤.
    그래서 전체 ROI 중 일부만 샘플링해서 그린다.
    """
    import cv2
    out = img_bgr.copy()

    # rois 형태:
    # vote: [ [(ax,ay,w,h),(bx,by,w,h)], ... ]
    # exam: [ [(x1,y,w,h),(x2,y,w,h),(x3,y,w,h)...], ... ]
    flat = []
    for row in rois:
        for (x, y, w, h) in row:
            flat.append((int(x), int(y), int(w), int(h)))

    n = len(flat)
    if n == 0:
        return out

    # 샘플링: max_boxes개 이하로만 그림
    if n > max_boxes:
        step = max(1, n // max_boxes)
        flat = flat[::step]

    for (x, y, w, h) in flat:
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 0, 255), 2)

    return out


def _draw_mark_points(img_bgr: np.ndarray, found_pts: Dict[str, Tuple[int, int]]) -> np.ndarray:
    """Draw found timing marks (yellow circles + labels)."""
    out = img_bgr.copy()
    for name, (x, y) in found_pts.items():
        cv2.circle(out, (int(x), int(y)), 10, (0, 255, 255), 3)
        cv2.putText(out, name, (int(x) + 12, int(y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    return out


def _put_status_text(img_bgr: np.ndarray, text: str, ok: bool) -> np.ndarray:
    out = img_bgr.copy()
    color = (0, 255, 0) if ok else (0, 0, 255)
    cv2.putText(out, text, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)
    return out

def warp_perspective(img_bgr, src_pts, dst_pts, out_size):
    import cv2
    import numpy as np
    src = np.array(src_pts, dtype=np.float32)
    dst = np.array(dst_pts, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(img_bgr, M, out_size)
    return warped


class CoordCalibratorDialog(QDialog):
    def auto_detect_exam_layout(self, img_bgr, form_data: dict):
        """
        시험 OMR 자동 탐지:
        - 분홍/보라 계열 원 버블 검출
        - y방향 반복 → 문항 수
        - x방향 반복 → 선택지 수
        - ROI 자동 생성
        """
        import cv2
        import numpy as np

        H, W = img_bgr.shape[:2]

        # 1) 분홍/보라 계열 마스크 (HSV)
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

        # 분홍~보라 범위 (OMR 인쇄색에 맞춤)
        lower = np.array([125, 40, 40])
        upper = np.array([165, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)

        # 2) 노이즈 제거
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        # 3) 컨투어 기반 원 후보
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        circles = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area < 40:
                continue
            x, y, w, h = cv2.boundingRect(c)
            if w < 8 or h < 8:
                continue

            peri = cv2.arcLength(c, True)
            if peri < 1:
                continue
            circularity = 4.0 * np.pi * area / (peri * peri + 1e-6)
            if circularity < 0.45:
                continue

            cx = x + w / 2.0
            cy = y + h / 2.0
            r = (w + h) / 4.0
            circles.append((cx, cy, r))

        if len(circles) < 20:
            return False


        circles = np.array(circles, dtype=np.float32)

        # 4) y방향 클러스터 → 문항 수
        ys = circles[:, 1]
        ys_sorted = np.sort(ys)

        diffs = []
        for i in range(1, len(ys_sorted)):
            d = ys_sorted[i] - ys_sorted[i-1]
            if 8 < d < 120:
                diffs.append(d)

        if not diffs:
            raise RuntimeError("cannot estimate question gap")

        gap_y = int(np.median(diffs))

        groups = []
        for y in ys_sorted:
            if not groups:
                groups.append([y])
            else:
                if abs(y - np.mean(groups[-1])) < gap_y * 0.45:
                    groups[-1].append(y)
                else:
                    groups.append([y])

        questions = len(groups)

        # 5) x방향 클러스터 → 선택지 수
        xs = circles[:, 0].reshape(-1, 1)
        # 선택지는 보통 4~5개 → k-means 시도
        best_k = None
        best_var = None
        centers_x = None

        for k in (4, 5):
            if len(xs) < k:
                continue
            _ret, labels, centers = cv2.kmeans(
                xs.astype(np.float32), k, None,
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.2),
                5, cv2.KMEANS_PP_CENTERS
            )
            var = np.var(centers)
            if best_var is None or var < best_var:
                best_var = var
                best_k = k
                centers_x = sorted([c[0] for c in centers])

        if centers_x is None:
            raise RuntimeError("cannot estimate choice columns")

        choices = len(centers_x)

        # 6) ROI 크기 추정
        r_med = float(np.median(circles[:, 2]))
        roi_w = int(max(16, min(50, r_med * 2.1)))
        roi_h = roi_w

        start_y = int(np.mean(groups[0]))

        # 7) form_data 반영
        form_data["questions"] = int(questions)
        form_data["choices"] = int(choices)

        form_data.setdefault("roi", {})
        form_data["roi"].update({
            "start_y": int(start_y),
            "gap_y": int(gap_y),
            "w": int(roi_w),
            "h": int(roi_h),
            # 객관식은 x 리스트로 저장
            "choice_x": [int(cx - roi_w // 2) for cx in centers_x],
        })

        self._log(f"[AUTO-EXAM] questions={questions}, choices={choices}")
        self._log(f"[AUTO-EXAM] start_y={start_y}, gap_y={gap_y}, w={roi_w}")
        self._log(f"[AUTO-EXAM] choice_x={form_data['roi']['choice_x']}")

        return form_data

    def auto_detect_vote_layout(self, img_bgr, form_data: dict) -> bool:
        """
        찬반표(2열) 자동 탐지 (안전 버전):
        - 빨간 원(또는 붉은 테두리) 버블들을 찾아서
        - questions(문항수) / roi(agree_x, disagree_x, start_y, gap_y, w, h) 자동 추정
        ✅ 실패해도 raise 하지 않고 False 반환 (프로그램 종료 방지)
        ✅ 성공하면 form_data를 업데이트하고 True 반환
        """
        import cv2
        import numpy as np

        try:
            if img_bgr is None:
                self._log("[AUTO-VOTE] img is None")
                return False

            H, W = img_bgr.shape[:2]
            if H < 50 or W < 50:
                self._log(f"[AUTO-VOTE] image too small: {W}x{H}")
                return False

            # --- form_data 원본 보호(실패하면 원복) ---
            original_roi = None
            original_questions = form_data.get("questions", None)
            if "roi" in form_data:
                original_roi = dict(form_data["roi"]) if isinstance(form_data["roi"], dict) else None

            # 1) HSV 변환
            hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)

            # (옵션) 채도/명도 약한 스캔 대비: S/V가 낮으면 마스크가 비어버림
            # → 하한을 너무 높게 두지 말고 조금 완화
            lower1 = np.array([0, 25, 25], dtype=np.uint8)
            upper1 = np.array([12, 255, 255], dtype=np.uint8)
            lower2 = np.array([168, 25, 25], dtype=np.uint8)
            upper2 = np.array([180, 255, 255], dtype=np.uint8)

            mask1 = cv2.inRange(hsv, lower1, upper1)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            mask = cv2.bitwise_or(mask1, mask2)

            # 2) 노이즈 제거
            # 이미지 크기에 따라 커널을 약간 조절 (너무 작으면 잡음, 너무 크면 버블 소실)
            k = 5 if min(H, W) < 2000 else 7
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

            # 3) 컨투어 기반 원 후보
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            circles = []
            for c in cnts:
                area = cv2.contourArea(c)
                # 스캔에 따라 면적이 들쑥날쑥 -> 너무 낮지만 않게
                if area < 20:
                    continue

                x, y, w, h = cv2.boundingRect(c)

                # 크기 필터(너무 작은 잡음/너무 큰 도장 등 제거)
                if w < 6 or h < 6:
                    continue
                if w > W * 0.25 or h > H * 0.25:
                    continue

                peri = cv2.arcLength(c, True)
                if peri < 1:
                    continue

                circularity = 4.0 * np.pi * area / (peri * peri + 1e-6)

                # '원형'이 완벽하지 않아도 통과시키되,
                # 너무 찌그러진 건 제외
                if circularity < 0.30:
                    continue

                cx = x + w / 2.0
                cy = y + h / 2.0
                r = (w + h) / 4.0
                circles.append((cx, cy, r, area))

            # 잡음이 너무 많으면 면적 큰 것 위주로 상위 N개만 사용
            if len(circles) > 500:
                circles.sort(key=lambda t: t[3], reverse=True)
                circles = circles[:500]

            # ✅ 실패 시 raise 금지
            if len(circles) < 6:
                self._log(f"[AUTO-VOTE] red bubbles not enough: {len(circles)} -> FAIL")
                # 원복
                if original_roi is not None:
                    form_data["roi"] = original_roi
                if original_questions is not None:
                    form_data["questions"] = original_questions
                return False

            circles_np = np.array([(c[0], c[1], c[2]) for c in circles], dtype=np.float32)

            # 4) x축 2열 클러스터링(k=2)
            xs = circles_np[:, 0].reshape(-1, 1)

            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.2)
            ret, labels, centers = cv2.kmeans(xs.astype(np.float32), 2, None, criteria, 10, cv2.KMEANS_PP_CENTERS)

            centers = [float(c[0]) for c in centers]
            centers.sort()
            agree_center_x = centers[0]
            disagree_center_x = centers[1]

            # 열 간격이 너무 좁으면(클러스터가 의미 없음) 실패
            if abs(disagree_center_x - agree_center_x) < max(30, W * 0.05):
                self._log(f"[AUTO-VOTE] column centers too close: {agree_center_x:.1f}, {disagree_center_x:.1f} -> FAIL")
                if original_roi is not None:
                    form_data["roi"] = original_roi
                if original_questions is not None:
                    form_data["questions"] = original_questions
                return False

            # 5) y축 간격(gap) 추정
            ys = np.sort(circles_np[:, 1])
            diffs = []
            for i in range(1, len(ys)):
                d = float(ys[i] - ys[i - 1])
                if 8 < d < 260:   # 약간 완화
                    diffs.append(d)

            if not diffs:
                self._log("[AUTO-VOTE] cannot estimate gap_y -> FAIL")
                if original_roi is not None:
                    form_data["roi"] = original_roi
                if original_questions is not None:
                    form_data["questions"] = original_questions
                return False

            gap_y = float(np.median(diffs))
            if gap_y < 8:
                self._log(f"[AUTO-VOTE] gap_y too small: {gap_y:.2f} -> FAIL")
                if original_roi is not None:
                    form_data["roi"] = original_roi
                if original_questions is not None:
                    form_data["questions"] = original_questions
                return False

            # 6) y를 gap_y 기준으로 그룹핑해서 문항 수 추정
            groups = []
            for y in ys:
                if not groups:
                    groups.append([float(y)])
                else:
                    if abs(float(y) - float(np.mean(groups[-1]))) < gap_y * 0.45:
                        groups[-1].append(float(y))
                    else:
                        groups.append([float(y)])

            questions = len(groups)

            # 현실적인 문항수 범위로 가드(투표지에 0/1/2 같은 이상치 방지)
            if questions < 3 or questions > 200:
                self._log(f"[AUTO-VOTE] questions out of range: {questions} -> FAIL")
                if original_roi is not None:
                    form_data["roi"] = original_roi
                if original_questions is not None:
                    form_data["questions"] = original_questions
                return False

            start_y = float(np.mean(groups[0]))

            # 7) ROI 크기 추정
            r_med = float(np.median(circles_np[:, 2]))
            roi_w = int(max(14, min(70, r_med * 2.2)))
            roi_h = roi_w

            # x는 "센터"를 기준으로 ROI 좌상단으로 변환
            agree_x = int(round(agree_center_x - roi_w / 2))
            disagree_x = int(round(disagree_center_x - roi_w / 2))

            # 경계 가드
            agree_x = max(0, min(W - roi_w - 1, agree_x))
            disagree_x = max(0, min(W - roi_w - 1, disagree_x))
            start_y_int = int(round(start_y))
            start_y_int = max(0, min(H - roi_h - 1, start_y_int))
            gap_y_int = int(round(gap_y))

            # 8) form_data 반영
            form_data["questions"] = int(questions)
            form_data.setdefault("roi", {})
            if not isinstance(form_data["roi"], dict):
                form_data["roi"] = {}

            form_data["roi"].update({
                "start_y": int(start_y_int),
                "gap_y": int(gap_y_int),
                "w": int(roi_w),
                "h": int(roi_h),
                "agree_x": int(agree_x),
                "disagree_x": int(disagree_x),
            })

            self._log(f"[AUTO-VOTE] OK  questions={questions}, start_y={start_y_int}, gap_y={gap_y_int}, w={roi_w}")
            self._log(f"[AUTO-VOTE] OK  agree_x={agree_x}, disagree_x={disagree_x}")

            return True

        except Exception as e:
            # ✅ 어떤 예외든 앱을 죽이지 말고 실패 처리
            self._log(f"[AUTO-VOTE] exception: {e} -> FAIL")
            return False


    def _warp_with_marks(self, img, found_pts, mark_map):
        """
        found_pts: {"TL":(x,y), "TR":..., "BL":..., "BR":...} 실제 검출 좌표
        mark_map : form_data["timing_marks"] 기반 기준 좌표
        return: (warped_ok, img_to_read)
        """
        need = ["TL", "TR", "BL", "BR"]
        if not all(k in found_pts for k in need):
            return False, img

        if not all(k in mark_map for k in need):
            return False, img

        src_pts = [found_pts["TL"], found_pts["TR"], found_pts["BR"], found_pts["BL"]]
        dst_pts = [
            (int(mark_map["TL"]["x"]), int(mark_map["TL"]["y"])),
            (int(mark_map["TR"]["x"]), int(mark_map["TR"]["y"])),
            (int(mark_map["BR"]["x"]), int(mark_map["BR"]["y"])),
            (int(mark_map["BL"]["x"]), int(mark_map["BL"]["y"])),
        ]
        h, w = img.shape[:2]
        try:
            warped, _ = warp_to_form(img, src_pts, dst_pts, (w, h))
            return True, warped
        except Exception as e:
            self._log(f"[WARP] error: {e}")
            return False, img


    def _finalize_visual(self, img_to_read, rois, found_pts, warped_ok: bool):
        """
        결과 시각화(ROI + marks + status) + 화면 갱신
        """
        self.warped_ok = warped_ok
        self.img_warped = img_to_read.copy() if warped_ok else None

        vis = img_to_read.copy()
        vis = _overlay_rois(vis, rois)
        vis = _draw_mark_points(vis, found_pts)
        vis = _put_status_text(vis, "WARP OK" if warped_ok else "WARP FAIL", warped_ok)

        if (not warped_ok) and self.chk_manual.isChecked():
            vis = _put_status_text(vis, "AUTO FAIL -> MANUAL CLICK TL TR BL BR", False)

        self.img_vis = vis
        self._refresh_view()

        
        """
        좌표설정/캘리브레이터:
        - 완전 자동: timing_marks (TL/TR/BL/BR) 자동탐지 -> warp -> ROI overlay 확인
        - 실패 시 수동: TL->TR->BL->BR 순서로 클릭 -> warp 재시도
        - (선택) DB(tblSettings) 저장 / 폼 JSON 저장
     """

    def _estimate_questions_vote(self, img_warped: np.ndarray, form_data: dict) -> int:
        """
        찬반(2열) 폼에서 질문 수를 자동 추정한다.
        ROI x영역(agree/disagree) 주변에서 y방향 밀도 peak를 세어 row 수를 계산.
        """
        roi = form_data.get("roi", {})
        start_y = int(roi.get("start_y", 0))
        gap_y = int(roi.get("gap_y", 80))
        w = int(roi.get("w", 35))
        agree_x = int(roi.get("agree_x", 0))
        disagree_x = int(roi.get("disagree_x", agree_x + 150))

        if img_warped is None:
            return int(form_data.get("questions", 5))

        H, W = img_warped.shape[:2]

        x1 = max(0, min(agree_x, disagree_x) - 40)
        x2 = min(W, max(agree_x, disagree_x) + w + 40)

        y1 = max(0, start_y - 30)
        y2 = H - 10

        crop = img_warped[y1:y2, x1:x2]
        if crop.size == 0:
            return int(form_data.get("questions", 5))

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        binv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                    cv2.THRESH_BINARY_INV, 31, 10)

        density = binv.mean(axis=1)  # 0~255
        k = 15
        kernel = np.ones(k) / k
        smooth = np.convolve(density, kernel, mode="same")

        thr = max(20, float(smooth.mean() + smooth.std() * 0.8))

        peaks = []
        for i in range(1, len(smooth) - 1):
            if smooth[i] > thr and smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
                peaks.append(i)

        if not peaks:
            return int(form_data.get("questions", 5))

        clusters = [peaks[0]]
        sep = max(25, int(gap_y * 0.5))
        for p in peaks[1:]:
            if abs(p - clusters[-1]) > sep:
                clusters.append(p)

        q_est = len(clusters)
        if q_est < 1:
            q_est = int(form_data.get("questions", 5))
        if q_est > 200:
            q_est = 200
        return int(q_est)

    def __init__(self, parent=None, db_path: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("좌표설정 / 캘리브레이션 (자동 → 실패시 클릭 보정)")
        self.resize(1300, 780)

        # Optional project db
        self.db_path = db_path
        self.db = DBManager() if DBManager else None

        # form state
        self.form_path: Optional[str] = None
        self.form_data: Optional[dict] = None

        # image state
        self.image_path: Optional[str] = None
        self.img_src: Optional[np.ndarray] = None           # original
        self.img_warped: Optional[np.ndarray] = None        # warped image (if warp ok)
        self.img_vis: Optional[np.ndarray] = None           # visualization (warped/original + overlays)

        # detection state
        self.found_pts: Dict[str, Tuple[int, int]] = {}
        self.warped_ok: bool = False
        self.last_dxdy: Tuple[int, int] = (0, 0)

        # manual click fallback
        self.manual_points: List[Tuple[int, int]] = []
        self.manual_names = ["TL", "TR", "BL", "BR"]

        # view state
        self.show_warped: bool = True

        self._build_ui()
        self._load_forms()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QHBoxLayout(self)

        # LEFT: Graphics view
        left = QVBoxLayout()

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)  # hand-drag
        self.view.viewport().installEventFilter(self)

        left.addWidget(self.view, 1)

        self.pix_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pix_item)

        bottom_row = QHBoxLayout()
        self.chk_show_warped = QCheckBox("보정(warp) 결과 보기")
        self.chk_show_warped.setChecked(True)
        self.chk_show_warped.stateChanged.connect(self._refresh_view)
        bottom_row.addWidget(self.chk_show_warped)

        self.chk_manual = QCheckBox("수동 보정 모드(자동 실패 시 클릭)")
        self.chk_manual.setChecked(False)
        bottom_row.addWidget(self.chk_manual)

        self.btn_reset_clicks = QPushButton("클릭 리셋")
        self.btn_reset_clicks.clicked.connect(self._reset_manual_points)
        bottom_row.addWidget(self.btn_reset_clicks)

        bottom_row.addStretch(1)
        left.addLayout(bottom_row)

        self.lbl_hint = QLabel("수동모드 ON 시: TL → TR → BL → BR 순서로 4점을 클릭하세요.")
        self.lbl_hint.setStyleSheet("color:#555;")
        left.addWidget(self.lbl_hint)

        root.addLayout(left, 7)

        # RIGHT: controls + logs
        right = QVBoxLayout()

        grp = QGroupBox("캘리브레이션")
        form = QFormLayout(grp)

        self.cb_form = QComboBox()
        self.cb_form.currentIndexChanged.connect(self._on_form_changed)
        form.addRow("폼 선택", self.cb_form)

        self.btn_pick_img = QPushButton("📂 이미지 선택")
        self.btn_pick_img.clicked.connect(self._pick_image)
        form.addRow("입력 이미지", self.btn_pick_img)

        self.btn_analyze = QPushButton("🔎 자동 분석(마크 탐지 → 원근보정 → ROI 표시)")
        self.btn_analyze.clicked.connect(lambda: self._analyze(use_manual=False))
        form.addRow("분석", self.btn_analyze)

        self.btn_analyze_manual = QPushButton("🖱 수동 보정으로 재시도(4점 클릭 후)")
        self.btn_analyze_manual.clicked.connect(lambda: self._analyze(use_manual=True))
        form.addRow("수동 재시도", self.btn_analyze_manual)

        # Save controls
        self.btn_save_db = QPushButton("💾 현재 값 DB(tblSettings)에 저장")
        self.btn_save_db.clicked.connect(self._save_to_db)
        form.addRow("저장", self.btn_save_db)

        self.btn_save_json = QPushButton("💾 폼 JSON 저장(선택: 탐색창 w/h만 수정 등)")
        self.btn_save_json.clicked.connect(self._save_form_json)
        form.addRow("", self.btn_save_json)

        right.addWidget(grp)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        right.addWidget(QLabel("로그"))
        right.addWidget(self.txt_log, 1)

        root.addLayout(right, 3)

    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else (1 / 1.15)
        self.view.scale(factor, factor)

    def eventFilter(self, obj, event):
        # Manual clicks (viewport events)
        if self.chk_manual.isChecked() and event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if self.img_src is None:
                return True

            pos = event.pos()
            scene_pos = self.view.mapToScene(pos)
            x, y = int(scene_pos.x()), int(scene_pos.y())

            if len(self.manual_points) < 4:
                self.manual_points.append((x, y))
                name = self.manual_names[len(self.manual_points) - 1]
                self._log(f"[MANUAL] {name} = ({x},{y})")

                # Quick visualize point on current visualization
                base = self.img_vis if self.img_vis is not None else self.img_src
                temp = base.copy()
                for i, (px, py) in enumerate(self.manual_points):
                    nm = self.manual_names[i]
                    cv2.circle(temp, (px, py), 10, (0, 255, 255), 3)
                    cv2.putText(temp, nm, (px + 12, py), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                self.img_vis = temp
                self._refresh_view()

                if len(self.manual_points) == 4:
                    self._log("[MANUAL] 4점 입력 완료. '수동 보정으로 재시도' 버튼을 누르거나, 자동으로 재시도합니다.")
                    # Auto retry once user completes 4 points
                    self._analyze(use_manual=True)

            return True

        return super().eventFilter(obj, event)

    # ---------------- Helpers ----------------
    def _log(self, msg: str):
        self.txt_log.append(msg)
        # Auto-scroll to bottom
        self.txt_log.moveCursor(self.txt_log.textCursor().End)

    def _load_forms(self):
        self.cb_form.clear()
        forms = list_forms()  # (form_id, display, path)
        if not forms:
            self.cb_form.addItem("폼 없음 (resources/forms)", userData=None)
            self._on_form_changed()
            return

        for form_id, display, path in forms:
            self.cb_form.addItem(display, userData=path)

        self._on_form_changed()

    def _on_form_changed(self):
        path = self.cb_form.currentData()
        self.form_path = path
        if path and os.path.exists(path):
            try:
                self.form_data = load_form(path)
                self._log(f"[FORM] loaded: {path}")
            except Exception as e:
                self.form_data = None
                self._log(f"[FORM] load failed: {e}")
        else:
            self.form_data = None
            if path:
                self._log(f"[FORM] not found: {path}")

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "OMR 이미지 선택", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if not path:
            return
        self.image_path = path
        self.img_src = _cv_imread_unicode(path)
        self.img_warped = None
        self.img_vis = None
        self.found_pts = {}
        self.warped_ok = False
        self.last_dxdy = (0, 0)
        self.manual_points = []

        if self.img_src is None:
            QMessageBox.critical(self, "오류", "이미지 로드 실패")
            return

        self._log(f"[IMG] loaded: {path} ({self.img_src.shape[1]}x{self.img_src.shape[0]})")
        # show original immediately
        self.img_vis = self.img_src.copy()
        self._refresh_view()

    def _reset_manual_points(self):
        self.manual_points = []
        self._log("[MANUAL] reset clicks")
        # revert view to current auto result if any
        if self.img_warped is not None and self.chk_show_warped.isChecked():
            self.img_vis = self.img_warped.copy()
        elif self.img_src is not None:
            self.img_vis = self.img_src.copy()
        self._refresh_view()

    def _refresh_view(self):
        if self.img_src is None:
            self.pix_item.setPixmap(QPixmap())
            self.scene.update()
            return

        use_warped = self.chk_show_warped.isChecked()
        if use_warped and self.img_vis is not None:
            show = self.img_vis
        else:
            # show source with minimal overlay if needed
            show = self.img_src

        pm = _cv_to_qpixmap(show)
        self.pix_item.setPixmap(pm)
        self.scene.setSceneRect(self.pix_item.boundingRect())
        self.scene.update()

    def _roi_too_many(self, rois, max_boxes=4000) -> bool:
    # rois: [[(x,y,w,h),...], ...] 형태라고 가정
        try:
            cnt = 0
            for row in rois:
                cnt += len(row)
                if cnt > max_boxes:
                    return True
            return False
        except Exception:
            return True

    def _sample_rois(self, rois, max_boxes=2500):
        """
        전체 rois를 flat으로 보고 max_boxes 이하로 샘플링해 다시 같은 구조로 복원.
        (간단히: row 단위는 유지하되, 전체적으로 step 샘플링)
        """
        flat = []
        for row in rois:
            for r in row:
                flat.append(r)

        n = len(flat)
        if n <= max_boxes or n == 0:
            return rois

        step = max(1, n // max_boxes)
        sampled = flat[::step]

        # 원 구조로 복원하기 어렵다면(시험/투표 구조 다양),
        # 여기서는 "그리기용"으로만 쓸 것이므로 1행짜리로 반환해도 됨.
        return [sampled]


    # ---------------- Core: Auto + Manual fallback ----------------
    def _try_warp_once(self, img_src, form_id: str, form_data: dict):
        """
        자동 warp 후보 중 '처음 성공한 1개'만 채택.
        return: (ok, img_warp, used_name, found_pts_dict)
        found_pts_dict는 디버그용(찾은 코너/마크)
        """
        found_pts = {}
        need4 = ["TL", "TR", "BL", "BR"]

        # A) vote면 table corner warp 먼저
        if "vote" in form_id:
            try:
                from logic.vision.table_corner_detector import detect_table_corners
                corners, dbg = detect_table_corners(img_src)
                if corners and all(k in corners for k in need4):
                    H, W = img_src.shape[:2]
                    src_pts = [corners["TL"], corners["TR"], corners["BR"], corners["BL"]]
                    dst_pts = [(0, 0), (W - 1, 0), (W - 1, H - 1), (0, H - 1)]
                    img_warp = warp_perspective(img_src, src_pts, dst_pts, (W, H))
                    return True, img_warp, "table_corners", corners
            except Exception as e:
                self._log(f"[WARP] table_corners exception: {e}")

        # B) timing_marks 기반 warp (form에 기준 좌표가 있을 때)
        try:
            marks = get_timing_marks(form_data)
            mark_map = {m.get("name"): m for m in marks} if marks else {}
            if all(k in mark_map for k in need4):
                from logic.vision.timing_mark_detector import detect_timing_marks
                corners, dbg = detect_timing_marks(img_src)
                if corners and all(k in corners for k in need4):
                    warped_ok, img_warp = self._warp_with_marks(img_src, corners, mark_map)
                    if warped_ok and img_warp is not None:
                        return True, img_warp, "timing_marks", corners
        except Exception as e:
            self._log(f"[WARP] timing_marks exception: {e}")

        # C) black marks 기반 warp (fallback)
        try:
            from logic.vision.grid_detector import find_black_marks, pick_corners_from_marks
            marks_auto = find_black_marks(img_src)
            corners = pick_corners_from_marks(marks_auto, img_src.shape)
            # black-marks로 corners를 찾았더라도, dst 기준이 필요하므로 form timing_marks가 있어야 _warp_with_marks 가능
            marks = get_timing_marks(form_data)
            mark_map = {m.get("name"): m for m in marks} if marks else {}
            if corners and all(k in corners for k in need4) and all(k in mark_map for k in need4):
                warped_ok, img_warp = self._warp_with_marks(img_src, corners, mark_map)
                if warped_ok and img_warp is not None:
                    return True, img_warp, "black_marks", corners
        except Exception as e:
            self._log(f"[WARP] black_marks exception: {e}")

        return False, img_src, "none", found_pts

    def _analyze(self, use_manual: bool = False):
        """
        제품용 안정화 버전:
        - 자동/수동 warp는 1번만 결정
        - 자동 레이아웃(vote/exam)은 실패해도 죽지 않음(False 처리)
        - rois/anchor는 최종 form_data + 최종 img 기준으로 한 번만 계산/표시
        """
        try:
            if self.form_data is None:
                QMessageBox.warning(self, "경고", "폼을 선택하세요.")
                return
            if self.img_src is None:
                QMessageBox.warning(self, "경고", "이미지를 먼저 불러오세요.")
                return

            form_id = (self.form_data.get("form_id", "") or "").lower()

            # -----------------------------------------
            # 0) 분석 대상 이미지(원본) -> img_for_search로 고정
            # -----------------------------------------
            img_for_search = self.img_src

            # -----------------------------------------
            # 1) 수동 warp가 우선(4점 클릭)
            # -----------------------------------------
            warped_ok = False
            used_warp = "none"
            found_pts = {}  # 디버그용

            if use_manual:
                marks = get_timing_marks(self.form_data)
                mark_map = {m.get("name"): m for m in marks} if marks else {}
                need4 = ["TL", "TR", "BL", "BR"]

                if len(self.manual_points) != 4:
                    QMessageBox.warning(self, "경고", "수동 보정은 TL→TR→BL→BR 4점을 모두 클릭해야 합니다.")
                    return

                if not all(k in mark_map for k in need4):
                    QMessageBox.warning(self, "경고", "폼 timing_marks에 TL/TR/BL/BR 기준 좌표가 없습니다.")
                    return

                found_pts = {
                    "TL": self.manual_points[0],
                    "TR": self.manual_points[1],
                    "BL": self.manual_points[2],
                    "BR": self.manual_points[3],
                }

                self._log(f"[WARP] manual points={found_pts}")

                warped_ok, img_warp = self._warp_with_marks(img_for_search, found_pts, mark_map)
                if warped_ok and img_warp is not None:
                    img_for_search = img_warp
                    used_warp = "manual_marks"
                else:
                    used_warp = "manual_failed"

            else:
                # -----------------------------------------
                # 2) 자동 warp는 후보 중 "처음 성공 1개"만 채택
                # -----------------------------------------
                warped_ok, img_warp, used_warp, found_pts = self._try_warp_once(img_for_search, form_id, self.form_data)
                if warped_ok and img_warp is not None:
                    img_for_search = img_warp

            self._log(f"[WARP] ok={warped_ok}, used={used_warp}")

            # ✅ 최종 분석 이미지 확정
            self.img_src = img_for_search

            # -----------------------------------------
            # 3) (선택) 자동 레이아웃 추정 (vote/exam)
            #    - 실패해도 절대 raise 금지 (False 반환 기반)
            # -----------------------------------------
            if not use_manual:
                if "vote" in form_id:
                    ok_layout = self.auto_detect_vote_layout(self.img_src, self.form_data)  # ✅ 반드시 True/False 반환 버전이어야 함
                    if not ok_layout:
                        QMessageBox.information(self, "자동 분석 실패", "투표 레이아웃 자동 추정 실패.\n수동 보정(4점 클릭)으로 진행하세요.")
                        # 실패해도 크래시 말고 여기서 종료
                        # (수동 버튼을 누르게 유도)
                        self._finalize_visual(self.img_src, [], found_pts, False)
                        return

                elif "exam" in form_id or "test" in form_id:
                    # exam도 가능하면 True/False 반환으로 통일 권장
                    ok_layout = self.auto_detect_exam_layout(self.img_src, self.form_data)
                    if ok_layout is False:
                        QMessageBox.information(self, "자동 분석 실패", "시험 레이아웃 자동 추정 실패.\n수동 보정(4점 클릭)으로 진행하세요.")
                        self._finalize_visual(self.img_src, [], found_pts, False)
                        return

            # -----------------------------------------
            # 4) 최종 form_data 기준으로 rois/anchor/omr 설정 계산
            # -----------------------------------------
            rois = build_rois_from_form(self.form_data)
            anchor = get_anchor_from_form(self.form_data)
            thresh, ratio = get_omr_params(self.form_data)
            sheet_code = get_sheet_code(self.form_data)

            self._log("========================================")
            self._log(f"[ANALYZE] form_id={form_id}")
            self._log(f"[ANALYZE] sheet_code={sheet_code}  omr=(th={thresh}, ratio={ratio})")
            self._log(f"[ANALYZE] anchor={anchor}  questions={int(self.form_data.get('questions', 0) or 0)}")

            # -----------------------------------------
            # 5) ROI 과다 방지 가드 (문항 많은 시험지에서 크래시/멈춤 예방)
            # -----------------------------------------
            if self._roi_too_many(rois, max_boxes=4000):
                QMessageBox.warning(self, "경고", "문항/선택지가 너무 많아 ROI 표시를 제한합니다.\n(분석 자체는 가능하지만 표시/편집은 수동 권장)")
                # 표시만 제한하고 진행은 계속하거나, 여기서 return해도 됨.
                # 여기서는 표시만 제한: rois를 샘플링된 rois로 바꾼다.
                rois = self._sample_rois(rois, max_boxes=2500)

            # -----------------------------------------
            # 6) 시각화/저장 (너의 finalize 함수로 마무리)
            # -----------------------------------------
            self._finalize_visual(self.img_src, rois, found_pts, warped_ok)

        except Exception as e:
            # ✅ Python 예외는 여기서 잡혀서 메시지로만 보여줌(프로그램 종료 방지)
            import traceback
            self._log("[ANALYZE] exception:\n" + traceback.format_exc())
            QMessageBox.critical(self, "오류", str(e))


        # ----------------------------
        # 1) 자동 1차: 4개 다 찾기 시도
        # ----------------------------
        def _auto_find(names, img, win_list):
            
            for ws in win_list:
                tmp = {}
                for k in names:
                    if k not in mark_map:
                        continue
                    m = mark_map[k]
                    ww = max(int(m.get("w", ws)), ws)
                    hh = max(int(m.get("h", ws)), ws)
                    rect = (int(m["x"]), int(m["y"]), ww, hh)
                    pt = find_timing_mark(img, rect)
                    if pt:
                        tmp[k] = (int(pt[0]), int(pt[1]))
                self._log(f"[MARKS] auto ws={ws} -> {list(tmp.keys())}")
                if all(k in tmp for k in names):
                    return tmp
            return {}

        # 1차는 조금만
        found_pts = _auto_find(need4, img_for_search, [80, 140, 220])

        if all(k in found_pts for k in need4):
            self._log("[AUTO] found 4 marks in stage-1")
            warped_ok, img_to_read = self._warp_with_marks(img_for_search, found_pts, mark_map)
            self._finalize_visual(img_to_read, rois, found_pts, warped_ok)
            return

        # ----------------------------
        # 2) 자동 2차(핵심): TL/TR만 먼저 찾고 회전(deskew) 후 BL/BR 재탐색
        # ----------------------------
        found_lr = _auto_find(["TL", "TR"], img_for_search, [80, 140, 220, 320, 420])
        if not ("TL" in found_lr and "TR" in found_lr):
            self._log("[AUTO] TL/TR not found -> fallback to manual click mode")
            self._finalize_visual(self.img_src, rois, found_lr, False)
            return

        self._log(f"[AUTO] TL/TR found: {found_lr}")

        # TL/TR로 기울기 각도 계산
        (x1, y1) = found_lr["TL"]
        (x2, y2) = found_lr["TR"]
        import math
        angle_rad = math.atan2((y2 - y1), (x2 - x1))
        angle_deg = angle_rad * 180.0 / math.pi

        # 너무 과한 각도는 오검출 가능 -> 제한
        if abs(angle_deg) > 20:
            self._log(f"[AUTO] angle too large({angle_deg:.2f}) -> ignore deskew")
            angle_deg = 0.0
        else:
            self._log(f"[AUTO] deskew angle = {angle_deg:.2f} deg")

        # 회전 보정(기울어진 만큼 반대로)
        img_rot = img_for_search
        if abs(angle_deg) > 0.01:
            try:
                from logic.vision.preprocessor import rotate_image_keep_size
                img_rot, _ = rotate_image_keep_size(img_for_search, -angle_deg)
            except Exception as e:
                self._log(f"[AUTO] rotate_image_keep_size missing? {e}")
                img_rot = img_for_search

        # 회전 보정된 이미지에서 BL/BR 탐색
        found_br = _auto_find(["BL", "BR"], img_rot, [140, 220, 320, 420, 520])
        found_pts = dict(found_lr)
        found_pts.update(found_br)

        if all(k in found_pts for k in need4):
            self._log("[AUTO] found 4 marks after deskew stage-2")
            warped_ok, img_to_read = self._warp_with_marks(img_rot, found_pts, mark_map)
            self._finalize_visual(img_to_read, rois, found_pts, warped_ok)
            return

        # ----------------------------
        # 3) 자동 실패 -> 수동 안내
        # ----------------------------
        self._log("[AUTO] failed to get 4 marks. Turn on manual and click TL/TR/BL/BR.")
        self._finalize_visual(img_rot, rois, found_pts, False)



    # ---------------- Save to DB / JSON ----------------
    def _save_to_db(self):
        """
        Save tuning parameters to DB tblSettings.
        - anchor (ref_x, ref_y)
        - roi (start_y, gap_y, w, h, agree_x, disagree_x)
        - omr threshold params
        Note: This assumes DBManager has set_setting(db_path, key, value)
        """
        if not self.db_path:
            QMessageBox.information(self, "안내", "DB 경로가 없습니다.\n(main_window에서 db_path를 넘기거나, DB 저장을 꺼두세요.)")
            return
        if self.db is None:
            QMessageBox.warning(self, "경고", "DBManager import 실패. database.py 경로/이름을 확인하세요.")
            return
        if self.form_data is None:
            QMessageBox.warning(self, "경고", "폼이 로드되어야 저장할 수 있습니다.")
            return

        # values from form
        anchor = get_anchor_from_form(self.form_data)
        thresh, ratio = get_omr_params(self.form_data)

        roi = (self.form_data or {}).get("roi", {})
        # roi keys - safe defaults
        start_y = roi.get("start_y")
        gap_y = roi.get("gap_y")
        w = roi.get("w")
        h = roi.get("h")
        agree_x = roi.get("agree_x")
        disagree_x = roi.get("disagree_x")

        # If you want: store detected marks too (optional)
        # We store only tuning values that influence reading.
        try:
            self.db.set_setting(self.db_path, "ref_x", str(anchor[0]))
            self.db.set_setting(self.db_path, "ref_y", str(anchor[1]))
            self.db.set_setting(self.db_path, "omr_threshold", str(thresh))
            self.db.set_setting(self.db_path, "omr_pixel_ratio", str(ratio))

            if start_y is not None: self.db.set_setting(self.db_path, "roi_start_y", str(start_y))
            if gap_y is not None: self.db.set_setting(self.db_path, "roi_gap_y", str(gap_y))
            if w is not None: self.db.set_setting(self.db_path, "roi_w", str(w))
            if h is not None: self.db.set_setting(self.db_path, "roi_h", str(h))
            if agree_x is not None: self.db.set_setting(self.db_path, "roi_agree_x", str(agree_x))
            if disagree_x is not None: self.db.set_setting(self.db_path, "roi_disagree_x", str(disagree_x))

            self._log("[SAVE][DB] OK (tblSettings updated)")
            QMessageBox.information(self, "저장 완료", "DB(tblSettings)에 저장했습니다.")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))

    def _save_form_json(self):
        """
        Save form JSON. (Safe policy)
        - 기본적으로는 '폼의 좌표(roi/anchor)'를 자동 덮어쓰기보다,
          'timing_marks의 w/h(탐색창)' 조정 같은 안전한 변경부터 추천.
        - 여기서는: 사용자가 원하면 timing_marks w/h를 현재 자동 윈도우 확장에 맞춰 키울 수 있게 함.
        """
        if not self.form_path or not self.form_data:
            QMessageBox.warning(self, "경고", "폼이 로드되어야 저장할 수 있습니다.")
            return

        # Ask save location
        save_path, _ = QFileDialog.getSaveFileName(
            self, "폼 JSON 저장", self.form_path, "JSON (*.json)"
        )
        if not save_path:
            return

        # Safe update example: ensure timing_marks have w/h (bigger search windows)
        # You can edit this policy later.
        data = dict(self.form_data)
        marks = data.get("timing_marks", [])

        # If user already has marks, ensure w/h at least 120 for stability
        new_marks = []
        for m in marks:
            mm = dict(m)
            mm["w"] = max(int(mm.get("w", 80)), 120)
            mm["h"] = max(int(mm.get("h", 80)), 120)
            new_marks.append(mm)
        data["timing_marks"] = new_marks

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"[SAVE][JSON] OK -> {save_path}")
            QMessageBox.information(self, "저장 완료", "폼 JSON 저장 완료")
        except Exception as e:
            QMessageBox.critical(self, "저장 실패", str(e))
