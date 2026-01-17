import cv2
import numpy as np


def find_timing_mark(image_cv, rect):
    """
    rect: (x,y,w,h) search window (폼 기준 좌표)
    return: (cx,cy) or None
    """
    x, y, w, h = rect
    H, W = image_cv.shape[:2]
    x0 = max(0, x); y0 = max(0, y)
    x1 = min(W, x + w); y1 = min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return None

    roi = image_cv[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # 검은 마크 찾기: 이진화(역)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 작은 노이즈 제거
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)

    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None

    # 가장 면적 큰 컨투어(마크 후보)
    cnt = max(cnts, key=cv2.contourArea)
    area = cv2.contourArea(cnt)
    if area < 50:  # 너무 작으면 실패 처리
        return None

    M = cv2.moments(cnt)
    if M["m00"] == 0:
        return None

    cx = int(M["m10"] / M["m00"]) + x0
    cy = int(M["m01"] / M["m00"]) + y0
    return (cx, cy)
