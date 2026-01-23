import cv2
import numpy as np
import os

class OMREngine:
    def __init__(self):
        self.threshold_value = 140  # 흑/백 마킹 구분 기준
        self.pixel_threshold = 0.05 # 칸의 5% 이상 채워지면 마킹으로 인정

        # 표준 변환 크기 (A4 비율)
        self.width = 1654
        self.height = 2339

    def configure(self, threshold, pixel_ratio):
        """외부(DB/JSON)에서 설정을 받아와 적용"""
        self.threshold_value = int(float(threshold))
        self.pixel_threshold = float(pixel_ratio)

    def load_image(self, image_path):
        """이미지 로드 (한글 경로 대응 + 컬러로 읽기)"""
        if not os.path.exists(image_path):
            return None
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img

    def reorder(self, myPoints):
        """네 모서리 점 정렬 (좌상, 우상, 우하, 좌하)"""
        myPoints = myPoints.reshape((4, 2))
        myPointsNew = np.zeros((4, 1, 2), np.int32)

        add = myPoints.sum(1)
        myPointsNew[0] = myPoints[np.argmin(add)]  # 좌상
        myPointsNew[2] = myPoints[np.argmax(add)]  # 우하

        diff = np.diff(myPoints, axis=1)
        myPointsNew[1] = myPoints[np.argmin(diff)] # 우상
        myPointsNew[3] = myPoints[np.argmax(diff)] # 좌하
        return myPointsNew

    # =========================================================
    # 종이 외곽선 찾아 펴기 (Auto-Deskew)
    # =========================================================
    def align_image(self, img, json_data=None):
        """
        [업그레이드] 종이 외곽선 또는 내부 표 테두리를 찾아 반듯하게 펴주는 함수
        return: (aligned_img, ok, reason)
        """
        if img is None:
            return None, False, "image_none"

        # 1. [1단계 시도] 종이 외곽선 찾기 (기존 로직)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 1)
        canny = cv2.Canny(blur, 10, 50)
        
        contours_info = cv2.findContours(canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
        
        biggest = np.array([])
        max_area = 0
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 5000:
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
                if area > max_area and len(approx) == 4:
                    biggest = approx
                    max_area = area
        
        # 2. [2단계 시도] 외곽선을 못 찾았다면? -> 표 테두리 감지기(table_corner_detector) 호출
        if biggest.size == 0:
            try:
                from logic.vision.table_corner_detector import detect_table_corners
                corners, _ = detect_table_corners(img)
                if corners:
                    # 찾은 코너를 biggest 포맷(4x1x2 배열)으로 변환
                    biggest = np.array([
                        [corners["TL"]], [corners["TR"]], [corners["BR"]], [corners["BL"]]
                    ], dtype=np.int32)
            except ImportError:
                pass # 모듈이 없으면 패스
            except Exception as e:
                print(f"[Warn] 표 테두리 감지 실패: {e}")

        # 3. 투시 변환 (Warp) 수행
        if biggest.size != 0:
            biggest = self.reorder(biggest)
            pts1 = np.float32(biggest)
            
            # 좌상, 우상, 우하, 좌하 순서
            pts2 = np.float32([
                [0, 0],
                [self.width - 1, 0],
                [self.width - 1, self.height - 1],
                [0, self.height - 1]
            ])
            
            matrix = cv2.getPerspectiveTransform(pts1, pts2)
            img_warped = cv2.warpPerspective(img, matrix, (self.width, self.height))
            
            return img_warped, True, "warp_ok"

        # 4. 정 안되면 원본 리사이즈 반환
        return cv2.resize(img, (self.width, self.height)), False, "fallback_resize"

    # =========================================================
    # 사이드 마크 감지
    # =========================================================
    def find_side_markers(self, image, min_area=100, max_area=5000):
        """
        반환값: [{'cx': int, 'cy': int}, ...] (Y좌표 순 정렬)
        - Otsu 이진화로 밝기 편차 대응
        - findContours 호환 처리
        """
        try:
            if image is None:
                return []

            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # ✅ 자동 임계값(Otsu)
            _, binary = cv2.threshold(
                gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )

            contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

            h, w = image.shape[:2]
            markers = []

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if not (min_area < area < max_area):
                    continue

                x, y, bw, bh = cv2.boundingRect(cnt)
                if bh <= 0:
                    continue

                aspect_ratio = float(bw) / float(bh)
                if not (0.6 < aspect_ratio < 1.7):
                    continue

                # 왼쪽 20% 영역
                if x > (w * 0.2):
                    continue

                M = cv2.moments(cnt)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    markers.append({"cx": cx, "cy": cy})

            markers.sort(key=lambda m: m["cy"])
            return markers

        except Exception as e:
            print(f"[Warning] 사이드 마크 검색 중 오류: {e}")
            return []

    def _clamp_roi(self, image, x, y, w, h):
        if image is None or w <= 0 or h <= 0:
            return None
        H, W = image.shape[:2]
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(W, int(x) + int(w))
        y2 = min(H, int(y) + int(h))
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2 - x1, y2 - y1)

    def get_marking_score(self, image, x, y, w, h):
        """ROI의 검은색 픽셀 수 반환 (안전 클램프 적용)"""
        c = self._clamp_roi(image, x, y, w, h)
        if c is None:
            return 0
        x, y, w, h = c

        roi = image[y:y+h, x:x+w]
        if roi.size == 0:
            return 0

        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_roi, self.threshold_value, 255, cv2.THRESH_BINARY_INV)
        return cv2.countNonZero(mask)

    # =========================================================
    # 고정 좌표(ROI) 기반 판독
    # =========================================================
    def analyze_sheet(self, image_path, questions_rois, ref_anchor=None):
        original_img = self.load_image(image_path)
        if original_img is None:
            return "ERROR", [], None
        return self.analyze_sheet_cv(original_img, questions_rois, ref_anchor)

    def analyze_sheet_cv(self, original_img, questions_rois, ref_anchor=None):
        """이미지(numpy)를 받아 ROI 리스트를 순회하며 판독"""
        if original_img is None:
            return "ERROR", [], None

        H, W = original_img.shape[:2]  # ✅ 로컬 변수 사용 (엔진 표준 크기 값은 건드리지 않음)

        img_gray = cv2.cvtColor(original_img, cv2.COLOR_BGR2GRAY)
        _, binary_img = cv2.threshold(img_gray, self.threshold_value, 255, cv2.THRESH_BINARY_INV)

        debug_img = original_img.copy()
        sheet_results = []
        has_error = False

        for q_idx, rois in enumerate(questions_rois):
            marked_indices = []

            for r_idx, (x, y, w, h) in enumerate(rois):
                c = self._clamp_roi(binary_img, x, y, w, h)
                if c is None:
                    continue
                x, y, w, h = c

                roi = binary_img[y:y+h, x:x+w]
                marked_pixels = cv2.countNonZero(roi)
                area = w * h
                fill_ratio = (marked_pixels / area) if area > 0 else 0.0
                is_marked = fill_ratio > self.pixel_threshold

                color = (0, 255, 0) if is_marked else (0, 0, 255)
                cv2.rectangle(debug_img, (x, y), (x+w, y+h), color, 2)

                if is_marked:
                    marked_indices.append(r_idx)

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

            if status != "정상" and rois:
                try:
                    bx1 = min(r[0] for r in rois)
                    by1 = min(r[1] for r in rois)
                    bx2 = max(r[0] + r[2] for r in rois)
                    by2 = max(r[1] + r[3] for r in rois)
                    cv2.rectangle(
                        debug_img,
                        (int(bx1) - 5, int(by1) - 5),
                        (int(bx2) + 5, int(by2) + 5),
                        (255, 0, 255),
                        3
                    )
                except:
                    pass

        final_status = "오류" if has_error else "정상"
        return final_status, sheet_results, debug_img
