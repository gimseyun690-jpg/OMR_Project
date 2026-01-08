import cv2
import numpy as np
import os

class OMREngine:
    def __init__(self):
        self.threshold_value = 140  # 임계값 (조명에 따라 조절 필요)
        self.pixel_threshold = 0.25 # 25% 이상 채워지면 마킹으로 인정

    def load_image(self, image_path):
        """이미지 로드 (한글 경로 대응)"""
        if not os.path.exists(image_path):
            return None
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        return img

    def analyze_sheet(self, image_path, questions_rois):
        """
        :param questions_rois: 문항별 좌표 리스트 
          예: [ [(x1,y1,w1,h1), (x2,y2,w2,h2)], ... ] -> 1번 문제의 찬성/반대 좌표
        :return: (판독상태, 문항별상세결과, 결과이미지)
        """
        original_img = self.load_image(image_path)
        if original_img is None:
            return "ERROR", [], None

        # 컬러 변환 (박스 그리기용)
        debug_img = cv2.cvtColor(original_img, cv2.COLOR_GRAY2BGR)
        
        # 이진화
        _, binary_img = cv2.threshold(original_img, self.threshold_value, 255, cv2.THRESH_BINARY_INV)

        sheet_results = [] # 각 문항의 결과 저장
        has_error = False  # 전체 용지 중 하나라도 에러가 있는지

        # 문항(Question) 단위로 반복
        for q_idx, rois in enumerate(questions_rois):
            marked_indices = [] # 체크된 인덱스 (0:찬성, 1:반대)
            
            for r_idx, (x, y, w, h) in enumerate(rois):
                roi = binary_img[y:y+h, x:x+w]
                marked_pixels = cv2.countNonZero(roi)
                fill_ratio = marked_pixels / (w * h)
                
                is_marked = fill_ratio > self.pixel_threshold
                
                # 시각화: 마킹됐으면 초록, 아니면 빨강 박스
                color = (0, 255, 0) if is_marked else (0, 0, 255)
                cv2.rectangle(debug_img, (x, y), (x+w, y+h), color, 2)
                
                if is_marked:
                    marked_indices.append(r_idx)

            # --- 판독 로직 (중복/공란 체크) ---
            status = "정상"
            if len(marked_indices) == 0:
                status = "공란" # 무효표
                has_error = True
            elif len(marked_indices) > 1:
                status = "중복" # 무효표
                has_error = True
            
            # 결과 저장
            sheet_results.append({
                "q_num": q_idx + 1,      # 문항 번호
                "marked": marked_indices,# 체크된 항목 리스트 예: [0] 또는 [0, 1]
                "status": status         # 정상, 공란, 중복
            })

            # 오류가 있는 문항은 이미지에 굵은 보라색 박스 추가
            if status != "정상":
                # 해당 문항 전체 영역을 감싸는 박스
                x1 = min(r[0] for r in rois)
                y1 = min(r[1] for r in rois)
                x2 = max(r[0]+r[2] for r in rois)
                y2 = max(r[1]+r[3] for r in rois)
                cv2.rectangle(debug_img, (x1-5, y1-5), (x2+5, y2+5), (255, 0, 255), 3)

        final_status = "오류" if has_error else "정상"
        return final_status, sheet_results, debug_img