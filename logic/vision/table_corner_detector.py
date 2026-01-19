# logic/vision/table_corner_detector.py
from __future__ import annotations
from typing import Dict, Tuple, Optional

import cv2
import numpy as np

Point = Tuple[int, int]


def _order_pts(pts4):
    # pts4: (4,2) float/int
    pts = np.array(pts4, dtype=np.float32)
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)

    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return {"TL": (int(tl[0]), int(tl[1])),
            "TR": (int(tr[0]), int(tr[1])),
            "BL": (int(bl[0]), int(bl[1])),
            "BR": (int(br[0]), int(br[1]))}


def detect_table_corners(img_bgr: np.ndarray) -> Tuple[Dict[str, Point], Dict]:
    """
    투표지/서면결의서처럼 '큰 표(그리드)'가 있는 문서에서
    가장 큰 사각형을 찾아 TL/TR/BL/BR 반환.
    """
    H, W = img_bgr.shape[:2]
    debug = {}

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # 조명 보정
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 선/테두리 강조: 에지
    edges = cv2.Canny(gray, 60, 180)

    # 에지 연결(표 테두리 끊김 보완)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges2 = cv2.dilate(edges, k, iterations=2)
    edges2 = cv2.erode(edges2, k, iterations=1)

    debug["edges"] = edges2

    cnts, _ = cv2.findContours(edges2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best = None
    best_area = 0.0

    for c in cnts:
        area = cv2.contourArea(c)
        if area < (W * H * 0.08):  # 너무 작은건 배제 (문서 크기에 맞게 조정)
            continue

        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)

        # 사각형에 가까운 것만
        if len(approx) != 4:
            continue

        # 너무 길쭉/찌그러진 것 배제
        x, y, w, h = cv2.boundingRect(approx)
        if w < W * 0.3 or h < H * 0.2:
            continue

        if area > best_area:
            best_area = area
            best = approx

    if best is None:
        return {}, {"ok": False, **debug}

    pts4 = best.reshape(4, 2)
    corners = _order_pts(pts4)

    # 간단 검증: 좌상/우상/좌하/우하 관계
    TL, TR, BL, BR = corners["TL"], corners["TR"], corners["BL"], corners["BR"]
    ok = (TL[0] < TR[0] and BL[0] < BR[0] and TL[1] < BL[1] and TR[1] < BR[1])
    debug["ok"] = ok
    debug["corners"] = corners
    debug["area"] = best_area

    return corners if ok else {}, debug


def draw_table_debug(img_bgr: np.ndarray, corners: Dict[str, Point]) -> np.ndarray:
    out = img_bgr.copy()
    for k, p in corners.items():
        cv2.circle(out, p, 12, (0, 0, 255), -1)
        cv2.putText(out, k, (p[0] + 10, p[1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
    return out
