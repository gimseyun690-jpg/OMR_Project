# ui/settings/coord_calibrator.py
import os
import json
import cv2
import numpy as np
import traceback
from typing import Optional, List, Tuple, Dict

from PySide2.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QComboBox, QTextEdit, QMessageBox, QCheckBox, QGroupBox, QFormLayout,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QSizePolicy
)
from PySide2.QtCore import Qt, QEvent
from PySide2.QtGui import QPixmap, QImage

# ---- project imports ----
from logic.form_loader import list_forms, load_form
from logic.vision.preprocessor import warp_to_form
from logic.vision.timing_mark_detector import detect_timing_marks


# ----------------- Utils -----------------
def cv_imread_unicode(path: str) -> Optional[np.ndarray]:
    try:
        arr = np.fromfile(path, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception:
        return None

def cv_to_qpixmap(img_bgr: np.ndarray) -> QPixmap:
    if img_bgr is None:
        return QPixmap()
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = img_rgb.shape
    bytes_per_line = ch * w
    qimg = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)

def order_quad_tl_tr_br_bl(pts4: np.ndarray) -> np.ndarray:
    """(4,2) -> TL,TR,BR,BL"""
    pts = np.asarray(pts4, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(d)]
    bl = pts[np.argmax(d)]
    return np.array([tl, tr, br, bl], dtype=np.float32)

def draw_points(img_bgr: np.ndarray, pts: Dict[str, Tuple[int,int]], color=(0, 255, 255)) -> np.ndarray:
    out = img_bgr.copy()
    for name, (x, y) in pts.items():
        cv2.circle(out, (int(x), int(y)), 10, color, -1)
        cv2.putText(out, name, (int(x) + 12, int(y)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    return out

def overlay_rois(img_bgr: np.ndarray, rois_2d, color=(0,0,255), thickness=2) -> np.ndarray:
    out = img_bgr.copy()
    for row in rois_2d or []:
        for r in row or []:
            if not r or len(r) != 4:
                continue
            x,y,w,h = map(int, r)
            cv2.rectangle(out, (x,y), (x+w, y+h), color, thickness)
    return out

def overlay_roi_labels(img_bgr: np.ndarray, rois_2d, color=(0,0,255)) -> np.ndarray:
    out = img_bgr.copy()
    for qi, row in enumerate(rois_2d or [], start=1):
        for oi, r in enumerate(row or [], start=1):
            if not r or len(r) != 4:
                continue
            x,y,w,h = map(int, r)
            label = f"Q{qi:02d}-O{oi}"
            tx = max(0, x + w + 4)
            ty = max(0, y + 18)
            cv2.putText(out, label, (tx, ty),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return out

def clamp_rect(W, H, x, y, w, h):
    x1 = max(0, int(x))
    y1 = max(0, int(y))
    x2 = min(W, int(x) + int(w))
    y2 = min(H, int(y) + int(h))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2 - x1, y2 - y1)

def quad_area(pts4: List[Tuple[int, int]]) -> float:
    if not pts4 or len(pts4) != 4:
        return 0.0
    s = 0.0
    for i in range(4):
        x1, y1 = pts4[i]
        x2, y2 = pts4[(i + 1) % 4]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0

def timing_corners_near_edges(corners: Dict[str, Tuple[int,int]], W: int, H: int, margin_ratio: float = 0.12) -> bool:
    if not corners:
        return False
    mx = W * margin_ratio
    my = H * margin_ratio
    tl = corners.get("TL")
    tr = corners.get("TR")
    bl = corners.get("BL")
    br = corners.get("BR")
    if not (tl and tr and bl and br):
        return False
    ok_tl = (tl[0] <= mx and tl[1] <= my)
    ok_tr = (tr[0] >= W - mx and tr[1] <= my)
    ok_bl = (bl[0] <= mx and bl[1] >= H - my)
    ok_br = (br[0] >= W - mx and br[1] >= H - my)
    return ok_tl and ok_tr and ok_bl and ok_br


# ----------------- Core Vision Algorithms -----------------
def detect_sheet_corners_by_paper(img_bgr: np.ndarray) -> Optional[Dict[str, Tuple[int,int]]]:
    """
    타이밍마크가 없을 때: 종이 외곽(사각형)으로 TL/TR/BR/BL 추정
    - 스캐너 환경 가정: 배경이 비교적 균일
    """
    if img_bgr is None:
        return None

    H, W = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)

    # 종이가 흰색이면 THRESH_BINARY로 종이(흰) 덩어리를 살리고 싶다.
    # 배경/테두리 상황 따라 invert가 필요한 경우가 있어 자동으로 선택:
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # 종이 영역이 흰색으로 크게 남는지 확인 후, 아니면 반전
    white_ratio = cv2.countNonZero(bw) / float(H*W)
    if white_ratio < 0.5:
        bw = 255 - bw

    k = cv2.getStructuringElement(cv2.MORPH_RECT, (9,9))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, k, iterations=2)

    cnts_info = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts_info[0] if len(cnts_info) == 2 else cnts_info[1]
    if not cnts:
        return None

    c = max(cnts, key=cv2.contourArea)

    # 1) 4각형 근사 시도
    peri = cv2.arcLength(c, True)
    approx = cv2.approxPolyDP(c, 0.02 * peri, True)

    if len(approx) == 4:
        quad = approx.reshape(4,2)
    else:
        # 2) fallback: minAreaRect
        rect = cv2.minAreaRect(c)
        quad = cv2.boxPoints(rect)

    quad = order_quad_tl_tr_br_bl(quad)
    corners = {
        "TL": (int(quad[0,0]), int(quad[0,1])),
        "TR": (int(quad[1,0]), int(quad[1,1])),
        "BR": (int(quad[2,0]), int(quad[2,1])),
        "BL": (int(quad[3,0]), int(quad[3,1])),
    }
    return corners

