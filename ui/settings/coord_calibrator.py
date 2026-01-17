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


def _overlay_rois(img_bgr: np.ndarray, rois: List[List[Tuple[int, int, int, int]]]) -> np.ndarray:
    """Draw ROI rectangles (red)."""
    out = img_bgr.copy()
    for q in rois:
        for (x, y, w, h) in q:
            cv2.rectangle(out, (int(x), int(y)), (int(x + w), int(y + h)), (0, 0, 255), 2)
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


class CoordCalibratorDialog(QDialog):
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

    # ---------------- Core: Auto + Manual fallback ----------------
    def _analyze(self, use_manual: bool = False):
        if self.form_data is None:
            QMessageBox.warning(self, "경고", "폼을 선택하세요.")
            return
        if self.img_src is None:
            QMessageBox.warning(self, "경고", "이미지를 먼저 불러오세요.")
            return

        rois = build_rois_from_form(self.form_data)
        anchor = get_anchor_from_form(self.form_data)
        thresh, ratio = get_omr_params(self.form_data)
        sheet_code = get_sheet_code(self.form_data)
        marks = get_timing_marks(self.form_data)
        mark_map = {m.get("name"): m for m in marks} if marks else {}

        self._log("========================================")
        self._log(f"[ANALYZE] sheet_code={sheet_code}  omr=(th={thresh}, ratio={ratio})")
        self._log(f"[ANALYZE] anchor={anchor}  questions={int(self.form_data.get('questions', 0) or 0)}")
        self._log(f"[ANALYZE] marks_in_form={list(mark_map.keys())}")

        need4 = ["TL", "TR", "BL", "BR"]
        found_pts = {}
        img_for_search = self.img_src

        # ----------------------------
        # 0) 수동이면 바로 사용
        # ----------------------------
        if use_manual:
            if len(self.manual_points) != 4:
                QMessageBox.warning(self, "경고", "수동 보정은 TL→TR→BL→BR 4점을 모두 클릭해야 합니다.")
                return
            found_pts = {
                "TL": self.manual_points[0],
                "TR": self.manual_points[1],
                "BL": self.manual_points[2],
                "BR": self.manual_points[3],
            }
            self._log(f"[MARKS] manual: {found_pts}")
            # 수동은 warp 바로 시도
            warped_ok, img_to_read = self._warp_with_marks(img_for_search, found_pts, mark_map)
            self._finalize_visual(img_to_read, rois, found_pts, warped_ok)
            return

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
