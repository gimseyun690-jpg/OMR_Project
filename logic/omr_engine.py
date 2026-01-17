import cv2
import numpy as np
import os

class OMREngine:
    def __init__(self):
        self.threshold_value = 140  # 흑/백 마킹 구분 기준
        self.pixel_threshold = 0.05 # 칸의 2% 이상 채워지면 마킹으로 인정
        
        # [중요] 변환될 표준 이미지 크기 (A4 비율 기준 고해상도)
        # 이 크기로 이미지를 '강제 정렬' 시킵니다.
        # 아까 find.py로 좌표를 딸 때 썼던 이미지의 해상도와 비슷해야 좋습니다.
        # (스캐너가 보통 width=1600~2400 정도 나옵니다. 적절히 고정합니다.)
        self.width = 1654 
        self.height = 2339 

    def configure(self, threshold, pixel_ratio):
        """외부(DB)에서 설정을 받아와 적용하는 함수"""
        self.threshold_value = int(threshold)
        self.pixel_threshold = float(pixel_ratio)
        # print(f"설정 적용됨: 임계값={self.threshold_value}, 비율={self.pixel_threshold}")

    def load_image(self, image_path):
        """이미지 로드 (한글 경로 대응 + 컬러로 읽기)"""
        if not os.path.exists(image_path):
            return None
        # 한글 경로 파일 읽기
        img_array = np.fromfile(image_path, np.uint8)
        # 컬러로 읽어야 디버그 박스(빨강/초록)를 그릴 수 있음
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR) 
        return img

    def reorder(self, myPoints):
        """
        네 모서리 점을 [좌상, 우상, 우하, 좌하] 순서로 정렬하는 함수
        이게 있어야 종이가 뒤집히지 않고 똑바로 펴집니다.
        """
        myPoints = myPoints.reshape((4, 2))
        myPointsNew = np.zeros((4, 1, 2), np.int32)
        
        add = myPoints.sum(1)
        myPointsNew[0] = myPoints[np.argmin(add)] # x+y가 최소인 곳 -> 좌상
        myPointsNew[2] = myPoints[np.argmax(add)] # x+y가 최대인 곳 -> 우하
        
        diff = np.diff(myPoints, axis=1)
        myPointsNew[1] = myPoints[np.argmin(diff)] # x-y가 최소 -> 우상
        myPointsNew[3] = myPoints[np.argmax(diff)] # x-y가 최대 -> 좌하
        return myPointsNew

    def align_image(self, img):
        """
        [핵심 기술] 종이의 외곽선을 찾아 반듯하게 펴주는 함수 (투시 변환)
        """
        # 1. 전처리 (흑백 -> 블러 -> 엣지 검출)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 1)
        canny = cv2.Canny(blur, 10, 50)
        
        # 2. 윤곽선 찾기
        contours, _ = cv2.findContours(canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        
        biggest = np.array([])
        max_area = 0
        
        # 3. 가장 큰 사각형(시험지) 찾기
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 5000: # 너무 작은 잡티는 무시
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                
                # 점이 4개(사각형)이고, 가장 큰 면적이라면? -> 시험지다!
                if area > max_area and len(approx) == 4:
                    biggest = approx
                    max_area = area
        
        # 4. 찾았다면 -> 반듯하게 펴기 (Warp)
        if biggest.size != 0:
            biggest = self.reorder(biggest)
            pts1 = np.float32(biggest)
            pts2 = np.float32([[0, 0], [self.width, 0], [0, self.height], [self.width, self.height]])
            
            matrix = cv2.getPerspectiveTransform(pts1, pts2)
            img_warped = cv2.warpPerspective(img, matrix, (self.width, self.height))
            
            # 잘라낸 이미지는 약간의 여백 제거를 위해 살짝 크롭(선택사항)
            # img_cropped = img_warped[20:img_warped.shape[0]-20, 20:img_warped.shape[1]-20]
            # img_cropped = cv2.resize(img_cropped, (self.width, self.height))
            return img_warped
        
        else:
            # 못 찾았으면 원본 그대로 반환 (배경이 너무 밝거나 종이가 안 보임)
            return cv2.resize(img, (self.width, self.height))

    def analyze_sheet(self, image_path, questions_rois, ref_anchor=None):
        """
        [호환용] path를 받아 이미지 로드 후 analyze_sheet_cv로 위임
        """
        original_img = self.load_image(image_path)
        if original_img is None:
            return "ERROR", [], None

        return self.analyze_sheet_cv(original_img, questions_rois, ref_anchor=ref_anchor)

    def analyze_sheet_cv(self, original_img, questions_rois, ref_anchor=None):
        """
        [신규] 이미 로드된 cv 이미지(ndarray)를 받아 판독
        - pipeline에서 deskew/warp한 이미지를 그대로 넘길 수 있게 됨
        """
        if original_img is None:
            return "ERROR", [], None

        # 엔진 내부에서 이미지 크기 최신화 (중요)
        self.height, self.width = original_img.shape[:2]

        # 1) 정렬/워핑 단계 (지금은 pass, 나중에 align_image로 교체)
        aligned_img = original_img

        # 2) 그레이 + 이진화
        img_gray = cv2.cvtColor(aligned_img, cv2.COLOR_BGR2GRAY)

        # threshold_value가 고정값이면 기존처럼, 아니라면 OTSU 옵션도 가능
        # 지금은 기존 로직 유지
        _, binary_img = cv2.threshold(
            img_gray, int(self.threshold_value), 255, cv2.THRESH_BINARY_INV
        )

        debug_img = aligned_img.copy()

        sheet_results = []
        has_error = False

        # ROI 순회
        for q_idx, rois in enumerate(questions_rois):
            marked_indices = []

            for r_idx, (x, y, w, h) in enumerate(rois):
                # ROI가 이미지 밖이면 안전하게 스킵/클립
                x = int(x); y = int(y); w = int(w); h = int(h)
                if w <= 0 or h <= 0:
                    continue

                x0 = max(0, x)
                y0 = max(0, y)
                x1 = min(self.width, x + w)
                y1 = min(self.height, y + h)

                if x1 <= x0 or y1 <= y0:
                    continue

                roi = binary_img[y0:y1, x0:x1]

                marked_pixels = cv2.countNonZero(roi)
                area = (x1 - x0) * (y1 - y0)
                fill_ratio = (marked_pixels / area) if area > 0 else 0.0

                is_marked = fill_ratio > float(self.pixel_threshold)

                # 시각화 (초록/빨강)
                color = (0, 255, 0) if is_marked else (0, 0, 255)
                cv2.rectangle(debug_img, (x0, y0), (x1, y1), color, 2)

                if is_marked:
                    marked_indices.append(r_idx)

            # 상태 결정
            if len(marked_indices) == 0:
                status = "공란"
                has_error = True
            elif len(marked_indices) > 1:
                status = "중복"
                has_error = True
            else:
                status = "정상"

            sheet_results.append({
                "q_num": q_idx + 1,
                "marked": marked_indices,
                "status": status
            })

            # 오류 강조(보라)
            if status != "정상" and rois:
                try:
                    x1 = min(int(r[0]) for r in rois)
                    y1 = min(int(r[1]) for r in rois)
                    x2 = max(int(r[0] + r[2]) for r in rois)
                    y2 = max(int(r[1] + r[3]) for r in rois)

                    x1 = max(0, x1 - 5); y1 = max(0, y1 - 5)
                    x2 = min(self.width - 1, x2 + 5)
                    y2 = min(self.height - 1, y2 + 5)

                    cv2.rectangle(debug_img, (x1, y1), (x2, y2), (255, 0, 255), 3)
                except Exception:
                    pass

        final_status = "오류" if has_error else "정상"
        return final_status, sheet_results, debug_img