def detect_side_markers(warped_bgr: np.ndarray,
                        left_ratio=0.14,
                        min_area=220,
                        max_area=8000,
                        circularity_th=0.6,
                        aspect_min=0.8,
                        aspect_max=1.35) -> List[dict]:
    """
    워프된 이미지의 왼쪽 띠에서 '검은 네모(또는 둥근 네모)' 마크를 검출.
    return: [{'cx','cy','x','y','w','h','area','circularity'}...]
    """
    if warped_bgr is None:
        return []
    H, W = warped_bgr.shape[:2]
    band = (0, 0, int(W * left_ratio), H)
    x,y,w,h = band
    roi = warped_bgr[y:y+h, x:x+w]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, k, iterations=1)

    cnts_info = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts_info[0] if len(cnts_info) == 2 else cnts_info[1]

    out = []
    for c in cnts:
        area = cv2.contourArea(c)
        if not (min_area <= area <= max_area):
            continue
        bx, by, bw2, bh2 = cv2.boundingRect(c)
        if bh2 <= 0:
            continue
        asp = bw2 / float(bh2)
        if not (aspect_min <= asp <= aspect_max):
            continue

        peri = cv2.arcLength(c, True)
        if peri <= 0:
            continue
        circularity = 4.0 * np.pi * area / (peri * peri)
        if circularity < circularity_th:
            continue

        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"]) + x
        cy = int(M["m01"] / M["m00"]) + y

        out.append({
            "cx": cx, "cy": cy,
            "x": int(bx + x), "y": int(by + y),
            "w": int(bw2), "h": int(bh2),
            "area": float(area),
            "circularity": float(circularity),
        })

    out.sort(key=lambda m: m["cy"])
    return out

