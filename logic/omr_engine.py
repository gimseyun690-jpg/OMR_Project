import cv2
import numpy as np
import os

class OMREngine:
    
    def __init__(self):
        # ===== 기준 해상도 (150dpi A4) =====
        self.width = 1240
        self.height = 1754

        # ===== 전처리 기본값 =====
        self.block_size = 15
        self.C = 7
        self.pixel_threshold = 0.05

        # ===== 마커 옵션 =====
        self.marker_thresh = 120


    def configure(self, block_size=None, pixel_ratio=None, marker_thresh=None, C=None):
        """외부 설정 적용"""
        if block_size is not None:
            self.block_size = int(block_size)
            if self.block_size % 2 == 0:
                self.block_size += 1

        if pixel_ratio is not None:
            self.pixel_threshold = float(pixel_ratio)

        if marker_thresh is not None:
            self.marker_thresh = int(marker_thresh)

        if C is not None:
            self.C = int(C)


    def load_image(self, image_path):
        if not os.path.exists(image_path): return None
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img

    def reorder(self, myPoints):
        """좌상, 우상, 우하, 좌하 순서 정렬"""
        myPoints = myPoints.reshape((4, 2))
        myPointsNew = np.zeros((4, 1, 2), np.int32)
        add = myPoints.sum(1)
        myPointsNew[0] = myPoints[np.argmin(add)]
        myPointsNew[2] = myPoints[np.argmax(add)]
        diff = np.diff(myPoints, axis=1)
        myPointsNew[1] = myPoints[np.argmin(diff)]
        myPointsNew[3] = myPoints[np.argmax(diff)]
        return myPointsNew

    def align_image(self, img):
        """
        [수정됨] "가장 큰 사각형 찾기(Warp)" 로직 완전 삭제
        - 이유: 표 테두리를 종이로 착각해 강제로 늘리면 좌표 비율이 깨짐.
        - 변경: 단순히 엔진 표준 해상도(1240x1754)로 리사이즈만 수행.
        """
        if img is None: 
            return None, False, "image_none"
        
        # 복잡한 지능형 처리 다 버리고, 무식하게 크기만 맞춥니다.
        # 이렇게 해야 원본 비율이 유지되어 '거리(Distance)' 기반 좌표가 정확히 맞습니다.
        img_resized = cv2.resize(img, (self.width, self.height))
        
        return img_resized, True, "resize_only"

    def _clamp_roi(self, image, x, y, w, h):
        if image is None or w <= 0 or h <= 0: return None
        H, W = image.shape[:2]
        x1 = max(0, int(x)); y1 = max(0, int(y))
        x2 = min(W, int(x) + int(w)); y2 = min(H, int(y) + int(h))
        if x2 <= x1 or y2 <= y1: return None
        return (x1, y1, x2 - x1, y2 - y1)

    # =========================================================
    # [NEW] 공통 전처리 메서드 (코드 중복 제거)
    # =========================================================
    def _preprocess_image(self, img):
        """크기 보정 -> Gray -> Adaptive Threshold -> Morphology"""
        if (img.shape[1] != self.width) or (img.shape[0] != self.height):
            work_img = cv2.resize(img, (self.width, self.height))
        else:
            work_img = img.copy()

        img_gray = cv2.cvtColor(work_img, cv2.COLOR_BGR2GRAY)
        binary_img = cv2.adaptiveThreshold(
            img_gray, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY_INV, 
            self.block_size, self.C
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        processed_img = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, kernel, iterations=1)
        
        return work_img, processed_img

    # =========================================================
    # [NEW] 사이드 마커 감지 (이전 코드 복구)
    # =========================================================
    def find_side_markers(self, image):
        """
        [최종 수정] 사이드 마커 인식 강화
        1. AdaptiveThreshold 제거 -> 고정 Threshold 사용 (하늘색 배경/글자 무시)
        2. Solidity(밀도) 필터 강화 -> 글자 무시
        3. Vertical Line Alignment (수직 정렬) -> 표 내부의 점 무시
        """
        try:
            if image is None: return []

            H, W = image.shape[:2]
            
            # 1. 전처리: 그냥 흑백 변환 후 '진한 검은색'만 남김
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 배경이 흰색/하늘색이고 마커가 진한 검은색이므로 
            # 100 이하는 검은색(1), 나머지는 흰색(0)으로 만드는게 훨씬 깔끔함
            _, binary = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)

            # 노이즈(작은 점) 제거
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

            contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

            candidates = []
            
            # 면적 필터 (150dpi ~ 300dpi 대응)
            # 너무 작으면 점, 너무 크면 표 테두리
            min_area = W * H * 0.0001
            max_area = W * H * 0.01

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < min_area or area > max_area: continue
                
                x, y, w, h = cv2.boundingRect(cnt)
                
                # [조건 1] 위치: 종이의 왼쪽 20% 안에 있어야 함
                if x > (W * 0.20): continue 

                # [조건 2] 비율: 정사각형에 가까워야 함 (0.6 ~ 1.6)
                ratio = float(w) / h
                if not (0.6 <= ratio <= 1.6): continue

                # [조건 3] 밀도(Solidity): ★핵심★
                # 글자는 획 사이가 비어있어서 hull 대비 area 비율이 낮음
                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull)
                if hull_area == 0: continue
                solidity = float(area) / hull_area
                
                # 마커는 꽉 찬 네모이므로 0.85 이상 나와야 함
                if solidity < 0.85: continue

                candidates.append({'cx': x + w // 2, 'cy': y + h // 2, 'x': x})

            if not candidates:
                return []

            # [조건 4] 수직 정렬 (Vertical Line Alignment) - 엉뚱한 점 거르기
            # X좌표가 비슷한 것끼리 그룹핑합니다.
            candidates.sort(key=lambda c: c['x'])
            
            groups = []
            if candidates:
                current_group = [candidates[0]]
                for i in range(1, len(candidates)):
                    # X좌표 차이가 10픽셀(150dpi 기준) 이내면 같은 라인으로 간주
                    if abs(candidates[i]['x'] - candidates[i-1]['x']) < 15:
                        current_group.append(candidates[i])
                    else:
                        groups.append(current_group)
                        current_group = [candidates[i]]
                groups.append(current_group)

            # 가장 많은 점이 모여있는 그룹이 '진짜 마커 라인'일 확률이 높음
            best_group = max(groups, key=len)
            
            # 만약 개수가 같은 그룹이 있다면, 더 왼쪽에 있는 그룹을 선택 (사이드 마커니까)
            # (여기서는 간단히 가장 긴 그룹 선택)

            # Y축 정렬 후 반환
            best_group.sort(key=lambda c: c['cy'])
            return best_group

        except Exception as e:
            print(f"[ERROR] Find Markers: {e}")
            return []


    # =========================================================
    # 1. 고정 좌표(ROI) 기반 판독
    # =========================================================
    def analyze_sheet_cv(self, original_img, questions_rois, ref_anchor=None):
        if original_img is None: return "ERROR", [], None

        work_img, processed_img = self._preprocess_image(original_img)
        debug_img = work_img.copy()
        
        sheet_results = []
        has_error = False

        for q_idx, rois in enumerate(questions_rois):
            marked_indices = []
            for r_idx, (x, y, w, h) in enumerate(rois):
                if self._check_roi(processed_img, x, y, w, h, debug_img, (0, 255, 0)):
                    marked_indices.append(r_idx)

            status = self._determine_status(marked_indices)
            if status != "정상": has_error = True
            
            sheet_results.append({"q_num": q_idx + 1, "marked": marked_indices, "status": status})
            if status != "정상": self._draw_error_box(debug_img, rois)

        return ("오류" if has_error else "정상"), sheet_results, debug_img

    # =========================================================
    # [NEW] 2. 사이드 마커 기반 동적 판독 (Pipeline에서 이관됨)
    # =========================================================
    # =========================================================
    # [수정] 2. 사이드 마커 기반 동적 판독
    # =========================================================
    def analyze_side_marker_sheet(self, original_img, questions, params, scale=1.0):
        """
        :param scale: 300dpi 좌표를 150dpi 이미지에 맞추기 위한 비율 (0.5 등)
        """
        if original_img is None: return "ERROR", [], None, "IMG_NONE"

        work_img, processed_img = self._preprocess_image(original_img)
        debug_img = work_img.copy()

        # 1. 마커 찾기
        markers = self.find_side_markers(work_img)
        
        # [안전장치] 마커가 하나도 안 잡혔다면? -> 전처리 이미지가 너무 깨졌을 수 있음. 원본으로 재시도
        if not markers:
            markers = self.find_side_markers(original_img)

        if len(markers) < len(questions):
            # 디버깅을 위해 찾은 마커라도 표시
            for m in markers:
                cv2.circle(debug_img, (m['cx'], m['cy']), 5, (0, 0, 255), -1)
            return "ERR", [], debug_img, "TIMING_MARK"

        # 2. 파라미터 추출 및 스케일 적용 (핵심 수정 부분)
        # JSON 키가 'marker_to_agree_dist'여도 읽을 수 있게 처리
        raw_dist_agree = params.get('dist_agree') or params.get('marker_to_agree_dist') or 100

        raw_dist_disagree = (
            params.get('dist_disagree')
            or params.get('marker_to_disagree_dist')
            or 200
        )

        if params.get('marker_to_disagree_dist'): 
            raw_dist_disagree = params.get('marker_to_disagree_dist')

        # 스케일 적용 (300dpi 좌표 -> 150dpi 좌표)
        box_w = int(int(params.get('box_w', 35)) * scale)
        box_h = int(int(params.get('box_h', 35)) * scale)
        dist_agree = int(raw_dist_agree * scale)
        dist_disagree = int(raw_dist_disagree * scale)

        sheet_results = []
        has_error = False
        error_reason = ""

        for i, q in enumerate(questions):
            q_num = q.get("no", i + 1)
            
            # 마커가 부족하면 루프 중단 (IndexError 방지)
            if i >= len(markers):
                sheet_results.append({"q_num": q_num, "marked": [], "status": "마커없음"})
                has_error = True
                continue

            # 마커 기반 좌표 계산
            base_cx = markers[i]['cx']
            base_cy = markers[i]['cy']
            start_y = base_cy - (box_h // 2)

            # 찬성(0), 반대(1) 좌표 생성
            rois = [
                (base_cx + dist_agree, start_y, box_w, box_h),
                (base_cx + dist_disagree, start_y, box_w, box_h)
            ]

            marked_indices = []
            for r_idx, (rx, ry, rw, rh) in enumerate(rois):
                # 디버깅용: 검색 영역 박스 그리기 (파란색) - 실제 좌표가 어디 찍히는지 확인용
                cv2.rectangle(debug_img, (rx, ry), (rx+rw, ry+rh), (255, 0, 0), 1)

                if self._check_roi(processed_img, rx, ry, rw, rh, debug_img, (0, 255, 0)):
                    marked_indices.append(r_idx)

            status = self._determine_status(marked_indices)
            if status != "정상": 
                has_error = True
                if not error_reason: error_reason = status 

            sheet_results.append({"q_num": q_num, "marked": marked_indices, "status": status})
            if status != "정상": self._draw_error_box(debug_img, rois)

            # 디버깅: 마커 위치 표시 (빨간 점)
            cv2.circle(debug_img, (base_cx, base_cy), 3, (0, 0, 255), -1)

        return ("ERR" if has_error else "OK"), sheet_results, debug_img, error_reason

    # =========================================================
    # [NEW] 3. 수험정보(Candidate Info) 판독 (Pipeline에서 이관됨)
    # =========================================================
    def analyze_candidate_info(self, original_img, config, scale=1.0):
        """
        수험번호, 생년월일, 선택과목 판독
        scale: JSON 좌표(예:200dpi)를 현재 이미지(150dpi)로 변환하기 위한 비율
        """
        if original_img is None or not config:
            return False, {}, None

        work_img, processed_img = self._preprocess_image(original_img)
        # 디버그 이미지는 투명 레이어처럼 겹쳐 보기 위해 별도 생성 가능
        debug_img = np.zeros_like(work_img) 

        info = {}
        error_msg = ""
        is_ok = True

        # (1) 수험번호
        if "exam_no" in config:
            ok, val = self._decode_digit_grid(processed_img, config["exam_no"], scale, debug_img)
            if ok: info["exam_no"] = val
            else: 
                is_ok = False
                error_msg = "수험번호 판독 오류"

        # (2) 생년월일
        if "birth" in config:
            ok, val = self._decode_digit_grid(processed_img, config["birth"], scale, debug_img)
            if ok: info["birth"] = val
            elif is_ok: # 앞선 오류가 없다면 기록
                is_ok = False
                error_msg = "생년월일 판독 오류"

        # (3) 선택과목
        if "subject" in config:
            ok, val = self._decode_single_choice(processed_img, config["subject"], scale, debug_img)
            if ok: info["subject"] = val
            elif is_ok:
                is_ok = False
                error_msg = "선택과목 판독 오류"

        return is_ok, info, debug_img

    # --- 내부 도우미 메서드 ---

    def _check_roi(self, processed_img, x, y, w, h, debug_img, color):
        """ROI 마킹 여부 확인 및 디버그 드로잉"""
        c = self._clamp_roi(processed_img, x, y, w, h)
        if c is None: return False
        x, y, w, h = c
        
        roi = processed_img[y:y+h, x:x+w]
        marked_pixels = cv2.countNonZero(roi)
        area = w * h
        ratio = (marked_pixels / area) if area > 0 else 0.0
        
        is_marked = ratio > self.pixel_threshold

        if debug_img is not None:
            # 마킹된 곳은 진한 색, 아닌 곳은 옅은 색
            draw_color = color if is_marked else (0, 0, 255)
            thickness = 2 if is_marked else 1
            cv2.rectangle(debug_img, (x, y), (x+w, y+h), draw_color, thickness)
            if is_marked:
                cv2.putText(debug_img, f"{int(ratio*100)}%", (x, y+h-2), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.3, draw_color, 1)
        return is_marked

    def _determine_status(self, marked_indices):
        if len(marked_indices) == 0: return "공란"
        if len(marked_indices) > 1: return "중복"
        return "정상"

    def _draw_error_box(self, debug_img, rois):
        try:
            bx1 = min(r[0] for r in rois)
            by1 = min(r[1] for r in rois)
            bx2 = max(r[0] + r[2] for r in rois)
            by2 = max(r[1] + r[3] for r in rois)
            cv2.rectangle(debug_img, (bx1-2, by1-2), (bx2+2, by2+2), (0, 255, 255), 2)
        except: pass

    def _decode_digit_grid(self, img, cfg, scale, debug_img):
        """그리드 형태 숫자 인식 (예: 수험번호)"""
        grid = cfg.get("grid", {})
        
        # 좌표 스케일링 적용
        start_x = int(grid.get("x", 0) * scale)
        start_y = int(grid.get("y", 0) * scale)
        col_w = int(grid.get("col_w", 20) * scale)
        row_h = int(grid.get("row_h", 20) * scale)
        
        cols = int(grid.get("cols", 0))
        rows = int(grid.get("rows", 10))
        digits = int(cfg.get("digits", cols))

        if digits <= 0 or rows <= 0: return False, ""

        result_str = ""
        for c in range(digits):
            best_r = -1
            max_ratio = -1.0
            hits = 0
            
            for r in range(rows):
                rx = start_x + (c * col_w)
                ry = start_y + (r * row_h)
                
                # 마킹 확인 (내부적으로 디버그 그림)
                # 여기서는 is_marked 여부보다는 비율 비교가 중요할 수 있음
                roi_c = self._clamp_roi(img, rx, ry, col_w, row_h)
                if roi_c:
                    cx, cy, cw, ch = roi_c
                    roi = img[cy:cy+ch, cx:cx+cw]
                    ratio = cv2.countNonZero(roi) / (cw * ch) if cw*ch > 0 else 0
                    
                    # 디버그 (cyan 색상)
                    if debug_img is not None:
                        color = (255, 255, 0) if ratio > self.pixel_threshold else (50, 50, 50)
                        cv2.rectangle(debug_img, (rx, ry), (rx+col_w, ry+row_h), color, 1)

                    if ratio > self.pixel_threshold:
                        hits += 1
                        if ratio > max_ratio:
                            max_ratio = ratio
                            best_r = r
            
            if hits == 1 and best_r != -1:
                result_str += str(best_r)
            else:
                return False, "" # 마킹이 없거나 중복이면 실패 처리
                
        return True, result_str

    def _decode_single_choice(self, img, cfg, scale, debug_img):
        """단일 선택 인식 (예: 선택과목)"""
        choices = cfg.get("choices", [])
        if not choices: return False, ""
        
        picked_label = ""
        hits = 0
        
        for ch in choices:
            x = int(ch.get("x", 0) * scale)
            y = int(ch.get("y", 0) * scale)
            w = int(ch.get("w", 20) * scale)
            h = int(ch.get("h", 20) * scale)
            
            # 마킹 확인
            if self._check_roi(img, x, y, w, h, debug_img, (255, 0, 255)):
                hits += 1
                picked_label = ch.get("label", "")
        
        if hits == 1: return True, picked_label
        return False, ""