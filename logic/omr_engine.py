import cv2
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

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
        self.marker_thresh = 215
        self.global_offset_x = 0
        self.global_offset_y = 0


    def configure(
        self,
        block_size=None,
        pixel_ratio=None,
        marker_thresh=None,
        C=None,
        global_offset_x=None,
        global_offset_y=None,
    ):
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

        if global_offset_x is not None:
            self.global_offset_x = int(global_offset_x)
        if global_offset_y is not None:
            self.global_offset_y = int(global_offset_y)

    def load_image(self, image_path):
        if not os.path.exists(image_path): return None
        img_array = np.fromfile(image_path, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img

    def parse_config(self, config):
        if not isinstance(config, dict):
            return []

        layout_defaults = config.get("layout_defaults", {})
        if not isinstance(layout_defaults, dict):
            layout_defaults = {}

        question_groups = config.get("question_groups", [])
        if not isinstance(question_groups, list):
            return []

        expanded = []

        for group in question_groups:
            if not isinstance(group, dict):
                continue

            try:
                start_no = int(group.get("start_no", 1))
                count = int(group.get("count", 0))
                start_row_index = int(group.get("start_row_index", 0))
            except Exception:
                continue

            if count <= 0:
                continue

            group_overrides = {
                k: v
                for k, v in group.items()
                if k not in ("start_no", "count", "start_row_index")
            }

            for i in range(count):
                q = dict(layout_defaults)
                q.update(group_overrides)
                q["no"] = start_no + i
                q["row_index"] = start_row_index + i
                expanded.append(q)

        return expanded

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
        입력 이미지를 기준 해상도(150dpi, 1240x1754)로 맞춤.
        - 종횡비를 보존하고, 가로 스캔은 필요 시 90도 회전
        - 비율 차이가 큰 경우에는 흰 배경 패딩(찌부 방지)
        """
        if img is None:
            return None, False, "image_none"
        if len(img.shape) < 2:
            return None, False, "invalid_shape"

        target_w, target_h = int(self.width), int(self.height)
        target_ratio = float(target_w) / float(target_h) if target_h > 0 else 1.0

        work = img
        h, w = work.shape[:2]
        if w <= 0 or h <= 0:
            return None, False, "invalid_size"

        if w == target_w and h == target_h:
            return work, True, "original"

        # 가로로 스캔된 경우(비율이 반대로 더 가까운 경우)에는 먼저 90도 회전.
        ratio_now = float(w) / float(h)
        ratio_rot = float(h) / float(w)
        rotated = False
        if abs(ratio_rot - target_ratio) + 1e-6 < abs(ratio_now - target_ratio):
            work = cv2.rotate(work, cv2.ROTATE_90_CLOCKWISE)
            rotated = True
            h, w = work.shape[:2]

        # 업/다운 스케일에 따라 보간 방식 선택
        scale = min(float(target_w) / float(w), float(target_h) / float(h))
        new_w = max(1, int(round(float(w) * scale)))
        new_h = max(1, int(round(float(h) * scale)))
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        resized = cv2.resize(work, (new_w, new_h), interpolation=interp)

        # 비율이 거의 동일하면 전체 캔버스로 맞춤(기존 동작과 유사).
        aspect_diff = abs((float(w) / float(h)) - target_ratio)
        if new_w == target_w and new_h == target_h:
            return resized, True, ("rotated_resized" if rotated else "resized")
        if aspect_diff <= 0.03:
            stretched = cv2.resize(resized, (target_w, target_h), interpolation=interp)
            return stretched, True, ("rotated_resized" if rotated else "resized")

        # 비율 차이가 큰 경우는 찌부를 피하기 위해 흰 배경에 가운데 배치.
        if resized.ndim == 2:
            canvas = np.full((target_h, target_w), 255, dtype=resized.dtype)
        else:
            canvas = np.full((target_h, target_w, resized.shape[2]), 255, dtype=resized.dtype)
        x0 = max(0, (target_w - new_w) // 2)
        y0 = max(0, (target_h - new_h) // 2)
        x1 = min(target_w, x0 + new_w)
        y1 = min(target_h, y0 + new_h)
        canvas[y0:y1, x0:x1] = resized[0:(y1 - y0), 0:(x1 - x0)]
        return canvas, True, ("rotated_padded" if rotated else "padded")

    def align_image_warp(self, img):
        """호환용 래퍼: 현재는 기준 해상도 리사이즈만 수행"""
        return self.align_image(img)

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
        # [안전장치 추가] 이미지가 없으면 그냥 빈 값 반환
        if img is None:
            return None, None
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
    # [NEW] 멀티 방향 마커 감지
    # =========================================================
    def find_markers(self, image, location="left", min_count=3):
        """
        Robust timing-mark detector.
        Strictly separates solid rectangular marks from text/lines/barcodes.

        location: left/right/top/bottom
        """
        # Strict filters requested:
        # 1) Solidity >= 0.90
        # 2) Fill ratio >= 0.70
        # 3) Group size consistency (std/mean <= 0.20)
        SOLIDITY_MIN = 0.90
        FILL_RATIO_MIN = 0.70
        SIZE_STD_MAX = 0.20

        # Extra guards to suppress text/line-like noise.
        EXTENT_MIN = 0.55
        ASPECT_MIN = 0.45
        ASPECT_MAX = 2.20
        RECT_FILL_MIN = 0.65
        RING_RATIO_MAX = 0.18

        def _roi_from_location(img_h, img_w, loc, ratio):
            if loc == "right":
                x0 = int(img_w * (1.0 - ratio))
                return x0, 0, img_w - x0, img_h
            if loc == "top":
                return 0, 0, img_w, int(img_h * ratio)
            if loc == "bottom":
                y0 = int(img_h * (1.0 - ratio))
                return 0, y0, img_w, img_h - y0
            return 0, 0, int(img_w * ratio), img_h

        def _required_span_ratio(group_len):
            if group_len <= 4:
                return 0.20
            if group_len <= 6:
                return 0.24
            return 0.30

        def _cluster_candidates(cands, axis_key):
            if not cands:
                return []
            ordered = sorted(cands, key=lambda c: int(c.get(axis_key, 0)))
            axis_sizes = [int(c.get("w", 1)) if axis_key == "x" else int(c.get("h", 1)) for c in ordered]
            median_size = float(np.median(np.asarray(axis_sizes, dtype=np.float32))) if axis_sizes else 1.0
            gap_thr = max(12, int(round(median_size * 0.9)))

            groups = []
            cur = [ordered[0]]
            for i in range(1, len(ordered)):
                prev = int(ordered[i - 1].get(axis_key, 0))
                curv = int(ordered[i].get(axis_key, 0))
                if abs(curv - prev) <= gap_thr:
                    cur.append(ordered[i])
                else:
                    groups.append(cur)
                    cur = [ordered[i]]
            groups.append(cur)
            return groups

        def _is_uniform_group(group):
            if not group:
                return False
            if len(group) == 1:
                return True
            ws = np.asarray([max(1, int(c.get("w", 1))) for c in group], dtype=np.float32)
            hs = np.asarray([max(1, int(c.get("h", 1))) for c in group], dtype=np.float32)
            mean_w = float(np.mean(ws))
            mean_h = float(np.mean(hs))
            if mean_w <= 0 or mean_h <= 0:
                return False
            rel_std_w = float(np.std(ws)) / mean_w
            rel_std_h = float(np.std(hs)) / mean_h
            return rel_std_w <= SIZE_STD_MAX and rel_std_h <= SIZE_STD_MAX

        def _validate_axis_spacing(group, axis_key):
            if not group or len(group) < 3:
                return bool(group)
            coords = sorted([int(c.get(axis_key, 0)) for c in group])
            gaps = np.diff(np.asarray(coords, dtype=np.float32))
            if gaps.size == 0:
                return False
            median_gap = float(np.median(gaps))
            if median_gap <= 1e-6:
                return False
            rel_std_gap = float(np.std(gaps)) / median_gap
            return rel_std_gap <= 0.30

        def _detect_in_roi(img, loc, ratio):
            if img is None:
                return []
            H, W = img.shape[:2]
            rx, ry, rw, rh = _roi_from_location(H, W, loc, ratio)
            if rw <= 0 or rh <= 0:
                return []

            roi_img = img[ry:ry + rh, rx:rx + rw]
            gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, int(self.marker_thresh), 255, cv2.THRESH_BINARY_INV)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

            contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

            roi_area = float(max(1, rw * rh))
            min_area = roi_area * 0.0001
            max_area = roi_area * 0.012

            candidates = []
            rej_area = 0
            rej_aspect = 0
            rej_solidity = 0
            rej_fill = 0
            rej_extent = 0
            rej_edge = 0
            rej_rect = 0
            rej_ring = 0

            for cnt in contours:
                area = float(cv2.contourArea(cnt))
                if area < min_area or area > max_area:
                    rej_area += 1
                    continue

                lx, ly, w, h = cv2.boundingRect(cnt)
                if w <= 1 or h <= 1:
                    rej_area += 1
                    continue

                # Ignore boundary-touching blobs (common in table borders / crop edges).
                if lx <= 0 or ly <= 0 or (lx + w) >= rw - 1 or (ly + h) >= rh - 1:
                    rej_edge += 1
                    continue

                ratio_wh = float(w) / float(h)
                if ratio_wh < ASPECT_MIN or ratio_wh > ASPECT_MAX:
                    rej_aspect += 1
                    continue

                hull = cv2.convexHull(cnt)
                hull_area = float(cv2.contourArea(hull))
                if hull_area <= 1e-6:
                    rej_solidity += 1
                    continue
                solidity = area / hull_area
                if solidity < SOLIDITY_MIN:
                    rej_solidity += 1
                    continue

                bbox_area = float(max(1, w * h))
                extent = area / bbox_area
                if extent < EXTENT_MIN:
                    rej_extent += 1
                    continue

                rect = cv2.minAreaRect(cnt)
                rw_rect, rh_rect = rect[1]
                rect_area = float(rw_rect * rh_rect)
                if rect_area <= 1e-6:
                    rej_rect += 1
                    continue
                rect_fill = area / rect_area
                if rect_fill < RECT_FILL_MIN:
                    rej_rect += 1
                    continue

                box = binary[ly:ly + h, lx:lx + w]
                if box is None or box.size == 0:
                    rej_fill += 1
                    continue
                fill_ratio = float(cv2.countNonZero(box)) / float(box.size)
                if fill_ratio < FILL_RATIO_MIN:
                    rej_fill += 1
                    continue

                pad = max(2, int(round(0.35 * float(max(w, h)))))
                ex1 = max(0, lx - pad)
                ey1 = max(0, ly - pad)
                ex2 = min(rw, lx + w + pad)
                ey2 = min(rh, ly + h + pad)

                expanded = binary[ey1:ey2, ex1:ex2]
                if expanded is None or expanded.size == 0:
                    rej_ring += 1
                    continue

                outer_nonzero = int(cv2.countNonZero(expanded))
                inner_nonzero = int(cv2.countNonZero(box))
                ring_area = int(expanded.size - box.size)
                ring_nonzero = max(0, outer_nonzero - inner_nonzero)
                ring_ratio = (float(ring_nonzero) / float(ring_area)) if ring_area > 0 else 1.0
                if ring_ratio > RING_RATIO_MAX:
                    rej_ring += 1
                    continue

                x = lx + rx
                y = ly + ry
                candidates.append(
                    {
                        "cx": int(x + w // 2),
                        "cy": int(y + h // 2),
                        "x": int(x),
                        "y": int(y),
                        "w": int(w),
                        "h": int(h),
                        "solidity": float(solidity),
                        "fill_ratio": float(fill_ratio),
                        "ring_ratio": float(ring_ratio),
                    }
                )

            logger.debug(
                "[MarkerDetect] loc=%s ratio=%.2f contours=%d kept=%d rej_area=%d rej_aspect=%d rej_solidity=%d rej_fill=%d rej_extent=%d rej_edge=%d rej_rect=%d rej_ring=%d",
                loc,
                float(ratio),
                len(contours),
                len(candidates),
                rej_area,
                rej_aspect,
                rej_solidity,
                rej_fill,
                rej_extent,
                rej_edge,
                rej_rect,
                rej_ring,
            )
            return candidates

        try:
            if image is None:
                return []

            loc = str(location or "left").strip().lower()
            if loc not in ("left", "right", "top", "bottom"):
                loc = "left"

            candidates = []
            for ratio in (0.10, 0.15, 0.20):
                candidates = _detect_in_roi(image, loc, ratio)
                if candidates:
                    break

            if not candidates:
                logger.info("[MarkerDetect] loc=%s min_count=%d -> no candidates", loc, int(min_count))
                return []

            group_axis = "y" if loc in ("top", "bottom") else "x"
            groups = _cluster_candidates(candidates, axis_key=group_axis)
            groups = [g for g in groups if len(g) >= int(min_count)]
            groups = [g for g in groups if _is_uniform_group(g)]
            if not groups:
                logger.info("[MarkerDetect] loc=%s -> no uniform groups", loc)
                return []

            if loc in ("top", "bottom"):
                primary_key = "y"
                span_key = "cx"
                span_limit = float(image.shape[1]) * _required_span_ratio(max(1, int(min_count) + 1))
                side_fn = min if loc == "top" else max
            else:
                primary_key = "x"
                span_key = "cy"
                span_limit = float(image.shape[0]) * _required_span_ratio(max(1, int(min_count) + 1))
                side_fn = min if loc == "left" else max

            groups = sorted(groups, key=lambda g: len(g), reverse=True)
            edge_group = side_fn(
                groups,
                key=lambda g: float(np.median([int(c.get(primary_key, 0)) for c in g])),
            )

            # If same edge has several groups, prefer the longer/cleaner one.
            edge_axis = float(np.median([int(c.get(primary_key, 0)) for c in edge_group]))
            same_edge = []
            for g in groups:
                g_axis = float(np.median([int(c.get(primary_key, 0)) for c in g]))
                if abs(g_axis - edge_axis) <= 12.0:
                    same_edge.append(g)
            if same_edge:
                edge_group = max(
                    same_edge,
                    key=lambda g: (
                        len(g),
                        float(np.mean([float(c.get("solidity", 0.0)) for c in g])),
                        float(np.mean([float(c.get("fill_ratio", 0.0)) for c in g])),
                    ),
                )

            span = float(
                max(int(c.get(span_key, 0)) for c in edge_group)
                - min(int(c.get(span_key, 0)) for c in edge_group)
            )
            if span < span_limit:
                logger.debug(
                    "[MarkerDetect] loc=%s group_reject=span span=%.1f required=%.1f len=%d",
                    loc,
                    span,
                    span_limit,
                    len(edge_group),
                )
                return []

            if not _validate_axis_spacing(edge_group, span_key):
                logger.debug("[MarkerDetect] loc=%s group_reject=axis_spacing len=%d", loc, len(edge_group))
                return []

            mean_ring = float(np.mean([float(c.get("ring_ratio", 1.0)) for c in edge_group]))
            if mean_ring > 0.12:
                logger.debug(
                    "[MarkerDetect] loc=%s group_reject=ring mean_ring=%.3f len=%d",
                    loc,
                    mean_ring,
                    len(edge_group),
                )
                return []

            if loc in ("top", "bottom"):
                edge_group = sorted(edge_group, key=lambda c: int(c.get("cx", 0)))
            else:
                edge_group = sorted(edge_group, key=lambda c: int(c.get("cy", 0)))

            logger.info(
                "[MarkerDetect] loc=%s selected=%d span=%.1f solidity=%.3f fill=%.3f ring=%.3f",
                loc,
                len(edge_group),
                span,
                float(np.mean([float(c.get("solidity", 0.0)) for c in edge_group])),
                float(np.mean([float(c.get("fill_ratio", 0.0)) for c in edge_group])),
                mean_ring,
            )
            return edge_group

        except Exception as e:
            logger.exception("[MarkerDetect] exception: %s", e)
            return []

    def find_side_markers(self, image):
        """호환용 래퍼 (left 고정)"""
        return self.find_markers(image, location="left", min_count=3)

    def normalize_orientation(self, image, expected_location="left", min_count=3):
        """
        Normalize sheet orientation so that detected timing markers end up on expected_location.

        Returns:
            (rotated_image, markers_on_expected_side)
        """
        if image is None:
            return None, []

        target_loc = str(expected_location or "left").strip().lower()
        if target_loc not in ("left", "right", "top", "bottom"):
            target_loc = "left"

        def _rotate_quarter_turns(src, k_cw):
            k = int(k_cw) % 4
            if k == 0:
                return src
            if k == 1:
                return cv2.rotate(src, cv2.ROTATE_90_CLOCKWISE)
            if k == 2:
                return cv2.rotate(src, cv2.ROTATE_180)
            return cv2.rotate(src, cv2.ROTATE_90_COUNTERCLOCKWISE)

        def _marker_span_ratio(markers, location, shape):
            if not markers or len(markers) < 2:
                return 0.0
            h, w = shape[:2]
            if str(location).strip().lower() in ("top", "bottom"):
                coords = [int(m.get("cx", 0)) for m in markers]
                denom = max(1.0, float(w - 1))
            else:
                coords = [int(m.get("cy", 0)) for m in markers]
                denom = max(1.0, float(h - 1))
            span = float(max(coords) - min(coords)) if coords else 0.0
            return span / denom

        def _marker_quality(markers):
            if not markers:
                return 0.0
            mean_solidity = float(np.mean([float(m.get("solidity", 0.0)) for m in markers]))
            mean_fill = float(np.mean([float(m.get("fill_ratio", 0.0)) for m in markers]))
            mean_ring = float(np.mean([float(m.get("ring_ratio", 1.0)) for m in markers]))
            # higher is better
            return (mean_solidity * 0.45) + (mean_fill * 0.45) + ((1.0 - mean_ring) * 0.10)

        # Evaluate expected-side markers directly at each quarter turn.
        trials = []
        side_counts_0 = {
            "left": len(self.find_markers(image, location="left", min_count=min_count)),
            "right": len(self.find_markers(image, location="right", min_count=min_count)),
            "top": len(self.find_markers(image, location="top", min_count=min_count)),
            "bottom": len(self.find_markers(image, location="bottom", min_count=min_count)),
        }
        logger.info(
            "[Orientation] target=%s min_count=%d side_counts_0=%s",
            target_loc,
            int(min_count),
            side_counts_0,
        )

        for k in (0, 1, 2, 3):
            rotated = _rotate_quarter_turns(image, k)
            markers = self.find_markers(rotated, location=target_loc, min_count=min_count)
            count = len(markers)
            span_ratio = _marker_span_ratio(markers, target_loc, rotated.shape)
            quality = _marker_quality(markers)
            # Count dominates, span/quality break ties.
            score = (count * 1000.0) + (quality * 10.0) + span_ratio
            trials.append(
                {
                    "k": int(k),
                    "img": rotated,
                    "markers": markers,
                    "count": int(count),
                    "span_ratio": float(span_ratio),
                    "quality": float(quality),
                    "score": float(score),
                }
            )

        # Tie-break priority for deterministic, stable selection.
        k_priority = {0: 0, 1: 1, 3: 2, 2: 3}
        best = max(
            trials,
            key=lambda t: (
                t["score"],
                -k_priority.get(int(t["k"]), 9),
            ),
        )
        base = next((t for t in trials if t["k"] == 0), trials[0])

        # Stability guard:
        # if current orientation already has enough markers, rotate only when evidence is clearly better.
        if base["count"] >= int(max(1, min_count)) and best["k"] != 0:
            required_count = max(
                int(base["count"]) + 2,
                int(np.ceil(float(base["count"]) * 1.40)),
            )
            if int(best["count"]) < required_count:
                best = base

        # Weak-evidence guard:
        # when both are low-confidence, avoid unnecessary quarter-turn flips.
        if int(base["count"]) > 0 and best["k"] != 0:
            if int(best["count"]) <= int(base["count"]) + 1:
                if float(best["span_ratio"]) <= float(base["span_ratio"]) + 0.05:
                    if float(best.get("quality", 0.0)) <= float(base.get("quality", 0.0)) + 0.03:
                        best = base

        logger.info(
            "[Orientation] selected_k_cw=%d target=%s count=%d span=%.3f quality=%.3f trials=%s",
            int(best["k"]),
            target_loc,
            int(best["count"]),
            float(best["span_ratio"]),
            float(best.get("quality", 0.0)),
            [(int(t["k"]), int(t["count"]), round(float(t.get("quality", 0.0)), 3)) for t in trials],
        )
        return best["img"], best["markers"]

    def ensure_gross_rotation(self, original_img):
        """
        [수정됨] 0도(원본) 우선 정책 적용
        - 0, 90, 180, 270도를 체크하되,
        - 0도에서 마커가 어느 정도(예: 8개 이상) 잡히면,
          다른 각도가 '압도적으로(1.3배)' 많지 않는 한 0도를 유지합니다.
        """
        if original_img is None:
            return None, 0, []

        # 속도를 위해 리사이즈 (가로 800px)
        small_img = original_img
        h0, w0 = original_img.shape[:2]
        scale_factor = 1.0
        if w0 > 800:
            scale_factor = 800.0 / float(w0)
            new_h = max(1, int(h0 * scale_factor))
            small_img = cv2.resize(original_img, (800, new_h), interpolation=cv2.INTER_AREA)

        # 1. 일단 0도(원본)부터 검사
        markers_0 = self.find_side_markers(small_img)
        count_0 = len(markers_0)

        best_img = small_img # 반환은 나중에 원본으로 교체
        best_k = 0
        best_markers = markers_0
        best_count = count_0

        # 0도에서 마커가 충분히 발견되었다면 방어적으로 동작
        # (예: 10개 이상 찾았으면, 다른 각도는 1.3배 이상이어야 교체)
        is_valid_0 = (count_0 >= 8) 
        threshold_multiplier = 1.3 if is_valid_0 else 1.0

        # 2. 나머지 각도(90, 180, 270) 검사
        rotations = [
            (1, cv2.ROTATE_90_CLOCKWISE),
            (2, cv2.ROTATE_180),
            (3, cv2.ROTATE_90_COUNTERCLOCKWISE),
        ]

        for k, rot in rotations:
            img = cv2.rotate(small_img, rot)
            markers = self.find_side_markers(img)
            count = len(markers)

            # [핵심] 단순 비교가 아니라 '가산점' 적용 비교
            if count > (best_count * threshold_multiplier):
                best_count = count
                best_k = k
                best_markers = markers
                # 새로운 베스트가 발견되면, 기준점이 높아졌으므로 멀티플라이어는 초기화하거나 유지
                # 여기서는 단순히 갱신만 함 (더 좋은게 나오면 바꿈)
        
        # 3. 최종 결정된 k에 맞춰 원본 이미지 회전 반환
        if best_k == 0:
            final_img = original_img
            # 0도일 때는 small_img에서 찾은 마커 좌표를 원본 스케일로 복원해야 함
            if scale_factor != 1.0:
                restored_markers = []
                for m in best_markers:
                    restored_markers.append({
                        "cx": int(m["cx"] / scale_factor),
                        "cy": int(m["cy"] / scale_factor),
                        "x": int(m["x"] / scale_factor)
                    })
                best_markers = restored_markers
            else:
                best_markers = best_markers

        elif best_k == 1:
            final_img = cv2.rotate(original_img, cv2.ROTATE_90_CLOCKWISE)
            # 회전된 상태에서는 좌표계가 바뀌므로 마커를 다시 찾는 게 가장 안전하고 정확함
            best_markers = self.find_side_markers(final_img)
        elif best_k == 2:
            final_img = cv2.rotate(original_img, cv2.ROTATE_180)
            best_markers = self.find_side_markers(final_img)
        else:
            final_img = cv2.rotate(original_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            best_markers = self.find_side_markers(final_img)

        return final_img, best_k, best_markers

    def ensure_correct_orientation(self, image, expected_location="left", min_keep=3, prefer_multiplier=1.3):
        """
        expected_location 기준으로 0/90/180/270 회전 중
        가장 마커가 잘 검출되는 방향을 선택
        """
        if image is None:
            return None, []

        expected = str(expected_location).strip().lower()
        markers_0 = self.find_markers(image, location=expected)
        best_img = image
        best_markers = markers_0
        best_count = len(markers_0)

        threshold = best_count * prefer_multiplier if best_count >= min_keep else best_count

        rotations = [
            (1, cv2.ROTATE_90_CLOCKWISE),
            (2, cv2.ROTATE_180),
            (3, cv2.ROTATE_90_COUNTERCLOCKWISE),
        ]

        for _, rot in rotations:
            rotated = cv2.rotate(image, rot)
            markers = self.find_markers(rotated, location=expected)
            count = len(markers)
            if best_count >= min_keep and count <= threshold:
                continue
            if count > best_count:
                best_count = count
                best_markers = markers
                best_img = rotated

        return best_img, best_markers

    def _interpolate_missing_marks(self, markers):
        if not markers or len(markers) < 2:
            return markers
        markers_sorted = sorted(markers, key=lambda m: m["cy"])
        ys = [m["cy"] for m in markers_sorted]
        gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        if not gaps:
            return markers_sorted
        median_gap = float(np.median(gaps))
        if median_gap <= 0:
            return markers_sorted

        new_marks = []
        for i in range(len(markers_sorted) - 1):
            cur_m = markers_sorted[i]
            next_m = markers_sorted[i + 1]
            new_marks.append(cur_m)
            gap = next_m["cy"] - cur_m["cy"]
            if gap >= 1.8 * median_gap:
                insert_count = int(round(gap / median_gap)) - 1
                insert_count = max(1, insert_count)
                for j in range(insert_count):
                    t = (j + 1) / float(insert_count + 1)
                    cx = int(round(cur_m["cx"] + (next_m["cx"] - cur_m["cx"]) * t))
                    cy = int(round(cur_m["cy"] + (next_m["cy"] - cur_m["cy"]) * t))
                    new_marks.append({"cx": cx, "cy": cy, "interpolated": True})
        new_marks.append(markers_sorted[-1])
        return sorted(new_marks, key=lambda m: m["cy"])

    def correct_rotation_by_markers(self, image, rows, xs_list):
        import numpy as np
        import cv2

        if image is None or rows is None or xs_list is None:
            return image

        h, w = image.shape[:2]
        if h < 2 or w < 2 or len(rows) < 2 or len(rows) != len(xs_list):
            return image

        # 1) Preprocess & Sort
        try:
            y = np.asarray(rows, dtype=np.float32).reshape(-1)
            x = np.asarray(xs_list, dtype=np.float32).reshape(-1)
            valid = np.isfinite(x) & np.isfinite(y)
            x, y = x[valid], y[valid]
        except Exception:
            return image

        if len(x) < 2: return image

        order = np.argsort(y)
        x, y = x[order], y[order]

        # 2) Helper function
        def fit_line_fn(points):
            vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
            return float(vx), float(vy), float(x0), float(y0)

        pts = np.stack([x, y], axis=1).astype(np.float32).reshape(-1, 1, 2)

        try:
            # 3) First fit
            vx, vy, x0, y0 = fit_line_fn(pts)
            if abs(vy) < 1e-6: return image # 수평선이면 패스

            # 4) Outlier Removal (Distance normalization)
            n0, n1 = -vy, vx
            denom = (n0**2 + n1**2)**0.5 + 1e-9
            d = np.abs((pts[:, 0, 0] - x0) * n0 + (pts[:, 0, 1] - y0) * n1) / denom

            if len(d) > 5:
                keep_thr = np.percentile(d, 85.0)
                inliers = pts[d <= keep_thr]
                if len(inliers) >= 2:
                    # [수정] 재피팅 수행
                    vx, vy, x0, y0 = fit_line_fn(inliers)
                    # [중요] 재피팅 후에도 수직/수평 체크 필수 (Division by zero 방지)
                    if abs(vy) < 1e-6: return image

            # 5) Angle Calculation
            angle_deg = float(np.degrees(np.arctan2(vy, vx)))
            rotate_deg = 90.0 - angle_deg

            # Normalize [-90, 90]
            if rotate_deg > 90.0:
                rotate_deg -= 180.0
            elif rotate_deg < -90.0:
                rotate_deg += 180.0

            # 6) Safety Guards
            # 스캐너가 12도 이상 삐뚤어질 일은 없음 -> 노이즈로 판단
            if abs(rotate_deg) > 12.0:
                return image
            # 너무 미세한 각도는 보간 화질 저하를 막기 위해 스킵
            if abs(rotate_deg) < 0.05:
                return image

            # 7) Pivot Calculation (Median Y Strategy)
            # 중앙값(Median)을 사용하여 이상치에 의한 회전축 쏠림 방지
            pivot_y = float(np.median(y))
            pivot_y = float(np.clip(pivot_y, 0.0, float(h - 1)))
            
            # 직선 방정식: x = x0 + (y - y0) * (vx/vy)
            k = float(vx / vy) 
            pivot_x = float(x0 + (pivot_y - y0) * k)
            
            # Pivot Clamp
            pivot_x = float(np.clip(pivot_x, 0.0, float(w - 1)))
            center = (pivot_x, pivot_y)

            # 8) Warp
            M = cv2.getRotationMatrix2D(center, rotate_deg, 1.0)
            corrected = cv2.warpAffine(
                image, 
                M, 
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255)
            )
            return corrected

        except Exception as e:
            # print(f"[WARN] Rotation Failed: {e}")
            return image

    def _fit_marker_line(self, rows, xs_list):
        try:
            rows_arr = np.asarray(rows, dtype=np.float32)
            xs_arr = np.asarray(xs_list, dtype=np.float32)
            valid = np.isfinite(rows_arr) & np.isfinite(xs_arr)
            rows_arr = rows_arr[valid]
            xs_arr = xs_arr[valid]
        except Exception:
            return None

        if len(rows_arr) < 2:
            return None

        order = np.argsort(rows_arr)
        rows_arr = rows_arr[order]
        xs_arr = xs_arr[order]

        try:
            slope, intercept = np.polyfit(rows_arr, xs_arr, 1)
            preds = slope * rows_arr + intercept
            residuals = xs_arr - preds
            rms = float(np.sqrt(np.mean(residuals ** 2))) if len(residuals) > 0 else 0.0
        except Exception:
            return None

        return {
            "rows": rows_arr,
            "xs": xs_arr,
            "slope": float(slope),
            "intercept": float(intercept),
            "rms": rms,
            "count": int(len(rows_arr)),
        }

    # =========================================================
    # [NEW] 타이밍 마크 검출/정렬 (Pipeline에서 이관됨)
    # =========================================================
    def find_timing_marks(self, image, left_ratio=0.08):
        """
        타이밍 마크(좌측 정렬 마커) 검출
        return: (rows, anchor_x, xs_list)
        """
        if image is None:
            return [], 0, []

        H, W = image.shape[:2]
        left_limit = int(W * float(left_ratio))

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, int(self.marker_thresh), 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

        candidates = []
        min_area = W * H * 0.0001
        max_area = W * H * 0.01

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            if x > left_limit:
                continue

            ratio = float(w) / h if h > 0 else 0
            if not (0.6 <= ratio <= 1.6):
                continue

            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area == 0:
                continue
            solidity = float(area) / hull_area
            if solidity < 0.85:
                continue

            candidates.append({"cx": x + w // 2, "cy": y + h // 2})

        if not candidates:
            return [], 0, []

        candidates.sort(key=lambda c: c["cy"])
        rows = [c["cy"] for c in candidates]
        xs_list = [c["cx"] for c in candidates]
        anchor_x = int(np.median(xs_list)) if xs_list else 0
        return rows, anchor_x, xs_list

    def find_timing_marks_aligned(self, image, left_ratio=0.08):
        """
        타이밍 마크 기준으로 미세 회전 보정까지 수행한 결과 반환
        return: (aligned_img, rows, anchor_x, xs_list)
        """
        if image is None:
            return None, [], 0, []

        rows, anchor_x, xs_list = self.find_timing_marks(image, left_ratio=left_ratio)
        if len(xs_list) >= 2 and abs(xs_list[-1] - xs_list[0]) > 1:
            corrected = self.correct_rotation_by_markers(image, rows, xs_list)
            if corrected is not None:
                image = corrected
            rows, anchor_x, xs_list = self.find_timing_marks(image, left_ratio=left_ratio)

        return image, rows, anchor_x, xs_list

    def read_answers(
        self,
        image,
        rows,
        anchor_x=0,
        x_offset_ratio=0.3,
        box_w_ratio=0.04,
        box_h_ratio=0.02,
        pixel_threshold=None,
    ):
        """
        타이밍 마크 기반 단일 마킹 판독
        return: (marks, debug_img)
        """
        if image is None:
            return [], None

        work_img, processed_img = self._preprocess_image(image)
        debug_img = work_img.copy() if work_img is not None else None

        if processed_img is None or not rows:
            return [], debug_img

        if pixel_threshold is None:
            pixel_threshold = self.pixel_threshold

        H, W = processed_img.shape[:2]
        box_w = max(1, int(W * float(box_w_ratio)))
        box_h = max(1, int(H * float(box_h_ratio)))
        x_offset = int(W * float(x_offset_ratio))

        marks = []
        for row_y in rows:
            rx = int(anchor_x + x_offset)
            ry = int(row_y - (box_h // 2))

            c = self._clamp_roi(processed_img, rx, ry, box_w, box_h)
            if c is None:
                marks.append(False)
                continue

            x, y, w, h = c
            roi = processed_img[y:y + h, x:x + w]
            ratio = cv2.countNonZero(roi) / (w * h) if w * h > 0 else 0.0
            is_marked = ratio > float(pixel_threshold)
            marks.append(is_marked)

            if debug_img is not None:
                color = (0, 255, 0) if is_marked else (0, 0, 255)
                cv2.rectangle(debug_img, (x, y), (x + w, y + h), color, 1)

        return marks, debug_img



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
    def analyze_side_marker_sheet(self, original_img, questions, params, scale=1.0, marker_location="left"):
        """
        :param scale: 300dpi 좌표를 150dpi 이미지에 맞추기 위한 비율 (0.5 등)
        """
        if original_img is None: return "ERROR", [], None, "IMG_NONE"

        # Orientation/axis estimation should stay permissive.
        # Requiring 4 markers caused frequent wrong rotations when 1 marker was faint.
        min_marker_count = 3
        logger.info(
            "[SideMarker] start marker_location=%s questions=%d min_marker_count=%d",
            str(marker_location),
            len(questions) if questions else 0,
            int(min_marker_count),
        )
        rotated_img, markers = self.normalize_orientation(
            original_img,
            expected_location=marker_location,
            min_count=min_marker_count,
        )
        if rotated_img is None:
            return "ERR", [], None, "IMG_NONE"

        base_img = rotated_img

        # Fine-tuning (skew correction) using markers
        markers = self.find_markers(base_img, location=marker_location, min_count=min_marker_count)
        logger.info("[SideMarker] markers_after_normalize=%d", len(markers))
        if markers and len(markers) >= 5:
            if str(marker_location).strip().lower() in ("top", "bottom"):
                rows = [m["cx"] for m in markers]
                xs_list = [m["cy"] for m in markers]
            else:
                rows = [m["cy"] for m in markers]
                xs_list = [m["cx"] for m in markers]

            corrected = self.correct_rotation_by_markers(base_img, rows, xs_list)
            if corrected is not None:
                base_img = corrected
                markers = self.find_markers(base_img, location=marker_location, min_count=min_marker_count)
                logger.info("[SideMarker] markers_after_skew_fix=%d", len(markers))

        work_img, processed_img = self._preprocess_image(base_img)
        debug_img = work_img.copy()

        markers = self._interpolate_missing_marks(markers)
        logger.info("[SideMarker] markers_after_interpolate=%d required=%d", len(markers), len(questions))

        if len(markers) < len(questions):
            # 디버깅을 위해 찾은 마커라도 표시
            for m in markers:
                cv2.circle(debug_img, (m['cx'], m['cy']), 5, (0, 0, 255), -1)
            logger.warning(
                "[SideMarker] timing_mark_fail markers=%d required=%d marker_location=%s",
                len(markers),
                len(questions),
                str(marker_location),
            )
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

        # Auto-scale based on current image width vs baseline width
        img_h, img_w = work_img.shape[:2]
        width_ratio = (float(img_w) / float(self.width)) if self.width > 0 else 1.0
        if width_ratio < 0.90:
            width_ratio = 0.90
        elif width_ratio > 3.0:
            width_ratio = 3.0

        sheet_results = []
        has_error = False
        error_reason = ""

        # Build mapping: row_index or y matching
        if str(marker_location).strip().lower() in ("top", "bottom"):
            marks_by_axis = sorted(markers, key=lambda m: m["cx"])
        else:
            marks_by_axis = sorted(markers, key=lambda m: m["cy"])

        for i, q in enumerate(questions):
            q_num = q.get("no", i + 1)
            row_index = q.get("row_index")
            q_y = q.get("y")

            if row_index is None:
                row_index = i

            if row_index is not None and 0 <= int(row_index) < len(marks_by_axis):
                base_mark = marks_by_axis[int(row_index)]
            elif q_y is not None:
                base_mark = min(marks_by_axis, key=lambda m: abs(m.get("cy", 0) - int(q_y)))
            else:
                if i >= len(marks_by_axis):
                    sheet_results.append({"q_num": q_num, "marked": [], "status": "마커없음"})
                    has_error = True
                    continue
                base_mark = marks_by_axis[i]

            base_cx = base_mark['cx']
            base_cy = base_mark['cy']
            start_y = base_cy - (box_h // 2) + self.global_offset_y

            # 찬성(0), 반대(1) 좌표 생성
            rois = [
                (
                    base_cx + int(dist_agree * width_ratio) + self.global_offset_x,
                    start_y,
                    int(box_w * width_ratio),
                    box_h,
                ),
                (
                    base_cx + int(dist_disagree * width_ratio) + self.global_offset_x,
                    start_y,
                    int(box_w * width_ratio),
                    box_h,
                ),
            ]

            marked_indices = []
            for r_idx, (rx, ry, rw, rh) in enumerate(rois):
                # 디버깅용: 검색 영역 박스 그리기 (파란색) - 실제 좌표가 어디 찍히는지 확인용
                cv2.rectangle(debug_img, (rx, ry), (rx+rw, ry+rh), (255, 0, 0), 1)

                if self._check_roi(processed_img, rx, ry, rw, rh, debug_img, (0, 255, 0)):
                    marked_indices.append(r_idx)
            logger.debug(
                "[SideMarker][Q%d] base=(%d,%d) rois=%s marked=%s",
                int(q_num),
                int(base_cx),
                int(base_cy),
                rois,
                marked_indices,
            )

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

    # =========================================================
    # [NEW] 3. 커스텀 필드 판독 (신규 폼 스키마)
    # =========================================================
    def analyze_custom_fields(self, original_img, fields, scale=1.0):
        if original_img is None or not fields:
            return False, {}, None

        work_img, processed_img = self._preprocess_image(original_img)
        debug_img = np.zeros_like(work_img) if work_img is not None else None

        info = {}
        is_ok = True

        for field in fields:
            if not isinstance(field, dict):
                continue
            f_name = field.get("name")
            f_type = str(field.get("type", "")).strip().lower()
            if not f_name or not f_type:
                continue

            if f_type == "grid":
                cfg = {
                    "digits": field.get("digits"),
                    "grid": field.get("grid", {}),
                }
                ok, val = self._decode_digit_grid(processed_img, cfg, scale, debug_img)
                if ok:
                    info[f_name] = val
                else:
                    is_ok = False
            elif f_type == "single_choice":
                cfg = {"choices": field.get("choices", [])}
                ok, val = self._decode_single_choice(processed_img, cfg, scale, debug_img)
                if ok:
                    info[f_name] = val
                else:
                    is_ok = False

        return is_ok, info, debug_img

    # =========================================================
    # [NEW] 4. 마커 기반 객관식 판독 (신규 폼 스키마)
    # =========================================================
    def analyze_marker_questions(self, original_img, questions, layout, scale=1.0, marker_location="left"):
        if original_img is None:
            return "ERR", [], None, "IMG_NONE"

        # Orientation/axis estimation should stay permissive.
        # Requiring 4 markers caused frequent wrong rotations when 1 marker was faint.
        min_marker_count = 3
        logger.info(
            "[MarkerQ] start marker_location=%s questions=%d min_marker_count=%d",
            str(marker_location),
            len(questions) if questions else 0,
            int(min_marker_count),
        )
        rotated_img, markers = self.normalize_orientation(
            original_img,
            expected_location=marker_location,
            min_count=min_marker_count,
        )
        if rotated_img is None:
            return "ERR", [], None, "IMG_NONE"

        work_img, processed_img = self._preprocess_image(rotated_img)
        debug_img = work_img.copy() if work_img is not None else None

        markers = self._interpolate_missing_marks(markers)
        logger.info("[MarkerQ] markers_after_interpolate=%d", len(markers))
        if not questions or not markers:
            logger.warning(
                "[MarkerQ] timing_mark_fail questions=%d markers=%d marker_location=%s",
                len(questions) if questions else 0,
                len(markers) if markers else 0,
                str(marker_location),
            )
            return "ERR", [], debug_img, "TIMING_MARK"

        x_offset = int(float(layout.get("x_offset", 600)) * scale)
        choice_dx = int(float(layout.get("choice_dx", 70)) * scale)
        box_w = int(float(layout.get("box_w", 40)) * scale)
        box_h = int(float(layout.get("box_h", 40)) * scale)
        row_offset_y = int(float(layout.get("row_offset_y", 0)) * scale)
        row_start_y = int(float(layout.get("row_start_y", 360)) * scale)
        row_dy = int(float(layout.get("row_dy", 70)) * scale)
        rows_per_col = int(layout.get("rows_per_col", 40))

        sheet_results = []
        has_error = False
        error_reason = ""

        marks_by_y = sorted(markers, key=lambda m: m["cy"])
        marks_by_x = sorted(markers, key=lambda m: m["cx"])
        is_horizontal = str(marker_location).strip().lower() in ("top", "bottom")

        if is_horizontal and rows_per_col <= 0:
            return "ERR", [], debug_img, "LAYOUT"

        for i, q in enumerate(questions):
            q_num = q.get("no", i + 1)
            row_index = q.get("row_index")
            q_y = q.get("y")
            choices_count = int(q.get("choices", 5))

            if is_horizontal:
                col_index = q.get("col_index")
                row_in_col = q.get("row_in_col")
                if col_index is None or row_in_col is None:
                    idx = int(q_num) - 1
                    col_index = idx // rows_per_col
                    row_in_col = idx % rows_per_col

                if not (0 <= int(col_index) < len(marks_by_x)):
                    return "ERR", [], debug_img, "TIMING_MARK"

                base_mark = marks_by_x[int(col_index)]
                base_cx = base_mark["cx"]
                base_cy = row_start_y + (int(row_in_col) * row_dy)
                start_y = base_cy - (box_h // 2) + self.global_offset_y + row_offset_y
            else:
                if row_index is not None and 0 <= int(row_index) < len(marks_by_y):
                    base_mark = marks_by_y[int(row_index)]
                elif q_y is not None:
                    base_mark = min(marks_by_y, key=lambda m: abs(m["cy"] - int(q_y)))
                else:
                    base_mark = marks_by_y[i]

                base_cx = base_mark["cx"]
                base_cy = base_mark["cy"]
                start_y = base_cy - (box_h // 2) + self.global_offset_y + row_offset_y

            rois = []
            for c in range(choices_count):
                rx = base_cx + x_offset + (c * choice_dx) + self.global_offset_x
                rois.append((rx, start_y, box_w, box_h))

            marked_indices = []
            for r_idx, (rx, ry, rw, rh) in enumerate(rois):
                if self._check_roi(processed_img, rx, ry, rw, rh, debug_img, (0, 255, 0)):
                    marked_indices.append(r_idx)
            logger.debug(
                "[MarkerQ][Q%d] base=(%d,%d) rois=%s marked=%s",
                int(q_num),
                int(base_cx),
                int(base_cy),
                rois,
                marked_indices,
            )

            status = self._determine_status(marked_indices)
            if status != "정상":
                has_error = True
                if not error_reason:
                    error_reason = status

            sheet_results.append({"q_num": q_num, "marked": marked_indices, "status": status})
            if status != "정상":
                self._draw_error_box(debug_img, rois)

        return ("ERR" if has_error else "OK"), sheet_results, debug_img, error_reason

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
