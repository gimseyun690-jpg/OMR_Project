# logic/vision/table_corner_detector.py
from __future__ import annotations
from typing import Dict, Tuple, Optional, List

import cv2
import numpy as np

Point = Tuple[int, int]

def _order_pts(pts4: np.ndarray) -> Dict[str, Point]:
    """
    좌표 4개를 TL, TR, BL, BR 순서로 정렬 (x+y 합/차 이용)
    """
    pts = pts4.reshape(4, 2).astype(np.float32)
    
    # TL: x+y 최소 / BR: x+y 최대
    s = pts.sum(axis=1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]

    # TR: x-y 최대 (또는 y-x 최소) / BL: y-x 최대
    diff = np.diff(pts, axis=1).reshape(-1) # y - x
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]

    return {
        "TL": (int(tl[0]), int(tl[1])),
        "TR": (int(tr[0]), int(tr[1])),
        "BL": (int(bl[0]), int(bl[1])),
        "BR": (int(br[0]), int(br[1]))
    }

def refine_corners(gray_img: np.ndarray, corners: Dict[str, Point]) -> Dict[str, Point]:
    """
    [상용급 기능] 발견된 코너 좌표를 서브픽셀 단위로 미세 조정하여 정확도 극대화
    """
    pts_vec = np.array([list(corners["TL"]), list(corners["TR"]), 
                        list(corners["BR"]), list(corners["BL"])], dtype=np.float32)
    
    # 탐색 윈도우 크기 (11x11), 데드존(-1,-1)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    
    # 미세 조정 수행
    refined_pts = cv2.cornerSubPix(gray_img, pts_vec, (5, 5), (-1, -1), criteria)

    return {
        "TL": (int(refined_pts[0][0]), int(refined_pts[0][1])),
        "TR": (int(refined_pts[1][0]), int(refined_pts[1][1])),
        "BR": (int(refined_pts[2][0]), int(refined_pts[2][1])),
        "BL": (int(refined_pts[3][0]), int(refined_pts[3][1]))
    }

def detect_table_corners(img_bgr: np.ndarray) -> Tuple[Dict[str, Point], Dict]:
    """
    문서 내의 가장 큰 '닫힌 사각형(표 테두리)'을 찾아 코너를 반환합니다.
    """
    if img_bgr is None:
        return {}, {"ok": False, "msg": "No Image"}

    H, W = img_bgr.shape[:2]
    debug = {"ok": False}
    
    # 1. 전처리: 그레이스케일
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # 2. 전처리: 가우시안 블러 (노이즈 제거)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 3. 적응형 이진화 (Adaptive Threshold) - Canny보다 끊긴 선 연결에 유리
    #    배경이 복잡하거나 그림자가 있어도 선을 잘 따냄
    thresh = cv2.adaptiveThreshold(blurred, 255, 
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY_INV, 11, 2)
    debug["thresh"] = thresh

    # 4. 모폴로지 연산: 끊긴 선 강제로 잇기 (핵심)
    #    가로/세로 커널을 사용하여 직사각형 구조 복원력 강화
    kernel_rect = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_rect, iterations=2)
    
    # 5. 윤곽선 검출
    cnts, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    best_cnt = None
    max_area = 0

    # 최소 면적: 전체 이미지의 5% 이상이어야 함 (너무 작은 박스 무시)
    min_area_threshold = W * H * 0.05 

    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area_threshold:
            continue
            
        # 6. 다각형 근사 (사각형 찾기)
        peri = cv2.arcLength(c, True)
        # 0.02는 오차가 클 수 있으므로 반복적으로 epsilon을 조절하며 사각형 시도
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        
        # 꼭짓점이 4개가 아니면 좀 더 유연하게 다시 시도
        if len(approx) != 4:
            approx = cv2.approxPolyDP(c, 0.05 * peri, True) # 더 단순화

        if len(approx) == 4:
            # 볼록한 사각형인지 확인 (모래시계 모양 제외)
            if cv2.isContourConvex(approx):
                if area > max_area:
                    max_area = area
                    best_cnt = approx

    if best_cnt is None:
        debug["msg"] = "사각형을 찾지 못함"
        return {}, debug

    # 7. 코너 정렬
    pts4 = best_cnt.reshape(4, 2)
    corners = _order_pts(pts4)
    
    # 8. [상용급] 서브픽셀 정제 (좌표 미세 보정)
    try:
        corners = refine_corners(gray, corners)
    except Exception as e:
        print(f"[Warn] Subpix refinement failed: {e}")

    # 9. 검증: 사각형이 너무 찌그러지지 않았는지 확인
    w_top = np.linalg.norm(np.array(corners["TR"]) - np.array(corners["TL"]))
    w_bot = np.linalg.norm(np.array(corners["BR"]) - np.array(corners["BL"]))
    h_left = np.linalg.norm(np.array(corners["BL"]) - np.array(corners["TL"]))
    h_right = np.linalg.norm(np.array(corners["BR"]) - np.array(corners["TR"]))
    
    min_side = min(w_top, w_bot, h_left, h_right)
    if min_side < 50: # 너무 얇은 사각형은 제외
         debug["msg"] = "유효하지 않은 사각형 비율"
         return {}, debug

    debug["ok"] = True
    debug["cnt"] = best_cnt
    debug["corners"] = corners
    
    return corners, debug

def draw_table_debug(img_bgr: np.ndarray, corners: Dict[str, Point]) -> np.ndarray:
    """디버깅용: 찾은 코너와 박스를 그립니다."""
    out = img_bgr.copy()
    if not corners:
        return out
        
    pts = [corners["TL"], corners["TR"], corners["BR"], corners["BL"]]
    pts_np = np.array(pts, np.int32).reshape((-1, 1, 2))
    
    # 테두리
    cv2.polylines(out, [pts_np], True, (0, 255, 0), 3)
    
    # 코너점
    for k, p in corners.items():
        cv2.circle(out, p, 10, (0, 0, 255), -1) # 빨간점
        cv2.putText(out, k, (p[0] + 15, p[1] - 15), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    return out