import cv2
import os
import numpy as np

# ==========================================
# 테스트할 이미지 경로 (여기를 파일명에 맞게 수정!)
# ==========================================
image_path = "data/scan_images/100000001.jpg" 

# ==========================================
# [설정] 화면에 보여줄 높이 (모니터 해상도에 맞춰 조절)
# ==========================================
DISPLAY_HEIGHT = 900  # 화면 세로 크기에 맞춰서 이 숫자를 조절하세요 (예: 800~1000)

# 전역 변수
drawing = False
ix, iy = -1, -1
scale_ratio = 1.0 # 축소 비율

def draw_rectangle(event, x, y, flags, param):
    global ix, iy, drawing, img_resized_copy, scale_ratio

    # 화면상의 좌표(x, y)를 원본 좌표로 변환
    real_x = int(x / scale_ratio)
    real_y = int(y / scale_ratio)

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y # 그리기 시작점 (화면 기준)

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            img_resized_copy = img_resized.copy()
            # 그림은 화면 기준으로 그립니다 (눈에 보여야 하니까)
            cv2.rectangle(img_resized_copy, (ix, iy), (x, y), (0, 255, 0), 2)
            cv2.imshow('Image', img_resized_copy)

    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        cv2.rectangle(img_resized_copy, (ix, iy), (x, y), (0, 255, 0), 2)
        cv2.imshow('Image', img_resized_copy)
        
        # --- [핵심] 원본 기준 좌표 계산 ---
        # 시작점(ix, iy)도 원본 기준으로 변환
        real_ix = int(ix / scale_ratio)
        real_iy = int(iy / scale_ratio)

        # 너비, 높이 계산 (절댓값)
        w = abs(real_x - real_ix)
        h = abs(real_y - real_iy)
        
        # 시작점 (왼쪽 위) 잡기
        start_x = min(real_ix, real_x)
        start_y = min(real_iy, real_y)
        
        print(f"\n✅ 좌표 확보 (원본 기준):")
        print(f"   x={start_x}, y={start_y}, w={w}, h={h}")
        print(f"   ----------------------------------")

# 이미지 로드
if not os.path.exists(image_path):
    print(f"❌ 오류: 파일이 없습니다 -> {image_path}")
else:
    # 1. 원본 이미지 불러오기
    img_array = np.fromfile(image_path, np.uint8)
    img_origin = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    if img_origin is None:
        print("이미지를 읽을 수 없습니다.")
    else:
        # 2. 화면에 맞게 축소하기
        h, w = img_origin.shape[:2]
        scale_ratio = DISPLAY_HEIGHT / h # 원본 대비 몇 배로 줄였는지 계산
        
        new_w = int(w * scale_ratio)
        new_h = int(h * scale_ratio)
        
        # 보여주기용 이미지 (img_resized)
        img_resized = cv2.resize(img_origin, (new_w, new_h))
        img_resized_copy = img_resized.copy()

        cv2.namedWindow('Image')
        cv2.setMouseCallback('Image', draw_rectangle)

        print(f"--- [이미지 좌표 찾기 도구] ---")
        print(f"* 원본 크기: {w} x {h}")
        print(f"* 화면 표시: {new_w} x {new_h} (비율: {scale_ratio:.2f})")
        print(f"1. 마우스로 박스를 드래그하세요.")
        print(f"2. 터미널에 출력되는 '원본 기준' 좌표를 사용하세요.")
        print(f"3. 종료하려면 'q' 키를 누르세요.")

        cv2.imshow('Image', img_resized)
        while True:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cv2.destroyAllWindows()