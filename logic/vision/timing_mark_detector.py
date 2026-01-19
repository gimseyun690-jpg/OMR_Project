# logic/vision/timing_mark_detector.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Tuple, List, Optional

import cv2
import numpy as np


Point = Tuple[int, int]


@dataclass
class MarkCandidate:
    cx: float
    cy: float
    w: int
    h: int
    area: float
    fill: float


def _clahe_gray(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _binarize_black(gray: np.ndarray) -> np.ndarray:
    """
    검은 요소를 흰색으로 올리는 이진화.
    조명/밝기 편차에 강하도록 OTSU + INV 사용.
    """
    gray2 = _clahe_gray(gray)
    # OTSU
    _, bw = cv2.threshold(gray2, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # 작은 노이즈 제거
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, k, iterations=1)
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, k, iterations=1)
    return bw


def _extract_candidates(
    bw: np.ndarray,
    min_area: int,
    max_area: int,
    aspect_min: float,
    aspect_max: float,
    fill_min: float,
    border_margin_ratio: float,
) -> List[MarkCandidate]:
    """
    이진화(bw)에서 후보 컨투어 추출 + 필터링.
    border_margin_ratio: 가장자리에서 얼마나 안쪽까지 후보를 허용할지(0.06=6%)
    """
    H, W = bw.shape[:2]
    margin_x = int(W * border_margin_ratio)
    margin_y = int(H * border_margin_ratio)

    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    cands: List[MarkCandidate] = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue

        x, y, w, h = cv2.boundingRect(c)
        if w < 6 or h < 6:
            continue

        aspect = w / float(h)
        if aspect < aspect_min or aspect > aspect_max:
            continue

        rect_area = w * h
        fill = float(area) / float(rect_area + 1e-6)
        if fill < fill_min:
            continue

        # ✅ 가장자리 근처만 후보로 인정 (타이밍 마크는 대개 외곽)
        near_border = (
            x < margin_x or y < margin_y or (x + w) > (W - margin_x) or (y + h) > (H - margin_y)
        )
        if not near_border:
            continue

        cx = x + w / 2.0
        cy = y + h / 2.0
        cands.append(MarkCandidate(cx=cx, cy=cy, w=w, h=h, area=area, fill=fill))

    return cands


def _pick_corners_from_candidates(cands: List[MarkCandidate]) -> Dict[str, Point]:
    """
    후보 중심점으로 코너 4점 선택
    """
    if not cands:
        return {}

    pts = [(c.cx, c.cy) for c in cands]

    TL = min(pts, key=lambda p: p[0] + p[1])
    TR = min(pts, key=lambda p: (-p[0]) + p[1])
    BL = min(pts, key=lambda p: p[0] + (-p[1]))
    BR = min(pts, key=lambda p: (-p[0]) + (-p[1]))

    return {
        "TL": (int(TL[0]), int(TL[1])),
        "TR": (int(TR[0]), int(TR[1])),
        "BL": (int(BL[0]), int(BL[1])),
        "BR": (int(BR[0]), int(BR[1])),
    }


def _validate_corners(corners: Dict[str, Point], img_shape) -> bool:
    """
    간단 검증: 사각형 형태/면적이 말이 되는지
    """
    if not all(k in corners for k in ("TL", "TR", "BL", "BR")):
        return False

    TL = corners["TL"]
    TR = corners["TR"]
    BL = corners["BL"]
    BR = corners["BR"]

    # 좌우/상하 관계
    if not (TL[0] < TR[0] and BL[0] < BR[0]):
        return False
    if not (TL[1] < BL[1] and TR[1] < BR[1]):
        return False

    H, W = img_shape[:2]

    # 면적이 너무 작으면 오검출일 확률 높음
    poly = np.array([TL, TR, BR, BL], dtype=np.int32)
    area = cv2.contourArea(poly)
    if area < (W * H * 0.10):  # 이미지의 10% 미만이면 너무 작다
        return False

    return True


def detect_timing_marks(
    img_bgr: np.ndarray,
    *,
    min_area: int = 120,
    max_area: int = 20000,
    aspect_min: float = 0.12,
    aspect_max: float = 8.0,
    fill_min: float = 0.35,
    border_margin_ratio: float = 0.08,
) -> Tuple[Dict[str, Point], Dict]:
    """
    타이밍마크(검은 네모/막대) 자동 탐지
    반환:
      corners: {"TL":(x,y),"TR":...,"BL":...,"BR":...} (없으면 빈 dict)
      debug: {"bw":..., "cands":..., "corners":..., "ok":bool}
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    bw = _binarize_black(gray)

    cands = _extract_candidates(
        bw,
        min_area=min_area,
        max_area=max_area,
        aspect_min=aspect_min,
        aspect_max=aspect_max,
        fill_min=fill_min,
        border_margin_ratio=border_margin_ratio,
    )

    corners = _pick_corners_from_candidates(cands)
    ok = _validate_corners(corners, img_bgr.shape)

    debug = {
        "bw": bw,
        "cands": cands,
        "corners": corners,
        "ok": ok,
    }

    if not ok:
        return {}, debug
    return corners, debug


def draw_detect_debug(img_bgr: np.ndarray, debug: Dict) -> np.ndarray:
    """
    디버그용: 후보 박스 + 코너 점 표시
    """
    out = img_bgr.copy()
    cands: List[MarkCandidate] = debug.get("cands", [])
    corners: Dict[str, Point] = debug.get("corners", {})
    ok = debug.get("ok", False)

    # 후보 박스 표시(최대 80개)
    # 너무 많이 그리면 느려지므로 샘플링
    show = cands
    if len(show) > 80:
        show = show[:: max(1, len(show)//80)]

    for c in show:
        x = int(c.cx - c.w / 2)
        y = int(c.cy - c.h / 2)
        cv2.rectangle(out, (x, y), (x + c.w, y + c.h), (0, 255, 255), 2)

    # 코너 점 표시
    for k, p in corners.items():
        cv2.circle(out, p, 10, (0, 0, 255), -1)
        cv2.putText(out, k, (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.putText(out, f"TIMING DETECT {'OK' if ok else 'FAIL'}", (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0) if ok else (0, 0, 255), 3)
    return out