def detect_bubbles_by_circularity(warped_bgr: np.ndarray,
                                 search_rect: Optional[Tuple[int,int,int,int]] = None,
                                 min_area=70, max_area=9000,
                                 circularity_th=0.74,
                                 aspect_min=0.7,
                                 aspect_max=1.35,
                                 filled_ratio_max=0.55) -> List[dict]:
    """
    원형도 기반 버블(동그라미) 후보 검출.
    - search_rect가 있으면 그 영역만 탐색 (성능/오탐 감소)
    """
    if warped_bgr is None:
        return []
    H, W = warped_bgr.shape[:2]

    if search_rect is None:
        # 기본: 좌측띠 제외 + 위아래 여백 제외
        search_rect = (int(W*0.12), int(H*0.08), int(W*0.85), int(H*0.84))

    x,y,w,h = search_rect
    x = max(0,x); y = max(0,y)
    w = min(w, W-x); h = min(h, H-y)
    if w <= 0 or h <= 0:
        return []

    roi = warped_bgr[y:y+h, x:x+w]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # 얇은 원 테두리 대응: adaptive + inv
    bw = cv2.adaptiveThreshold(gray, 255,
                               cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV,
                               31, 5)

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, k, iterations=1)

    cnts_info = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts_info[0] if len(cnts_info) == 2 else cnts_info[1]

    bubbles = []
    for c in cnts:
        area = cv2.contourArea(c)
        if not (min_area <= area <= max_area):
            continue
        peri = cv2.arcLength(c, True)
        if peri <= 0:
            continue
        circularity = 4*np.pi*area/(peri*peri)
        if circularity < circularity_th:
            continue

        bx, by, bw2, bh2 = cv2.boundingRect(c)
        if bh2 <= 0:
            continue
        asp = bw2/float(bh2)
        if not (aspect_min <= asp <= aspect_max):
            continue

        # filled bubble 제거: 내부가 너무 까맣게(이진화 기준 흰색) 채워진 경우 제외
        mask = np.zeros(bw.shape, dtype=np.uint8)
        cv2.drawContours(mask, [c], -1, 255, -1)
        total = cv2.countNonZero(mask)
        if total <= 0:
            continue
        filled_ratio = cv2.countNonZero(cv2.bitwise_and(bw, bw, mask=mask)) / float(total)
        if filled_ratio > filled_ratio_max:
            continue

        M = cv2.moments(c)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"]/M["m00"]) + x
        cy = int(M["m01"]/M["m00"]) + y

        bubbles.append({
            "cx": cx, "cy": cy,
            "bbox": (int(bx + x), int(by + y), int(bw2), int(bh2)),
            "area": float(area),
            "circularity": float(circularity),
        })

    bubbles.sort(key=lambda b: (b["cy"], b["cx"]))
    return bubbles

def cluster_rows_by_y(points: List[dict], y_tol: int) -> List[List[dict]]:
    """
    points: [{'cx','cy',...}]
    y_tol: 같은 줄로 볼 y 허용오차
    """
    if not points:
        return []
    pts = sorted(points, key=lambda p: p["cy"])
    rows: List[List[dict]] = []
    for p in pts:
        if not rows:
            rows.append([p]); continue
        med = float(np.median([q["cy"] for q in rows[-1]]))
        if abs(p["cy"] - med) <= y_tol:
            rows[-1].append(p)
        else:
            rows.append([p])
    for r in rows:
        r.sort(key=lambda p: p["cx"])
    return rows

def infer_box_size_from_bubbles(bubbles: List[dict], default=40) -> int:
    if not bubbles:
        return default
    ws = []
    hs = []
    for b in bubbles:
        bx, by, bw2, bh2 = b["bbox"]
        ws.append(bw2); hs.append(bh2)
    s = int(np.median(ws + hs))
    return max(12, min(s, 120))

def build_rois_from_rows(rows: List[List[dict]], box_w: int, box_h: int) -> List[List[Tuple[int,int,int,int]]]:
    rois_2d = []
    for r in rows:
        row_rois = []
        for p in r:
            x = int(p["cx"] - box_w/2)
            y = int(p["cy"] - box_h/2)
            row_rois.append((x,y,box_w,box_h))
        rois_2d.append(row_rois)
    return rois_2d

