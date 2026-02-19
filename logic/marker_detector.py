from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from logic.omr_types import Marker

logger = logging.getLogger(__name__)

class MarkerDetector:
    def __init__(self, marker_thresh: int = 215):
        self.marker_thresh = int(marker_thresh)

    def configure(self, marker_thresh: Optional[int] = None) -> None:
        if marker_thresh is not None:
            self.marker_thresh = int(marker_thresh)

    @staticmethod
    def _roi_from_location(img_h: int, img_w: int, location: str, ratio: float) -> Tuple[int, int, int, int]:
        if location == "right":
            x0 = int(img_w * (1.0 - ratio))
            return x0, 0, img_w - x0, img_h
        if location == "top":
            return 0, 0, img_w, int(img_h * ratio)
        if location == "bottom":
            y0 = int(img_h * (1.0 - ratio))
            return 0, y0, img_w, img_h - y0
        return 0, 0, int(img_w * ratio), img_h

    @staticmethod
    def _required_span_ratio(group_len: int) -> float:
        if group_len <= 4:
            return 0.20
        if group_len <= 6:
            return 0.24
        return 0.30

    @staticmethod
    def _cluster_candidates(cands: Sequence[Marker], axis_key: str) -> List[List[Marker]]:
        if not cands:
            return []
        ordered = sorted(cands, key=lambda c: int(getattr(c, axis_key, 0)))
        axis_sizes = [int(getattr(c, "w", 1)) if axis_key == "x" else int(getattr(c, "h", 1)) for c in ordered]
        median_size = float(np.median(np.asarray(axis_sizes, dtype=np.float32))) if axis_sizes else 1.0
        gap_thr = max(12, int(round(median_size * 0.9)))
        groups: List[List[Marker]] = []
        cur = [ordered[0]]
        for i in range(1, len(ordered)):
            prev = int(getattr(ordered[i - 1], axis_key, 0))
            now = int(getattr(ordered[i], axis_key, 0))
            if abs(now - prev) <= gap_thr:
                cur.append(ordered[i])
            else:
                groups.append(cur)
                cur = [ordered[i]]
        groups.append(cur)
        return groups

    @staticmethod
    def _is_uniform_group(group: Sequence[Marker], size_std_max: float) -> bool:
        if not group:
            return False
        if len(group) == 1:
            return True
        ws = np.asarray([max(1, int(g.w)) for g in group], dtype=np.float32)
        hs = np.asarray([max(1, int(g.h)) for g in group], dtype=np.float32)
        mean_w = float(np.mean(ws))
        mean_h = float(np.mean(hs))
        if mean_w <= 0 or mean_h <= 0:
            return False
        rel_std_w = float(np.std(ws)) / mean_w
        rel_std_h = float(np.std(hs)) / mean_h
        return (rel_std_w <= size_std_max) and (rel_std_h <= size_std_max)

    @staticmethod
    def _validate_axis_spacing(group: Sequence[Marker], axis_key: str) -> bool:
        if not group or len(group) < 3:
            return bool(group)
        coords = sorted([int(getattr(m, axis_key, 0)) for m in group])
        gaps = np.diff(np.asarray(coords, dtype=np.float32))
        if gaps.size == 0:
            return False
        median_gap = float(np.median(gaps))
        if median_gap <= 1e-6:
            return False
        rel_std_gap = float(np.std(gaps)) / median_gap
        return rel_std_gap <= 0.30

    @staticmethod
    def _fallback_horizontal_candidates(cands: Sequence[Marker], location: str) -> List[Marker]:
        if not cands:
            return []

        ordered = sorted(cands, key=lambda m: int(m.cx))
        ws = np.asarray([max(1, int(m.w)) for m in ordered], dtype=np.float32)
        gap_thr = max(6, int(round(float(np.median(ws)) * 0.8))) if ws.size > 0 else 8

        grouped: List[List[Marker]] = [[ordered[0]]]
        for m in ordered[1:]:
            if abs(int(m.cx) - int(grouped[-1][-1].cx)) <= gap_thr:
                grouped[-1].append(m)
            else:
                grouped.append([m])

        # Keep one marker per x-cluster: closest to top/bottom edge depending on location.
        reduced: List[Marker] = []
        for g in grouped:
            pick = min(g, key=lambda m: int(m.cy)) if location == "top" else max(g, key=lambda m: int(m.cy))
            reduced.append(pick)

        if len(reduced) <= 2:
            return sorted(reduced, key=lambda m: int(m.cx))

        # Remove very-close duplicates based on global x-gap statistics.
        reduced = sorted(reduced, key=lambda m: int(m.cx))
        xs = np.asarray([int(m.cx) for m in reduced], dtype=np.float32)
        gaps = np.diff(xs)
        if gaps.size == 0:
            return reduced
        median_gap = float(np.median(gaps))
        dedup_gap = max(4, int(round(median_gap * 0.45)))
        deduped: List[Marker] = [reduced[0]]
        for m in reduced[1:]:
            if (int(m.cx) - int(deduped[-1].cx)) >= dedup_gap:
                deduped.append(m)
            else:
                # Same-x candidate: keep edge-nearer one.
                keep_new = (int(m.cy) < int(deduped[-1].cy)) if location == "top" else (int(m.cy) > int(deduped[-1].cy))
                if keep_new:
                    deduped[-1] = m

        return deduped

    def _detect_in_roi(self, image: np.ndarray, location: str, ratio: float) -> List[Marker]:
        solidity_min = 0.90
        fill_ratio_min = 0.70
        size_std_max = 0.20
        extent_min = 0.55
        aspect_min = 0.45
        aspect_max = 2.20
        rect_fill_min = 0.65
        ring_ratio_max = 0.18

        img_h, img_w = image.shape[:2]
        rx, ry, rw, rh = self._roi_from_location(img_h, img_w, location, ratio)
        if rw <= 0 or rh <= 0:
            return []
        roi_img = image[ry : ry + rh, rx : rx + rw]
        gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, int(self.marker_thresh), 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

        roi_area = float(max(1, rw * rh))
        min_area = roi_area * 0.0001
        max_area = roi_area * 0.012
        markers: List[Marker] = []

        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < min_area or area > max_area:
                continue

            lx, ly, w, h = cv2.boundingRect(cnt)
            if w <= 1 or h <= 1:
                continue
            if lx <= 0 or ly <= 0 or (lx + w) >= rw - 1 or (ly + h) >= rh - 1:
                continue

            ratio_wh = float(w) / float(h)
            if ratio_wh < aspect_min or ratio_wh > aspect_max:
                continue

            hull = cv2.convexHull(cnt)
            hull_area = float(cv2.contourArea(hull))
            if hull_area <= 1e-6:
                continue
            solidity = area / hull_area
            if solidity < solidity_min:
                continue

            bbox_area = float(max(1, w * h))
            extent = area / bbox_area
            if extent < extent_min:
                continue

            rect = cv2.minAreaRect(cnt)
            rw_rect, rh_rect = rect[1]
            rect_area = float(rw_rect * rh_rect)
            if rect_area <= 1e-6:
                continue
            rect_fill = area / rect_area
            if rect_fill < rect_fill_min:
                continue

            box = binary[ly : ly + h, lx : lx + w]
            if box is None or box.size == 0:
                continue
            fill_ratio = float(cv2.countNonZero(box)) / float(box.size)
            if fill_ratio < fill_ratio_min:
                continue

            pad = max(2, int(round(0.35 * float(max(w, h)))))
            ex1 = max(0, lx - pad)
            ey1 = max(0, ly - pad)
            ex2 = min(rw, lx + w + pad)
            ey2 = min(rh, ly + h + pad)
            expanded = binary[ey1:ey2, ex1:ex2]
            if expanded is None or expanded.size == 0:
                continue
            outer_nonzero = int(cv2.countNonZero(expanded))
            inner_nonzero = int(cv2.countNonZero(box))
            ring_area = int(expanded.size - box.size)
            ring_nonzero = max(0, outer_nonzero - inner_nonzero)
            ring_ratio = (float(ring_nonzero) / float(ring_area)) if ring_area > 0 else 1.0
            if ring_ratio > ring_ratio_max:
                continue

            x = lx + rx
            y = ly + ry
            markers.append(
                Marker(
                    cx=int(x + (w // 2)),
                    cy=int(y + (h // 2)),
                    x=int(x),
                    y=int(y),
                    w=int(w),
                    h=int(h),
                    solidity=float(solidity),
                    fill_ratio=float(fill_ratio),
                    ring_ratio=float(ring_ratio),
                )
            )

        groups = self._cluster_candidates(markers, axis_key=("y" if location in ("top", "bottom") else "x"))
        groups = [g for g in groups if len(g) >= 3]
        groups = [g for g in groups if self._is_uniform_group(g, size_std_max)]
        if not groups:
            return []

        if location in ("top", "bottom"):
            primary_key = "y"
            span_key = "cx"
            span_limit = float(image.shape[1]) * self._required_span_ratio(4)
            edge_ref = float(image.shape[0] - 1) if location == "bottom" else 0.0
            axis_den = float(max(1, image.shape[0] - 1))
            span_den = float(max(1, image.shape[1] - 1))
        else:
            primary_key = "x"
            span_key = "cy"
            span_limit = float(image.shape[0]) * self._required_span_ratio(4)
            edge_ref = float(image.shape[1] - 1) if location == "right" else 0.0
            axis_den = float(max(1, image.shape[1] - 1))
            span_den = float(max(1, image.shape[0] - 1))

        scored_groups: List[Tuple[float, List[Marker]]] = []
        for g in groups:
            span = float(max(int(getattr(c, span_key, 0)) for c in g) - min(int(getattr(c, span_key, 0)) for c in g))
            if span < span_limit:
                continue
            if not self._validate_axis_spacing(g, span_key):
                continue

            mean_ring = float(np.mean([float(c.ring_ratio) for c in g]))
            if mean_ring > 0.12:
                continue
            mean_solidity = float(np.mean([float(c.solidity) for c in g]))
            mean_fill = float(np.mean([float(c.fill_ratio) for c in g]))
            axis_med = float(np.median([int(getattr(c, primary_key, 0)) for c in g]))
            edge_distance = abs(axis_med - edge_ref) / max(1.0, axis_den)
            span_ratio = span / max(1.0, span_den)
            score = (len(g) * 1000.0) + (span_ratio * 25.0) + (mean_solidity * 8.0) + (mean_fill * 8.0) - (edge_distance * 30.0)
            scored_groups.append((float(score), g))

        if not scored_groups:
            if location in ("top", "bottom"):
                return self._fallback_horizontal_candidates(markers, location)
            return []

        best_group = max(scored_groups, key=lambda it: float(it[0]))[1]
        if location in ("top", "bottom"):
            fallback = self._fallback_horizontal_candidates(markers, location)
            if len(fallback) >= max(6, len(best_group) + 2):
                return sorted(fallback, key=lambda m: int(m.cx))
            return sorted(best_group, key=lambda m: int(m.cx))
        return sorted(best_group, key=lambda m: int(m.cy))

    def find_markers(self, image: Optional[np.ndarray], location: str = "left", min_count: int = 3) -> List[Marker]:
        if image is None:
            return []
        loc = str(location or "left").strip().lower()
        if loc not in ("left", "right", "top", "bottom"):
            loc = "left"

        try:
            candidates: List[Marker] = []
            ratio_candidates = (0.07, 0.09, 0.11, 0.13) if loc in ("top", "bottom") else (0.10, 0.15, 0.20)
            for ratio in ratio_candidates:
                candidates = self._detect_in_roi(image, loc, ratio)
                if len(candidates) >= int(min_count):
                    break
            return candidates if len(candidates) >= int(min_count) else []
        except Exception as exc:
            logger.exception("[MarkerDetect] exception: %s", exc)
            return []

    def normalize_orientation(
        self,
        image: Optional[np.ndarray],
        expected_location: str = "left",
        min_count: int = 3,
    ) -> Tuple[Optional[np.ndarray], List[Marker]]:
        if image is None:
            return None, []

        target_loc = str(expected_location or "left").strip().lower()
        if target_loc not in ("left", "right", "top", "bottom"):
            target_loc = "left"

        def _rotate(src: np.ndarray, k_cw: int) -> np.ndarray:
            k = int(k_cw) % 4
            if k == 0:
                return src
            if k == 1:
                return cv2.rotate(src, cv2.ROTATE_90_CLOCKWISE)
            if k == 2:
                return cv2.rotate(src, cv2.ROTATE_180)
            return cv2.rotate(src, cv2.ROTATE_90_COUNTERCLOCKWISE)

        def _span_ratio(markers: Sequence[Marker], location: str, shape: Tuple[int, int, int]) -> float:
            if not markers or len(markers) < 2:
                return 0.0
            h, w = shape[:2]
            if location in ("top", "bottom"):
                coords = [int(m.cx) for m in markers]
                denom = max(1.0, float(w - 1))
            else:
                coords = [int(m.cy) for m in markers]
                denom = max(1.0, float(h - 1))
            return float(max(coords) - min(coords)) / denom

        def _quality(markers: Sequence[Marker]) -> float:
            if not markers:
                return 0.0
            mean_solidity = float(np.mean([float(m.solidity) for m in markers]))
            mean_fill = float(np.mean([float(m.fill_ratio) for m in markers]))
            mean_ring = float(np.mean([float(m.ring_ratio) for m in markers]))
            return (mean_solidity * 0.45) + (mean_fill * 0.45) + ((1.0 - mean_ring) * 0.10)

        trials: List[Dict[str, Any]] = []
        prefer_rotation = target_loc in ("top", "bottom")
        for k in (0, 1, 2, 3):
            rotated = _rotate(image, k)
            markers = self.find_markers(rotated, location=target_loc, min_count=min_count)
            count = len(markers)
            span_ratio = _span_ratio(markers, target_loc, rotated.shape)
            quality = _quality(markers)
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

        k_priority = {0: 0, 1: 1, 3: 2, 2: 3}
        best = max(trials, key=lambda t: (t["score"], -k_priority.get(int(t["k"]), 9)))
        base = next((t for t in trials if t["k"] == 0), trials[0])
        if (not prefer_rotation) and base["count"] >= int(max(1, min_count)) and best["k"] != 0:
            required_count = max(int(base["count"]) + 2, int(np.ceil(float(base["count"]) * 1.40)))
            if int(best["count"]) < required_count:
                best = base
        if (not prefer_rotation) and int(base["count"]) > 0 and best["k"] != 0:
            if int(best["count"]) <= int(base["count"]) + 1:
                if float(best["span_ratio"]) <= float(base["span_ratio"]) + 0.05:
                    if float(best["quality"]) <= float(base["quality"]) + 0.03:
                        best = base
        return best["img"], list(best["markers"])

    def interpolate_missing_marks(self, markers: Sequence[Marker]) -> List[Marker]:
        if not markers or len(markers) < 2:
            return list(markers or [])

        xs = [int(m.cx) for m in markers]
        ys = [int(m.cy) for m in markers]
        span_x = (max(xs) - min(xs)) if xs else 0
        span_y = (max(ys) - min(ys)) if ys else 0
        is_horizontal = span_x >= span_y
        axis_key = "cx" if is_horizontal else "cy"
        sec_key = "cy" if is_horizontal else "cx"

        markers_sorted = sorted(markers, key=lambda m: int(getattr(m, axis_key)))
        coords = [int(getattr(m, axis_key)) for m in markers_sorted]
        gaps = [coords[i + 1] - coords[i] for i in range(len(coords) - 1)]
        if not gaps:
            return markers_sorted
        median_gap = float(np.median(gaps))
        if median_gap <= 0:
            return markers_sorted

        new_marks: List[Marker] = []
        for i in range(len(markers_sorted) - 1):
            cur = markers_sorted[i]
            nxt = markers_sorted[i + 1]
            new_marks.append(cur)
            gap = int(getattr(nxt, axis_key)) - int(getattr(cur, axis_key))
            if gap >= 1.8 * median_gap:
                insert_count = max(1, int(round(gap / median_gap)) - 1)
                for j in range(insert_count):
                    t = (j + 1) / float(insert_count + 1)
                    axis_v = int(round(int(getattr(cur, axis_key)) + (int(getattr(nxt, axis_key)) - int(getattr(cur, axis_key))) * t))
                    sec_v = int(round(int(getattr(cur, sec_key)) + (int(getattr(nxt, sec_key)) - int(getattr(cur, sec_key))) * t))
                    cx = axis_v if is_horizontal else sec_v
                    cy = sec_v if is_horizontal else axis_v
                    new_marks.append(Marker(cx=cx, cy=cy, interpolated=True))
        new_marks.append(markers_sorted[-1])
        return sorted(new_marks, key=lambda m: int(getattr(m, axis_key)))

    def sample_evenly(self, markers_sorted: Sequence[Marker], target_count: int, axis_key: str = "cx") -> List[Marker]:
        if not markers_sorted or int(target_count) <= 0:
            return []
        ordered = sorted(markers_sorted, key=lambda m: int(getattr(m, axis_key, 0)))
        n = len(ordered)
        target = int(target_count)
        if n <= target:
            return ordered
        if target == 1:
            return [ordered[n // 2]]

        raw_indices = np.linspace(0, n - 1, target)
        picked: List[Marker] = []
        used = set()
        for raw_idx in raw_indices:
            idx = int(round(float(raw_idx)))
            if idx in used:
                left = idx - 1
                right = idx + 1
                while left >= 0 or right < n:
                    if right < n and right not in used:
                        idx = right
                        break
                    if left >= 0 and left not in used:
                        idx = left
                        break
                    left -= 1
                    right += 1
            used.add(idx)
            picked.append(ordered[idx])
        return sorted(picked, key=lambda m: int(getattr(m, axis_key, 0)))



