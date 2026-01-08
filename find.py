import cv2
import os

# ==========================================
# 테스트할 이미지 경로 (여기를 파일명에 맞게 수정!)
# ==========================================
image_path = "data/scan_images/100000004.jpg" 

# 마우스 콜백 함수
drawing = False
ix, iy = -1, -1

def draw_rectangle(event, x, y, flags, param):
    global ix, iy, drawing, img_copy

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            img_copy = img.copy()
            cv2.rectangle(img_copy, (ix, iy), (x, y), (0, 255, 0), 2)
            cv2.imshow('Image', img_copy)

    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        cv2.rectangle(img_copy, (ix, iy), (x, y), (0, 255, 0), 2)
        cv2.imshow('Image', img_copy)
        
        # 너비, 높이 계산
        w = abs(x - ix)
        h = abs(y - iy)
        start_x = min(ix, x)
        start_y = min(iy, y)
        
        print(f"📌 좌표 발견! -> x={start_x}, y={start_y}, w={w}, h={h}")
        print(f"   (복사해서 사용하세요)")

# 이미지 로드
if not os.path.exists(image_path):
    print("이미지 파일이 없습니다. 경로를 확인하세요.")
else:
    img = cv2.imread(image_path)
    if img is None:
        # 한글 경로 문제일 경우
        import numpy as np
        n = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(n, cv2.IMREAD_COLOR)

    img_copy = img.copy()
    cv2.namedWindow('Image')
    cv2.setMouseCallback('Image', draw_rectangle)

    print("--- 사용법 ---")
    print("1. 마우스 왼쪽 버튼으로 '마킹 박스'를 드래그하세요.")
    print("2. 터미널에 찍히는 좌표를 기록하세요.")
    print("3. 종료하려면 'q' 키를 누르세요.")

    cv2.imshow('Image', img)
    while True:
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()