def filter_points_by_axis_repetition(points: List[dict],
                                     x_tol: int,
                                     y_tol: int,
                                     min_x_repeat: int = 2,
                                     min_y_repeat: int = 2) -> List[dict]:
    """
    x 또는 y 좌표가 일정 범위 내에서 반복되는 점만 남김.
    - min_x_repeat: 같은 x 근처에 몇 개 이상 있어야 통과하는지 (자기 포함)
    - min_y_repeat: 같은 y 근처에 몇 개 이상 있어야 통과하는지 (자기 포함)
    """
    if not points:
        return []
    out = []
    for p in points:
        cx = p["cx"]
        cy = p["cy"]
        x_count = 0
        y_count = 0
        for q in points:
            if abs(q["cx"] - cx) <= x_tol:
                x_count += 1
            if abs(q["cy"] - cy) <= y_tol:
                y_count += 1
            if x_count >= min_x_repeat and y_count >= min_y_repeat:
                break
        if x_count >= min_x_repeat and y_count >= min_y_repeat:
            out.append(p)
    out.sort(key=lambda b: (b["cy"], b["cx"]))
    return out

def estimate_roi_spacing(rows: List[List[Tuple[int,int,int,int]]]) -> Tuple[Optional[int], Optional[int]]:
    if not rows:
        return None, None
    row_centers = []
    dxs = []
    for row in rows:
        if not row:
            continue
        centers = [(x + w / 2.0, y + h / 2.0) for (x, y, w, h) in row]
        centers.sort(key=lambda p: p[0])
        row_centers.append(np.median([c[1] for c in centers]))
        for i in range(1, len(centers)):
            dxs.append(centers[i][0] - centers[i - 1][0])
    row_centers.sort()
    dys = []
    for i in range(1, len(row_centers)):
        dys.append(row_centers[i] - row_centers[i - 1])
    dx = int(np.median(dxs)) if dxs else None
    dy = int(np.median(dys)) if dys else None
    return dx, dy


