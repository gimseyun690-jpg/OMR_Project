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

def find_black_marks(img_bgr, min_area=80, max_area=6000):
    """
    검은 마크(네모/막대) 후보를 찾아 (cx,cy,w,h) 리스트 반환
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # 검은 것 강조 (이진화)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 노이즈 제거
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel, iterations=1)

    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    marks = []
    H, W = gray.shape[:2]
    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(c)

        # 너무 큰 덩어리/너무 납작한 건 제외 (필요시 조정)
        if w < 5 or h < 5:
            continue

        # “바”까지 허용하려면 aspect 조건을 완화
        aspect = w / float(h)
        if aspect < 0.15 or aspect > 8.0:
            continue

        cx = x + w/2.0
        cy = y + h/2.0

        # 시험 OMR 타이밍 바는 보통 상단 근처에 몰림 → 필요시 영역 제한 가능
        marks.append((cx, cy, w, h))

    return marks

def pick_corners_from_marks(marks, img_shape):
    """
    marks: (cx,cy,w,h)
    return: dict {"TL":(x,y), "TR":..., "BL":..., "BR":...}  (x,y는 중심)
    """
    H, W = img_shape[:2]
    if not marks:
        return {}

    # 가장자리 점수: 좌상단은 (cx+cy) 최소, 우상단은 (-cx+cy) 최소 ...
    pts = [(m[0], m[1]) for m in marks]

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
