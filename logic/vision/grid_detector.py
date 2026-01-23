import cv2
import numpy as np

def find_timing_mark(image_cv, rect, aspect_tol=0.4):
    """
    특정 영역(rect) 내에서 OMR 마크를 정밀하게 찾습니다.
    - rect: (x, y, w, h) 탐색 영역
    - aspect_tol: 가로세로 비율 허용 오차 (정사각형이면 0.0일 때 1:1, 0.4면 0.6~1.4)
    """
    x, y, w, h = rect
    H, W = image_cv.shape[:2]
    
    # 영역 클램핑 (이미지 밖으로 나가는 것 방지)
    x0 = max(0, int(x)); y0 = max(0, int(y))
    x1 = min(W, int(x + w)); y1 = min(H, int(y + h))
    
    if x1 <= x0 or y1 <= y0:
        return None

    roi = image_cv[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # 1. 이진화 (Adaptive Threshold가 그림자에 더 강함)
    # 주변 25픽셀 평균보다 10 낮으면 검은색으로 간주
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                               cv2.THRESH_BINARY_INV, 25, 10)

    # 2. 노이즈 제거 (모폴로지)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, kernel, iterations=1) # 자잘한 점 제거
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=1) # 끊어진 선 연결

    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None

    best_cnt = None
    max_score = 0

    # 3. 형상 검증 (가장 큰 것 무조건 선택 X -> 가장 '마크 같은' 것 선택)
    roi_area = (x1 - x0) * (y1 - y0)
    
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if area < 50: continue # 너무 작은 노이즈
        
        x_c, y_c, w_c, h_c = cv2.boundingRect(cnt)
        
        # (1) 면적 비율 체크 (ROI 대비 너무 크거나 작으면 제외)
        # 보통 타이밍 마크는 ROI의 10%~90% 정도 차지한다고 가정
        if not (0.05 < area / roi_area < 0.95):
            continue

        # (2) 종횡비(Aspect Ratio) 체크
        aspect = float(w_c) / h_c
        if abs(1.0 - aspect) > aspect_tol: # 정사각형에서 많이 벗어나면 제외
            continue
            
        # (3) 충실도(Solidity) 체크: 외곽선 내부가 꽉 차 있는지 (글자는 낮음, 네모는 높음)
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity = float(area) / hull_area if hull_area > 0 else 0
        
        if solidity < 0.85: # 찌그러지거나 속이 빈 형태 제외
            continue

        # 점수 매기기 (면적이 클수록 + 정사각형에 가까울수록)
        score = area * (1.0 - abs(1.0 - aspect))
        if score > max_score:
            max_score = score
            best_cnt = cnt

    if best_cnt is None:
        return None

    M = cv2.moments(best_cnt)
    if M["m00"] == 0: return None
    
    cx = int(M["m10"] / M["m00"]) + x0
    cy = int(M["m01"] / M["m00"]) + y0
    
    return (cx, cy)


def find_black_marks(img_bgr, min_area=80, max_area=10000):
    """
    전체 이미지에서 마크 후보군을 찾습니다.
    (노이즈 제거 및 형상 검증 강화)
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # 1. Otsu + Binary Invert
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # 2. 노이즈 제거 (가로/세로 커널을 따로 써서 십자선 제거에도 효과적)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel, iterations=1) 
    
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    marks = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < min_area or area > max_area:
            continue
        
        x, y, w, h = cv2.boundingRect(c)
        
        # (1) 종횡비 제한 (타이밍 마크는 보통 정사각형~약간 직사각형)
        aspect = float(w) / h
        if aspect < 0.5 or aspect > 2.0: # 1:2 비율 이상 차이나면 마크 아님 (바코드 등 제외)
            continue
        
        # (2) Solidity 체크 (글자 제외용)
        hull = cv2.convexHull(c)
        hull_area = cv2.contourArea(hull)
        if hull_area == 0: continue
        solidity = area / hull_area
        
        if solidity < 0.8: # 0.8 미만이면 'ㄷ'자 형태나 글자일 확률 높음
            continue

        cx = x + w / 2.0
        cy = y + h / 2.0
        marks.append((cx, cy, w, h))

    return marks


def pick_corners_from_marks(marks, img_shape):
    """
    발견된 마크들 중 4귀퉁이(TL, TR, BL, BR)를 '4분면 방식'으로 찾습니다.
    (단순 x+y 방식보다 오인식 확률이 훨씬 낮음)
    """
    H, W = img_shape[:2]
    if not marks:
        return {}

    # 이미지 중심점
    cx_img = W / 2
    cy_img = H / 2

    # 각 사분면의 후보군 분류
    quadrants = {
        "TL": [], # Top-Left
        "TR": [], # Top-Right
        "BL": [], # Bottom-Left
        "BR": []  # Bottom-Right
    }

    for m in marks:
        mx, my, mw, mh = m
        
        # 중심점 기준으로 4분면 분류 (경계선 근처 마크 제외를 위해 약간 여유 둠)
        if mx < cx_img and my < cy_img:
            quadrants["TL"].append(m)
        elif mx >= cx_img and my < cy_img:
            quadrants["TR"].append(m)
        elif mx < cx_img and my >= cy_img:
            quadrants["BL"].append(m)
        elif mx >= cx_img and my >= cy_img:
            quadrants["BR"].append(m)

    corners = {}

    # 각 사분면에서 '가장 귀퉁이에 가까운' 점 선택
    # TL: (0,0) 거리 최소 / TR: (W,0) 거리 최소 ...
    
    if quadrants["TL"]:
        # TL은 (0,0)에서 가장 가까운 점 (x+y 최소화와 유사하나 거리기반이 더 정확)
        corners["TL"] = min(quadrants["TL"], key=lambda m: (m[0]**2 + m[1]**2))[:2]
    
    if quadrants["TR"]:
        # TR은 (W,0)에서 가장 가까운 점
        corners["TR"] = min(quadrants["TR"], key=lambda m: ((W-m[0])**2 + m[1]**2))[:2]
        
    if quadrants["BL"]:
        # BL은 (0,H)에서 가장 가까운 점
        corners["BL"] = min(quadrants["BL"], key=lambda m: (m[0]**2 + (H-m[1])**2))[:2]
        
    if quadrants["BR"]:
        # BR은 (W,H)에서 가장 가까운 점
        corners["BR"] = min(quadrants["BR"], key=lambda m: ((W-m[0])**2 + (H-m[1])**2))[:2]

    # float 좌표를 int로 변환
    result = {}
    for k, v in corners.items():
        result[k] = (int(v[0]), int(v[1]))

    return result