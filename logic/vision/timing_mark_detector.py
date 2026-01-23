# logic/vision/timing_mark_detector.py
from __future__ import annotations
from typing import Dict, Tuple, List, Optional
import cv2
import numpy as np

Point = Tuple[int, int]
def detect_timing_marks(img_bgr: np.ndarray) -> Tuple[Dict[str, Point], Dict]:
    """
    [상용급] 이미지 전체에서 '타이밍 마크(검은 네모)' 4개를 찾아
    TL(좌상), TR(우상), BL(좌하), BR(우하) 좌표를 반환합니다.
    """
    debug = {"ok": False}
    if img_bgr is None:
        return {}, debug

    H, W = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 1. 전처리 & 이진화 (그림자에 강한 Adaptive Threshold)
    #    블록 크기(31)와 상수(15)는 환경에 따라 미세조정 가능
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                               cv2.THRESH_BINARY_INV, 31, 15)

    # 2. 노이즈 제거 (작은 점들 삭제)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # 3. 윤곽선 검출
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    
    # 전체 이미지 면적 대비 너무 작거나 큰 건 제외
    min_area = W * H * 0.0005  # 0.05%
    max_area = W * H * 0.05    # 5%

    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue

        x, y, w, h = cv2.boundingRect(c)
        
        # (1) 종횡비 검사 (정사각형에 가까워야 함, 0.5 ~ 2.0)
        aspect = float(w) / h
        if aspect < 0.5 or aspect > 2.0:
            continue

        # (2) Solidity(밀도) 검사 (글자는 속이 비어서 낮게 나옴 -> 0.8 이상이면 꽉 찬 도형)
        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0: continue
        solidity = area / hull_area
        if solidity < 0.85: 
            continue

        # 후보 등록 (중심점)
        cx = int(x + w / 2)
        cy = int(y + h / 2)
        candidates.append({'cx': cx, 'cy': cy, 'area': area})

    # 후보가 4개 미만이면 실패
    if len(candidates) < 4:
        debug['msg'] = f"후보 부족 ({len(candidates)}개)"
        return {}, debug

    # 4. 4귀퉁이 분류 (Quadrant 방식)
    #    이미지를 4등분해서 각 구역의 가장 구석에 있는 점을 찾음
    cx_img, cy_img = W // 2, H // 2
    
    quads = {'TL': [], 'TR': [], 'BL': [], 'BR': []}
    
    for c in candidates:
        cx, cy = c['cx'], c['cy']
        if cx < cx_img and cy < cy_img:   quads['TL'].append(c)
        elif cx >= cx_img and cy < cy_img: quads['TR'].append(c)
        elif cx < cx_img and cy >= cy_img: quads['BL'].append(c)
        elif cx >= cx_img and cy >= cy_img: quads['BR'].append(c)

    corners = {}
    
    # 각 분면에서 '이미지 중심에서 가장 먼 점' (즉, 모서리에 가까운 점) 선택
    # TL: (0,0) 거리 최소화 = x+y 최소화
    # TR: (W,0) 거리 최소화 = (W-x)+y 최소화
    # ... 유클리드 거리로 계산하는 것이 가장 정확함
    
    def dist_sq(x1, y1, x2, y2): return (x1-x2)**2 + (y1-y2)**2

    if quads['TL']: corners['TL'] = min(quads['TL'], key=lambda p: dist_sq(p['cx'], p['cy'], 0, 0))
    if quads['TR']: corners['TR'] = min(quads['TR'], key=lambda p: dist_sq(p['cx'], p['cy'], W, 0))
    if quads['BL']: corners['BL'] = min(quads['BL'], key=lambda p: dist_sq(p['cx'], p['cy'], 0, H))
    if quads['BR']: corners['BR'] = min(quads['BR'], key=lambda p: dist_sq(p['cx'], p['cy'], W, H))

    # 4개가 다 찾아졌는지 확인
    if len(corners) != 4:
        debug['msg'] = "4귀퉁이 중 일부를 못 찾음"
        return {}, debug

    # 최종 결과 포맷팅
    final_pts = {
        k: (v['cx'], v['cy']) for k, v in corners.items()
    }
    
    # 5. 서브픽셀 정밀 보정 (선택 사항: 더 정확한 좌표를 원하면 활성화)
    # gray_img에서 final_pts 주변을 미세 탐색하여 0.1픽셀 단위로 보정
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    for k, pt in final_pts.items():
        pts_vec = np.array([[pt[0], pt[1]]], dtype=np.float32)
        cv2.cornerSubPix(gray, pts_vec, (5, 5), (-1, -1), criteria)
        final_pts[k] = (int(pts_vec[0][0]), int(pts_vec[0][1]))

    debug['ok'] = True
    debug['corners'] = final_pts
    return final_pts, debug