# ----------------- Main Dialog -----------------
class CoordCalibratorDialog(QDialog):
    """
    ✅ 요구사항 충족
    - 1) 타이밍마크 4점이 있으면 그걸로 워프
    - 2) 없으면 종이 외곽으로 TL/TR/BR/BL 자동 추정 -> 워프
    - 3) 워프된 이미지에서 원형도 기반 버블 검출 -> ROI 자동 생성 -> 빨간 네모 표시 + 좌표 로그
    - 4) 워프된 이미지에서 사이드 타이밍마크(검은 네모) 검출 -> 표시 + 좌표 로그
    - 5) 결과를 JSON으로 저장
    """

    def __init__(self, parent=None, db_path: Optional[str] = None):
        super().__init__(parent)
        self.setWindowTitle("OMR 좌표 캘리브레이터 (외곽+원형도+사이드마크)")
        self.resize(1500, 900)

        self.db_path = db_path

        self.form_path: Optional[str] = None
        self.form_data: Optional[dict] = None

        self.img_path: Optional[str] = None
        self.img_src: Optional[np.ndarray] = None
        self.img_warped: Optional[np.ndarray] = None
        self.img_vis: Optional[np.ndarray] = None

        # 결과 캐시
        self.last_corners: Optional[Dict[str, Tuple[int,int]]] = None
        self.last_side_markers: List[dict] = []
        self.last_bubbles: List[dict] = []
        self.last_rois: List[List[Tuple[int,int,int,int]]] = []

        # manual 4pt (옵션)
        self.manual_points: List[Tuple[int,int]] = []
        self.manual_names = ["TL", "TR", "BR", "BL"]

        self._build_ui()
        self._load_forms()

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QHBoxLayout(self)

        # LEFT
        left = QVBoxLayout()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.viewport().installEventFilter(self)
        left.addWidget(self.view, 1)

        self.pix_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pix_item)

        bar = QHBoxLayout()
        self.chk_show_roi = QCheckBox("ROI(빨간네모) 표시")
        self.chk_show_roi.setChecked(True)
        self.chk_show_roi.stateChanged.connect(self._refresh_view)
        bar.addWidget(self.chk_show_roi)

        self.chk_show_side = QCheckBox("사이드마크(초록) 표시")
        self.chk_show_side.setChecked(True)
        self.chk_show_side.stateChanged.connect(self._refresh_view)
        bar.addWidget(self.chk_show_side)

        self.chk_show_corners = QCheckBox("TL/TR/BR/BL(노랑) 표시")
        self.chk_show_corners.setChecked(True)
        self.chk_show_corners.stateChanged.connect(self._refresh_view)
        bar.addWidget(self.chk_show_corners)

        self.chk_manual = QCheckBox("수동 4점 클릭 모드")
        bar.addWidget(self.chk_manual)

        btn_reset = QPushButton("클릭 초기화")
        btn_reset.clicked.connect(self._reset_manual)
        bar.addWidget(btn_reset)

        bar.addStretch(1)
        left.addLayout(bar)

        self.lbl_info = QLabel("준비됨")
        self.lbl_info.setStyleSheet("font-weight:bold; color:blue;")
        left.addWidget(self.lbl_info)

        root.addLayout(left, 7)

        # RIGHT
        right = QVBoxLayout()
        grp = QGroupBox("실행")
        form = QFormLayout(grp)

        self.cb_form = QComboBox()
        self.cb_form.currentIndexChanged.connect(self._on_form_changed)
        form.addRow("폼:", self.cb_form)

        btn_img = QPushButton("이미지 열기")
        btn_img.clicked.connect(self._pick_image)
        form.addRow("", btn_img)

        btn_auto = QPushButton("자동: (타이밍마크 or 외곽) 워프 + 버블/사이드 검출")
        btn_auto.setFixedHeight(45)
        btn_auto.setStyleSheet("background-color:#E3F2FD; font-weight:bold; font-size:14px;")
        btn_auto.clicked.connect(self._run_auto)
        form.addRow("", btn_auto)

        btn_manual = QPushButton("수동 4점 워프 + 버블/사이드 검출")
        btn_manual.clicked.connect(self._run_manual)
        form.addRow("", btn_manual)

        btn_save = QPushButton("JSON 저장")
        btn_save.setStyleSheet("font-weight:bold;")
        btn_save.clicked.connect(self._save_json)
        form.addRow("", btn_save)

        right.addWidget(grp)

        self.txt_log = QTextEdit()
        self.txt_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.txt_log.setMinimumHeight(260)
        self.txt_log.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        right.addWidget(QLabel("로그:"))
        right.addWidget(self.txt_log, 1)

        root.addLayout(right, 3)

    # ---------------- events ----------------
    def wheelEvent(self, event):
        if self.view.underMouse():
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else (1 / 1.15)
            self.view.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def eventFilter(self, obj, event):
        if self.chk_manual.isChecked() and event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if self.img_src is None:
                return True
            pos = self.view.mapToScene(event.pos())
            x, y = int(pos.x()), int(pos.y())
            if len(self.manual_points) < 4:
                self.manual_points.append((x, y))
                name = self.manual_names[len(self.manual_points)-1]
                self._log(f"[수동] {name} 클릭: ({x}, {y})")
                self._refresh_view()
            return True
        return super().eventFilter(obj, event)

    # ---------------- helpers ----------------
    def _log(self, msg: str):
        self.txt_log.append(msg)
        self.txt_log.moveCursor(self.txt_log.textCursor().End)
        self.txt_log.ensureCursorVisible()

    def _reset_manual(self):
        self.manual_points.clear()
        self._refresh_view()

    def _load_forms(self):
        self.cb_form.clear()
        for _, display, path in list_forms():
            self.cb_form.addItem(display, userData=path)
        self._on_form_changed()

    def _on_form_changed(self):
        path = self.cb_form.currentData()
        self.form_path = path
        if path and os.path.exists(path):
            self.form_data = load_form(path)
            self._log(f"[폼] 로드: {os.path.basename(path)}")
        else:
            self.form_data = None

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "이미지 선택", "", "Images (*.jpg *.png *.bmp)")
        if not path:
            return
        img = cv_imread_unicode(path)
        if img is None:
            QMessageBox.warning(self, "오류", "이미지 로드 실패")
            return

        self.img_path = path
        self.img_src = img
        self.img_warped = None
        self.img_vis = img.copy()

        self.last_corners = None
        self.last_side_markers = []
        self.last_bubbles = []
        self.last_rois = []
        self.manual_points.clear()

        self._log(f"[이미지] {os.path.basename(path)}")
        self._refresh_view()

    def _refresh_view(self):
        if self.img_src is None:
            return
        base = self.img_warped if self.img_warped is not None else self.img_src
        vis = base.copy()

        # ROI
        if self.chk_show_roi.isChecked() and self.last_rois:
            vis = overlay_rois(vis, self.last_rois, color=(0,0,255), thickness=2)
            vis = overlay_roi_labels(vis, self.last_rois, color=(0,0,255))

        # side markers (green box)
        if self.chk_show_side.isChecked() and self.last_side_markers:
            for i, m in enumerate(self.last_side_markers, start=1):
                x,y,w,h = int(m["x"]), int(m["y"]), int(m["w"]), int(m["h"])
                cv2.rectangle(vis, (x,y), (x+w, y+h), (0,255,0), 2)
                label = f"SM{i:02d}"
                cv2.putText(vis, label, (x, max(0,y-5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        # corners (yellow)
        if self.chk_show_corners.isChecked() and self.last_corners and self.img_warped is not None:
            pts = {k: self.last_corners[k] for k in ["TL","TR","BR","BL"] if k in self.last_corners}
            vis = draw_points(vis, pts, color=(0,255,255))

        # manual points (only before warp)
        if self.chk_manual.isChecked() and self.img_warped is None and self.manual_points:
            for i, (x,y) in enumerate(self.manual_points):
                cv2.circle(vis, (x,y), 10, (0,0,255), -1)
                cv2.putText(vis, self.manual_names[i], (x+12, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

        self.img_vis = vis
        self.pix_item.setPixmap(cv_to_qpixmap(vis))
        self.scene.setSceneRect(self.pix_item.boundingRect())
        self.scene.update()

    # ---------------- core ----------------
    def _require_img(self) -> bool:
        if self.img_src is None:
            QMessageBox.warning(self, "경고", "이미지를 먼저 여세요.")
            return False
        return True

    def _get_out_size(self) -> Tuple[int,int]:
        """
        폼에 sheet_size가 있으면 사용, 없으면 A4 고정(엔진 값과 동일하게 맞춤)
        """
        if isinstance(self.form_data, dict):
            ss = self.form_data.get("sheet_size")
            if isinstance(ss, dict) and "w" in ss and "h" in ss:
                return int(ss["w"]), int(ss["h"])
        # default (OMREngine과 동일)
        return 1654, 2339

    def _run_auto(self):
        if not self._require_img():
            return
        try:
            self._log("=== AUTO 시작 ===")
            out_w, out_h = self._get_out_size()

            corners = None
            mode = ""

            # 1) 타이밍마크 기반 시도
            tm, _dbg = detect_timing_marks(self.img_src)
            if tm and all(k in tm for k in ("TL","TR","BR","BL")):
                H, W = self.img_src.shape[:2]
                if timing_corners_near_edges(tm, W, H, margin_ratio=0.12):
                    corners = tm
                    mode = "TIMING_MARK"
                    self._log("[AUTO] 타이밍마크 4점 성공")
                    self._log(f"[TM] TL={tm['TL']} TR={tm['TR']} BR={tm['BR']} BL={tm['BL']}")
                else:
                    self._log("[AUTO] 타이밍마크가 가장자리와 멀어 무시함")
            else:
                # 2) 외곽 기반
                corners = detect_sheet_corners_by_paper(self.img_src)
                mode = "PAPER_EDGE" if corners else "FAIL"
                self._log("[AUTO] 타이밍마크 실패 -> 외곽 기반 시도")

            # 외곽 검출이 너무 작으면 이미지 전체로 대체
            if corners:
                H, W = self.img_src.shape[:2]
                area = quad_area([corners["TL"], corners["TR"], corners["BR"], corners["BL"]])
                if area < (0.6 * W * H):
                    self._log("[AUTO] 외곽 검출이 너무 작음 -> 이미지 전체로 대체")
                    corners = {"TL": (0, 0), "TR": (W-1, 0), "BR": (W-1, H-1), "BL": (0, H-1)}
                    mode = "IMAGE_EDGE"

            if not corners:
                # 마지막 fallback: 이미지 전체를 사용
                H, W = self.img_src.shape[:2]
                corners = {"TL": (0, 0), "TR": (W-1, 0), "BR": (W-1, H-1), "BL": (0, H-1)}
                mode = "IMAGE_EDGE"
                self._log("[AUTO] 외곽/타이밍마크 실패 -> 이미지 전체로 대체")

            # warp
            src = [corners["TL"], corners["TR"], corners["BR"], corners["BL"]]
            dst = [(0,0), (out_w-1,0), (out_w-1,out_h-1), (0,out_h-1)]
            warped, _M = warp_to_form(self.img_src, src, dst, (out_w, out_h))
            self.img_warped = warped
            self.last_corners = {k: tuple(map(int, corners[k])) for k in corners}

            self._log(f"[WARP] mode={mode} out=({out_w},{out_h})")
            self._log(f"[WARP] corners={self.last_corners}")

            # 3) side markers
            self.last_side_markers = detect_side_markers(self.img_warped)
            self._log(f"[SIDE] found={len(self.last_side_markers)}")
            if self.last_side_markers:
                for i,m in enumerate(self.last_side_markers[:10], start=1):
                    self._log(f"  SM{i:02d}: cx={m['cx']} cy={m['cy']} bbox=({m['x']},{m['y']},{m['w']},{m['h']})")

            # 4) bubbles -> rois
            self.last_bubbles = detect_bubbles_by_circularity(self.img_warped)
            self._log(f"[BUBBLE] candidates={len(self.last_bubbles)}")

            box = infer_box_size_from_bubbles(self.last_bubbles, default=40)
            y_tol = max(12, int(box * 0.8))
            x_tol = max(12, int(box * 0.8))
            filtered = filter_points_by_axis_repetition(
                self.last_bubbles,
                x_tol=x_tol,
                y_tol=y_tol,
                min_x_repeat=2,
                min_y_repeat=2,
            )
            self._log(f"[BUBBLE] filtered={len(filtered)} (x_tol={x_tol}, y_tol={y_tol})")
            rows = cluster_rows_by_y(filtered, y_tol=y_tol)

            # row 정리: 너무 짧은 줄(노이즈) 제거 (2개 미만은 제거)
            rows = [r for r in rows if len(r) >= 2]
            self.last_rois = build_rois_from_rows(rows, box_w=box, box_h=box)

            self._log(f"[ROI] box={box} y_tol={y_tol} rows={len(rows)}")
            self._log_rois()

            # form_data에도 임시 반영(저장용)
            if isinstance(self.form_data, dict):
                self.form_data["layout_mode"] = "fixed"
                self.form_data["sheet_size"] = {"w": out_w, "h": out_h}
                self.form_data["auto_calib"] = {
                    "mode": mode,
                    "corners": self.last_corners,
                    "bubble_box": box,
                    "row_tol": y_tol,
                }
                self.form_data["side_markers"] = [
                    {"cx": m["cx"], "cy": m["cy"], "x": m["x"], "y": m["y"], "w": m["w"], "h": m["h"]}
                    for m in self.last_side_markers
                ]
                # ✅ 직접 ROI 저장 (스키마 모르면 이게 제일 확실)
                self.form_data["rois"] = self.last_rois
                self.form_data["questions"] = len(self.last_rois)

            self.lbl_info.setText(f"AUTO 완료 ({mode})")
            self._refresh_view()
            QMessageBox.information(self, "완료", "자동 캘리브레이션 완료")

        except Exception:
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "오류", "자동 처리 중 오류")

    def _run_manual(self):
        if not self._require_img():
            return
        if len(self.manual_points) != 4:
            QMessageBox.warning(self, "경고", "수동 모드: TL,TR,BR,BL 순서로 4점을 찍어주세요.")
            return
        try:
            self._log("=== MANUAL 시작 ===")
            out_w, out_h = self._get_out_size()

            src = [(int(x), int(y)) for x,y in self.manual_points]
            dst = [(0,0), (out_w-1,0), (out_w-1,out_h-1), (0,out_h-1)]
            warped, _M = warp_to_form(self.img_src, src, dst, (out_w, out_h))
            self.img_warped = warped
            self.last_corners = {"TL": src[0], "TR": src[1], "BR": src[2], "BL": src[3]}

            # side markers
            self.last_side_markers = detect_side_markers(self.img_warped)
            self._log(f"[SIDE] found={len(self.last_side_markers)}")

            # bubbles -> rois
            self.last_bubbles = detect_bubbles_by_circularity(self.img_warped)
            box = infer_box_size_from_bubbles(self.last_bubbles, default=40)
            y_tol = max(12, int(box * 0.8))
            x_tol = max(12, int(box * 0.8))
            filtered = filter_points_by_axis_repetition(
                self.last_bubbles,
                x_tol=x_tol,
                y_tol=y_tol,
                min_x_repeat=2,
                min_y_repeat=2,
            )
            self._log(f"[BUBBLE] filtered={len(filtered)} (x_tol={x_tol}, y_tol={y_tol})")
            rows = cluster_rows_by_y(filtered, y_tol=y_tol)
            rows = [r for r in rows if len(r) >= 2]
            self.last_rois = build_rois_from_rows(rows, box_w=box, box_h=box)

            self._log(f"[ROI] box={box} rows={len(rows)}")
            self._log_rois()

            if isinstance(self.form_data, dict):
                self.form_data["layout_mode"] = "fixed"
                self.form_data["sheet_size"] = {"w": out_w, "h": out_h}
                self.form_data["auto_calib"] = {"mode": "MANUAL", "corners": self.last_corners, "bubble_box": box, "row_tol": y_tol}
                self.form_data["side_markers"] = [{"cx": m["cx"], "cy": m["cy"], "x": m["x"], "y": m["y"], "w": m["w"], "h": m["h"]} for m in self.last_side_markers]
                self.form_data["rois"] = self.last_rois
                self.form_data["questions"] = len(self.last_rois)

            self.lbl_info.setText("MANUAL 완료")
            self._refresh_view()
            QMessageBox.information(self, "완료", "수동 캘리브레이션 완료")

        except Exception:
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "오류", "수동 처리 중 오류")

    def _log_rois(self):
        if not self.last_rois:
            self._log("[ROI] 없음")
            return
        self._log(f"[ROI] 총 문항(줄)={len(self.last_rois)}")
        for qi, row in enumerate(self.last_rois, start=1):
            for oi, (x,y,w,h) in enumerate(row):
                self._log(f"  ROI Q{qi:02d}-O{oi}: x={x} y={y} w={w} h={h}")
        dx, dy = estimate_roi_spacing(self.last_rois)
        if dx is not None or dy is not None:
            dx_str = f"{dx}" if dx is not None else "N/A"
            dy_str = f"{dy}" if dy is not None else "N/A"
            self._log(f"[SPACING] dx={dx_str} dy={dy_str}")

    def _save_json(self):
        if not isinstance(self.form_data, dict):
            QMessageBox.warning(self, "경고", "폼을 먼저 선택하세요.")
            return
        if self.img_warped is None or not self.last_rois:
            QMessageBox.warning(self, "경고", "먼저 자동/수동 실행 후 ROI가 생성되어야 저장할 수 있습니다.")
            return

        try:
            default_name = "calibrated_form.json"
            if self.form_path:
                default_name = os.path.basename(self.form_path)

            path, _ = QFileDialog.getSaveFileName(self, "폼 JSON 저장", default_name, "JSON (*.json)")
            if not path:
                return

            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.form_data, f, indent=2, ensure_ascii=False)

            self._log(f"[SAVE] {path}")
            QMessageBox.information(self, "저장", "JSON 저장 완료")

        except Exception:
            self._log(traceback.format_exc())
            QMessageBox.critical(self, "오류", "저장 중 오류")

