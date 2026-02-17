from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from logic.geometry import GeometryManager
from logic.marker_detector import MarkerDetector
from logic.omr_types import Marker, QuestionResult

logger = logging.getLogger(__name__)

class ImageProcessor:
    def __init__(self, block_size: int = 15, c_value: int = 7):
        self.block_size = int(block_size) if int(block_size) % 2 == 1 else int(block_size) + 1
        self.c_value = int(c_value)

    def configure(self, block_size: Optional[int] = None, c_value: Optional[int] = None) -> None:
        if block_size is not None:
            b = int(block_size)
            if b % 2 == 0:
                b += 1
            self.block_size = max(3, b)
        if c_value is not None:
            self.c_value = int(c_value)

    def preprocess(self, img: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        if img is None:
            return None, None
        work_img = img.copy()

        if len(work_img.shape) == 2:
            img_gray = work_img
        else:
            try:
                _, _, r = cv2.split(work_img)
                img_gray = r
            except Exception:
                img_gray = cv2.cvtColor(work_img, cv2.COLOR_BGR2GRAY)

        binary_img = cv2.adaptiveThreshold(
            img_gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self.block_size,
            self.c_value,
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        processed_img = cv2.morphologyEx(binary_img, cv2.MORPH_OPEN, kernel, iterations=1)
        return work_img, processed_img

    def clamp_roi(self, image: Optional[np.ndarray], x: int, y: int, w: int, h: int) -> Optional[Tuple[int, int, int, int]]:
        if image is None or w <= 0 or h <= 0:
            return None
        img_h, img_w = image.shape[:2]
        x1 = max(0, int(x))
        y1 = max(0, int(y))
        x2 = min(int(img_w), int(x) + int(w))
        y2 = min(int(img_h), int(y) + int(h))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2 - x1, y2 - y1

    def roi_fill_ratio(
        self,
        processed_img: Optional[np.ndarray],
        x: int,
        y: int,
        w: int,
        h: int,
        inner_ratio: float = 0.18,
    ) -> Tuple[Optional[float], Optional[Tuple[int, int, int, int]]]:
        clamped = self.clamp_roi(processed_img, x, y, w, h)
        if clamped is None:
            return None, None
        rx, ry, rw, rh = clamped

        ratio = float(inner_ratio)
        if ratio > 0:
            mx = int(round(float(rw) * ratio))
            my = int(round(float(rh) * ratio))
            if (rw - (mx * 2)) >= 4 and (rh - (my * 2)) >= 4:
                rx += mx
                ry += my
                rw -= (mx * 2)
                rh -= (my * 2)

        roi = processed_img[ry : ry + rh, rx : rx + rw]
        if roi is None or roi.size == 0:
            return None, None
        area = float(rw * rh)
        if area <= 0.0:
            return None, None
        fill = float(cv2.countNonZero(roi)) / area
        return fill, (rx, ry, rw, rh)

    def check_roi(
        self,
        processed_img: Optional[np.ndarray],
        x: int,
        y: int,
        w: int,
        h: int,
        threshold: float,
    ) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]], Optional[Tuple[int, int, int, int]]]:
        clamped = self.clamp_roi(processed_img, x, y, w, h)
        if clamped is None:
            return False, 0.0, None, None
        ratio, eval_roi = self.roi_fill_ratio(processed_img, x, y, w, h)
        if ratio is None:
            return False, 0.0, clamped, eval_roi
        return bool(float(ratio) > float(threshold)), float(ratio), clamped, eval_roi



class OMRScanner:
    SECTION_KEYS: Tuple[str, ...] = ("exam_no", "birth", "name", "subject", "question")

    def __init__(
        self,
        image_processor: ImageProcessor,
        marker_detector: MarkerDetector,
        geometry_manager: GeometryManager,
        pixel_threshold: float = 0.05,
        global_offset_x: int = 0,
        global_offset_y: int = 0,
    ):
        self.image_processor = image_processor
        self.marker_detector = marker_detector
        self.geometry_manager = geometry_manager
        self.pixel_threshold = float(pixel_threshold)
        self.global_offset_x = int(global_offset_x)
        self.global_offset_y = int(global_offset_y)
        self.section_offsets: Dict[str, Dict[str, int]] = {
            key: {"x": 0, "y": 0} for key in self.SECTION_KEYS
        }
        self.section_scale_offsets: Dict[str, float] = {key: 0.0 for key in self.SECTION_KEYS}

    def configure(
        self,
        pixel_threshold: Optional[float] = None,
        global_offset_x: Optional[int] = None,
        global_offset_y: Optional[int] = None,
        exam_no_offset_x: Optional[int] = None,
        exam_no_offset_y: Optional[int] = None,
        birth_offset_x: Optional[int] = None,
        birth_offset_y: Optional[int] = None,
        name_offset_x: Optional[int] = None,
        name_offset_y: Optional[int] = None,
        subject_offset_x: Optional[int] = None,
        subject_offset_y: Optional[int] = None,
        question_offset_x: Optional[int] = None,
        question_offset_y: Optional[int] = None,
        exam_no_offset: Optional[float] = None,
        birth_offset: Optional[float] = None,
        name_offset: Optional[float] = None,
        subject_offset: Optional[float] = None,
        questions_offset: Optional[float] = None,
    ) -> None:
        if pixel_threshold is not None:
            self.pixel_threshold = float(pixel_threshold)
        if global_offset_x is not None:
            self.global_offset_x = int(global_offset_x)
        if global_offset_y is not None:
            self.global_offset_y = int(global_offset_y)
        partial_updates: Dict[str, Dict[str, Optional[int]]] = {
            "exam_no": {"x": exam_no_offset_x, "y": exam_no_offset_y},
            "birth": {"x": birth_offset_x, "y": birth_offset_y},
            "name": {"x": name_offset_x, "y": name_offset_y},
            "subject": {"x": subject_offset_x, "y": subject_offset_y},
            "question": {"x": question_offset_x, "y": question_offset_y},
        }
        for key, axis in partial_updates.items():
            slot = self.section_offsets.setdefault(key, {"x": 0, "y": 0})
            if axis["x"] is not None:
                slot["x"] = int(axis["x"])
            if axis["y"] is not None:
                slot["y"] = int(axis["y"])
        scale_updates: Dict[str, Optional[float]] = {
            "exam_no": exam_no_offset,
            "birth": birth_offset,
            "name": name_offset,
            "subject": subject_offset,
            "question": questions_offset,
        }
        for key, value in scale_updates.items():
            if value is None:
                continue
            try:
                parsed = float(value)
            except Exception:
                parsed = 0.0
            if not np.isfinite(parsed):
                parsed = 0.0
            self.section_scale_offsets[key] = float(parsed)

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "y", "on")
        return default

    @classmethod
    def _normalize_section_key(cls, section_key: str) -> str:
        key = str(section_key or "").strip().lower()
        if key in cls.SECTION_KEYS:
            return key
        return "question"

    def _section_offset(self, section_key: str) -> Tuple[int, int]:
        key = self._normalize_section_key(section_key)
        slot = self.section_offsets.get(key, {"x": 0, "y": 0})
        return int(slot.get("x", 0)), int(slot.get("y", 0))

    def _combined_offset(self, section_key: str) -> Tuple[int, int]:
        sx, sy = self._section_offset(section_key)
        return int(self.global_offset_x + sx), int(self.global_offset_y + sy)

    def _section_scale_delta(self, section_key: str) -> float:
        key = self._normalize_section_key(section_key)
        value = self.section_scale_offsets.get(key, 0.0)
        try:
            parsed = float(value)
        except Exception:
            parsed = 0.0
        if not np.isfinite(parsed):
            parsed = 0.0
        return float(parsed)

    def _scaled_config_offset(self, section_key: str, config_offset: float, global_scale_factor: float) -> float:
        # Unified formula:
        # target = anchor + (config_offset * global_scale_factor) + (config_offset * section_partial_offset)
        return (float(config_offset) * float(global_scale_factor)) + (
            float(config_offset) * float(self._section_scale_delta(section_key))
        )

    @staticmethod
    def _infer_field_section(field: Dict[str, Any]) -> str:
        if not isinstance(field, dict):
            return "question"
        raw = str(field.get("section", field.get("name", ""))).strip().lower()
        if raw in ("exam_no", "examno", "exam", "candidate_no", "수험번호"):
            return "exam_no"
        if raw in ("birth", "birthdate", "dob", "생년월일"):
            return "birth"
        if raw in ("name", "candidate_name", "성명", "이름"):
            return "name"
        if raw in ("subject", "choice_subject", "선택과목", "과목"):
            return "subject"
        return "question"

    @staticmethod
    def _effective_field_type(field: Dict[str, Any]) -> str:
        if not isinstance(field, dict):
            return ""
        raw = str(field.get("type", "")).strip().lower()
        if raw in ("digit_columns", "digit_column", "marker_digit", "marker_digit_column"):
            return "marker_digit_columns"
        if raw in ("single_choice_column", "marker_single_choice", "marker_single_choice_columns"):
            return "marker_single_choice_column"
        if raw == "grid":
            # Legacy absolute grid type is no longer used.
            if field.get("marker_start_index") is not None:
                return "marker_digit_columns"
            return "grid"
        if raw == "single_choice":
            # Legacy absolute single-choice type is no longer used.
            if field.get("marker_index") is not None:
                return "marker_single_choice_column"
            return "single_choice"
        return raw

    def _compute_global_scale_factors(
        self,
        work_img: Optional[np.ndarray],
        markers: Sequence[Marker],
        marker_location: str,
        base_scale: float,
        cfg: Optional[Dict[str, Any]] = None,
    ) -> Tuple[float, float]:
        if work_img is None:
            s = float(base_scale)
            return s, s

        config = cfg if isinstance(cfg, dict) else {}
        scale_value = float(base_scale)
        if not np.isfinite(scale_value) or scale_value <= 0.0:
            scale_value = 1.0

        x_factor = 1.0
        y_factor = 1.0
        img_h, img_w = work_img.shape[:2]

        # Keep the same scaling policy as analyze_marker_questions:
        # - apply axis scaling only when explicit metadata exists in config
        # - otherwise keep base factor (avoid implicit over-correction)
        try:
            layout_w = float(config.get("width", config.get("layout_width", 0.0)))
        except Exception:
            layout_w = 0.0
        try:
            layout_h = float(config.get("height", config.get("layout_height", 0.0)))
        except Exception:
            layout_h = 0.0

        if layout_w > 0.0:
            expected_w = float(layout_w) * float(scale_value)
            if expected_w > 1e-6:
                x_factor = float(np.clip(float(img_w) / expected_w, 0.92, 1.08))
        if layout_h > 0.0:
            expected_h = float(layout_h) * float(scale_value)
            if expected_h > 1e-6:
                y_factor = float(np.clip(float(img_h) / expected_h, 0.92, 1.08))

        loc = str(marker_location or "left").strip().lower()
        ordered = list(markers or [])
        if len(ordered) >= 2:
            if loc in ("top", "bottom"):
                ordered = sorted(ordered, key=lambda m: int(m.cx))
                measured_span = abs(float(ordered[-1].cx) - float(ordered[0].cx))
                pitch_key = "marker_dx"
            else:
                ordered = sorted(ordered, key=lambda m: int(m.cy))
                measured_span = abs(float(ordered[-1].cy) - float(ordered[0].cy))
                pitch_key = "marker_dy"

            try:
                expected_span = float(config.get("expected_marker_span", 0.0))
            except Exception:
                expected_span = 0.0
            if expected_span <= 0.0:
                try:
                    pitch = float(config.get(pitch_key, config.get("marker_pitch", 0.0)))
                except Exception:
                    pitch = 0.0
                if pitch > 0.0:
                    expected_span = float(pitch) * float(max(1, len(ordered) - 1))
            expected_span = float(expected_span) * float(scale_value)
            if expected_span > 1e-6 and measured_span > 1e-6:
                span_factor = float(np.clip(float(measured_span) / float(expected_span), 0.92, 1.08))
                if loc in ("top", "bottom"):
                    x_factor = span_factor
                else:
                    y_factor = span_factor

        if len(ordered) >= 1 and loc in ("top", "bottom"):
            try:
                top_cfg = float(config.get("top_marker_y", config.get("anchor_top_y", 0.0)))
            except Exception:
                top_cfg = 0.0
            if float(layout_h) > float(top_cfg) and float(top_cfg) > 0.0:
                expected_span_y = (float(layout_h) - float(top_cfg)) * float(scale_value)
                current_top_y = float(np.mean(np.asarray([float(m.cy) for m in ordered], dtype=np.float32)))
                measured_span_y = float(img_h) - float(current_top_y)
                if expected_span_y > 1e-6 and measured_span_y > 1e-6:
                    y_factor = float(np.clip(float(measured_span_y) / float(expected_span_y), 0.92, 1.08))

        return float(scale_value * x_factor), float(scale_value * y_factor)

    @staticmethod
    def _required_marker_index_for_fields(fields: Sequence[Dict[str, Any]]) -> int:
        required = 0
        for f in fields:
            if not isinstance(f, dict):
                continue
            f_type = OMRScanner._effective_field_type(f)
            try:
                if f_type == "marker_digit_columns":
                    start_idx = int(f.get("marker_start_index", 1))
                    digits = max(0, int(f.get("digits", 0)))
                    required = max(required, start_idx + digits - 1)
                elif f_type == "marker_single_choice_column":
                    required = max(required, int(f.get("marker_index", 1)))
            except Exception:
                continue
        return max(0, int(required))

    @staticmethod
    def _select_contiguous_marker_cluster(
        marker_axis: Sequence[Marker],
        axis_key: str,
        required_count: int,
        prefer_low_axis: bool = True,
    ) -> List[Marker]:
        if not marker_axis:
            return []
        if len(marker_axis) == 1:
            return list(marker_axis)

        ordered = sorted(marker_axis, key=lambda m: int(getattr(m, axis_key, 0)))
        coords = np.asarray([int(getattr(m, axis_key, 0)) for m in ordered], dtype=np.float32)
        gaps = np.diff(coords)
        if gaps.size == 0:
            return ordered

        q75 = float(np.percentile(gaps, 75.0))
        core = gaps[gaps <= q75] if gaps.size >= 4 else gaps
        median_gap = float(np.median(core)) if core.size > 0 else float(np.median(gaps))
        if median_gap <= 1.0:
            return ordered

        split_thr = max(28, int(round(median_gap * 2.4)))
        clusters: List[List[Marker]] = [[ordered[0]]]
        for i in range(1, len(ordered)):
            if int(coords[i] - coords[i - 1]) > split_thr:
                clusters.append([ordered[i]])
            else:
                clusters[-1].append(ordered[i])

        def _axis_anchor(group: Sequence[Marker]) -> int:
            return int(getattr(group[0], axis_key, 0)) if group else 10**9

        if int(required_count) > 0:
            eligible = [g for g in clusters if len(g) >= int(required_count)]
            if eligible:
                return list(min(eligible, key=_axis_anchor) if prefer_low_axis else max(eligible, key=_axis_anchor))

        # Fallback to the longest cluster, then edge preference.
        clusters = sorted(clusters, key=lambda g: (-len(g), _axis_anchor(g)))
        if not clusters:
            return ordered
        return list(clusters[0])

    @staticmethod
    def _select_stable_marker_window(
        marker_axis: Sequence[Marker],
        axis_key: str,
        required_count: int,
    ) -> List[Marker]:
        if not marker_axis:
            return []
        ordered = sorted(marker_axis, key=lambda m: int(getattr(m, axis_key, 0)))
        target = int(required_count)
        if target <= 0 or len(ordered) <= target:
            return ordered

        best_start = 0
        best_score = 10**9
        max_start = len(ordered) - target
        for start in range(max_start + 1):
            coords = np.asarray(
                [int(getattr(m, axis_key, 0)) for m in ordered[start : start + target]],
                dtype=np.float32,
            )
            gaps = np.diff(coords)
            if gaps.size == 0:
                score = 0.0
            else:
                med = float(np.median(gaps))
                if med <= 1.0:
                    continue
                rel_std = float(np.std(gaps)) / med
                outlier_penalty = float(np.sum(np.abs(gaps - med) > (0.45 * med)))
                score = rel_std + (outlier_penalty * 0.6)
            if score < best_score:
                best_score = score
                best_start = start
        return list(ordered[best_start : best_start + target])

    def _check_roi(
        self,
        processed_img: Optional[np.ndarray],
        x: int,
        y: int,
        w: int,
        h: int,
        debug_img: Optional[np.ndarray],
        color: Tuple[int, int, int],
        draw_unmarked: bool = True,
    ) -> bool:
        marked, ratio, clamped, eval_roi = self.image_processor.check_roi(
            processed_img, x, y, w, h, self.pixel_threshold
        )
        if debug_img is not None and clamped is not None:
            rx, ry, rw, rh = clamped
            if (not marked) and (not draw_unmarked):
                return marked
            draw_color = color if marked else (0, 0, 255)
            thickness = 2 if marked else 1
            cv2.rectangle(debug_img, (rx, ry), (rx + rw, ry + rh), draw_color, thickness)
            if marked:
                cv2.putText(
                    debug_img,
                    f"{int(ratio * 100)}%",
                    (rx, ry + rh - 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.3,
                    draw_color,
                    1,
                )
        return marked

    @staticmethod
    def _determine_status(marked_indices: Sequence[int]) -> str:
        if len(marked_indices) == 0:
            return "공란"
        if len(marked_indices) > 1:
            return "중복"
        return "정상"

    @staticmethod
    def _draw_error_box(debug_img: Optional[np.ndarray], rois: Sequence[Tuple[int, int, int, int]]) -> None:
        if debug_img is None or not rois:
            return
        try:
            bx1 = min(r[0] for r in rois)
            by1 = min(r[1] for r in rois)
            bx2 = max(r[0] + r[2] for r in rois)
            by2 = max(r[1] + r[3] for r in rois)
            cv2.rectangle(debug_img, (bx1 - 2, by1 - 2), (bx2 + 2, by2 + 2), (0, 255, 255), 2)
        except Exception:
            return

    @staticmethod
    def _fixed_row_linear_scale(cfg: Dict[str, Any]) -> float:
        """Deterministic row scale: no pixel-hit optimization, config-only fallback."""
        try:
            value = float(cfg.get("row_linear_scale", 1.0))
        except Exception:
            value = 1.0
        if not np.isfinite(value) or value <= 0.0:
            value = 1.0
        return float(np.clip(value, 0.85, 1.15))

    def analyze_sheet_cv(
        self,
        original_img: Optional[np.ndarray],
        questions_rois: Sequence[Sequence[Tuple[int, int, int, int]]],
        ref_anchor: Optional[Any] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray]]:
        del ref_anchor
        if original_img is None:
            return "ERROR", [], None

        work_img, processed_img = self.image_processor.preprocess(original_img)
        if work_img is None or processed_img is None:
            return "ERROR", [], None
        debug_img = work_img.copy()
        results: List[QuestionResult] = []
        has_error = False

        for q_idx, rois in enumerate(questions_rois):
            marked_indices: List[int] = []
            for r_idx, (x, y, w, h) in enumerate(rois):
                if self._check_roi(processed_img, x, y, w, h, debug_img, (0, 255, 0)):
                    marked_indices.append(int(r_idx))
            status = self._determine_status(marked_indices)
            if status != "정상":
                has_error = True
                self._draw_error_box(debug_img, rois)
            results.append(QuestionResult(q_num=int(q_idx + 1), marked=marked_indices, status=status))

        return ("오류" if has_error else "정상"), [r.as_dict() for r in results], debug_img

    def find_timing_marks(self, image: Optional[np.ndarray], left_ratio: float = 0.08) -> Tuple[List[int], int, List[int]]:
        if image is None:
            return [], 0, []
        img_h, img_w = image.shape[:2]
        left_limit = int(img_w * float(left_ratio))

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, int(self.marker_detector.marker_thresh), 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        contours_info = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]
        candidates: List[Tuple[int, int]] = []
        min_area = img_w * img_h * 0.0001
        max_area = img_w * img_h * 0.01
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            if x > left_limit:
                continue
            ratio = float(w) / float(h) if h > 0 else 0.0
            if not (0.6 <= ratio <= 1.6):
                continue
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area <= 0:
                continue
            solidity = float(area) / float(hull_area)
            if solidity < 0.85:
                continue
            candidates.append((int(x + (w // 2)), int(y + (h // 2))))

        if not candidates:
            return [], 0, []
        candidates = sorted(candidates, key=lambda it: int(it[1]))
        rows = [int(cy) for _, cy in candidates]
        xs_list = [int(cx) for cx, _ in candidates]
        anchor_x = int(np.median(xs_list)) if xs_list else 0
        return rows, anchor_x, xs_list

    def find_timing_marks_aligned(
        self, image: Optional[np.ndarray], left_ratio: float = 0.08
    ) -> Tuple[Optional[np.ndarray], List[int], int, List[int]]:
        if image is None:
            return None, [], 0, []
        rows, anchor_x, xs_list = self.find_timing_marks(image, left_ratio=left_ratio)
        if len(xs_list) >= 2 and abs(xs_list[-1] - xs_list[0]) > 1:
            corrected = self.geometry_manager.deskew_from_rows(image, rows, xs_list)
            if corrected is not None:
                image = corrected
            rows, anchor_x, xs_list = self.find_timing_marks(image, left_ratio=left_ratio)
        return image, rows, anchor_x, xs_list

    def read_answers(
        self,
        image: Optional[np.ndarray],
        rows: Sequence[int],
        anchor_x: int = 0,
        x_offset_ratio: float = 0.3,
        box_w_ratio: float = 0.04,
        box_h_ratio: float = 0.02,
        pixel_threshold: Optional[float] = None,
    ) -> Tuple[List[bool], Optional[np.ndarray]]:
        if image is None:
            return [], None

        work_img, processed_img = self.image_processor.preprocess(image)
        debug_img = work_img.copy() if work_img is not None else None
        if processed_img is None or not rows:
            return [], debug_img

        threshold = self.pixel_threshold if pixel_threshold is None else float(pixel_threshold)
        img_h, img_w = processed_img.shape[:2]
        box_w = max(1, int(img_w * float(box_w_ratio)))
        box_h = max(1, int(img_h * float(box_h_ratio)))
        x_offset = int(img_w * float(x_offset_ratio))

        marks: List[bool] = []
        for row_y in rows:
            rx = int(anchor_x + x_offset)
            ry = int(int(row_y) - (box_h // 2))
            clamped = self.image_processor.clamp_roi(processed_img, rx, ry, box_w, box_h)
            if clamped is None:
                marks.append(False)
                continue
            x, y, w, h = clamped
            roi = processed_img[y : y + h, x : x + w]
            ratio = float(cv2.countNonZero(roi)) / float(w * h) if (w * h) > 0 else 0.0
            is_marked = bool(ratio > threshold)
            marks.append(is_marked)
            if debug_img is not None:
                color = (0, 255, 0) if is_marked else (0, 0, 255)
                cv2.rectangle(debug_img, (x, y), (x + w, y + h), color, 1)
        return marks, debug_img

    def analyze_side_marker_sheet(
        self,
        original_img: Optional[np.ndarray],
        questions: Sequence[Dict[str, Any]],
        params: Dict[str, Any],
        scale: float = 1.0,
        marker_location: str = "left",
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray], str]:
        if original_img is None:
            return "ERROR", [], None, "IMG_NONE"

        try:
            min_marker_count = 3
            rotated_img, markers = self.marker_detector.normalize_orientation(
                original_img,
                expected_location=marker_location,
                min_count=min_marker_count,
            )
            if rotated_img is None:
                return "ERR", [], None, "IMG_NONE"

            base_img = rotated_img
            markers = self.marker_detector.find_markers(base_img, location=marker_location, min_count=min_marker_count)
            if markers and len(markers) >= 5:
                corrected = self.geometry_manager.deskew_by_markers(base_img, markers, marker_location)
                if corrected is not None:
                    base_img = corrected
                    markers = self.marker_detector.find_markers(base_img, location=marker_location, min_count=min_marker_count)

            work_img, processed_img = self.image_processor.preprocess(base_img)
            if work_img is None or processed_img is None:
                return "ERR", [], None, "PREPROCESS"
            debug_img = work_img.copy()

            markers = self.marker_detector.interpolate_missing_marks(markers)
            if len(markers) < len(questions):
                for m in markers:
                    cv2.circle(debug_img, (int(m.cx), int(m.cy)), 5, (0, 0, 255), -1)
                return "ERR", [], debug_img, "TIMING_MARK"

            raw_dist_agree = params.get("dist_agree") or params.get("marker_to_agree_dist") or 100
            raw_dist_disagree = params.get("dist_disagree") or params.get("marker_to_disagree_dist") or 200
            if params.get("marker_to_disagree_dist"):
                raw_dist_disagree = params.get("marker_to_disagree_dist")

            box_w = int(int(params.get("box_w", 35)) * float(scale))
            box_h = int(int(params.get("box_h", 35)) * float(scale))
            dist_agree = int(float(raw_dist_agree) * float(scale))
            dist_disagree = int(float(raw_dist_disagree) * float(scale))

            _, img_w = work_img.shape[:2]
            width_ratio = (float(img_w) / float(self.geometry_manager.width)) if self.geometry_manager.width > 0 else 1.0
            width_ratio = float(np.clip(width_ratio, 0.90, 3.0))

            is_horizontal = str(marker_location).strip().lower() in ("top", "bottom")
            marks_by_axis = sorted(markers, key=lambda m: int(m.cx if is_horizontal else m.cy))

            sheet_results: List[QuestionResult] = []
            has_error = False
            error_reason = ""
            question_off_x, question_off_y = self._combined_offset("question")

            for i, q in enumerate(questions):
                if not isinstance(q, dict):
                    continue
                q_num = int(q.get("no", i + 1))
                row_index = q.get("row_index", i)
                q_y = q.get("y")

                if row_index is not None and 0 <= int(row_index) < len(marks_by_axis):
                    base_mark = marks_by_axis[int(row_index)]
                elif q_y is not None:
                    base_mark = min(marks_by_axis, key=lambda m: abs(int(m.cy) - int(q_y)))
                else:
                    if i >= len(marks_by_axis):
                        sheet_results.append(QuestionResult(q_num=q_num, marked=[], status="마킹없음"))
                        has_error = True
                        continue
                    base_mark = marks_by_axis[i]

                base_cx = int(base_mark.cx)
                base_cy = int(base_mark.cy)
                start_y = int(base_cy - (box_h // 2) + question_off_y)
                rois = [
                    (
                        int(base_cx + int(dist_agree * width_ratio) + question_off_x),
                        int(start_y),
                        int(max(1, int(box_w * width_ratio))),
                        int(box_h),
                    ),
                    (
                        int(base_cx + int(dist_disagree * width_ratio) + question_off_x),
                        int(start_y),
                        int(max(1, int(box_w * width_ratio))),
                        int(box_h),
                    ),
                ]

                marked_indices: List[int] = []
                for r_idx, (rx, ry, rw, rh) in enumerate(rois):
                    cv2.rectangle(debug_img, (rx, ry), (rx + rw, ry + rh), (255, 0, 0), 1)
                    if self._check_roi(processed_img, rx, ry, rw, rh, debug_img, (0, 255, 0)):
                        marked_indices.append(r_idx)

                status = self._determine_status(marked_indices)
                if status != "정상":
                    has_error = True
                    if not error_reason:
                        error_reason = f"{status}(Q{q_num})"
                    self._draw_error_box(debug_img, rois)

                sheet_results.append(QuestionResult(q_num=q_num, marked=marked_indices, status=status))
                cv2.circle(debug_img, (base_cx, base_cy), 3, (0, 0, 255), -1)

            return ("ERR" if has_error else "OK"), [r.as_dict() for r in sheet_results], debug_img, error_reason
        except Exception as exc:
            logger.exception("[SideMarker] exception: %s", exc)
            return "ERR", [], None, "EXCEPTION"

    def analyze_marker_questions(
        self,
        original_img: Optional[np.ndarray],
        questions: Sequence[Dict[str, Any]],
        layout: Dict[str, Any],
        scale: float = 1.0,
        marker_location: str = "left",
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray], str]:
        if original_img is None:
            return "ERR", [], None, "IMG_NONE"
        if not isinstance(layout, dict):
            layout = {}

        try:
            is_horizontal_target = str(marker_location).strip().lower() in ("top", "bottom")
            numbering_order = str(layout.get("numbering_order", "column_major")).strip().lower()
            layout_columns = int(layout.get("columns", 0))
            rows_per_col = int(layout.get("rows_per_col", 40))
            if rows_per_col <= 0:
                rows_per_col = 40
            marker_start_index = max(1, int(layout.get("marker_start_index", 1)))
            row_start_from_marker = self._to_bool(layout.get("row_start_from_marker", True), True)

            rotated_img, markers = self.marker_detector.normalize_orientation(
                original_img,
                expected_location=marker_location,
                min_count=3,
            )
            if rotated_img is None:
                return "ERR", [], None, "IMG_NONE"

            work_img, processed_img = self.image_processor.preprocess(rotated_img)
            if work_img is None or processed_img is None:
                return "ERR", [], None, "PREPROCESS"
            debug_img = work_img.copy()

            markers = list(markers or [])
            if debug_img is not None:
                for m in markers:
                    cv2.circle(debug_img, (int(m.cx), int(m.cy)), 3, (0, 0, 255), -1)

            if not questions or not markers:
                return "ERR", [], debug_img, "TIMING_MARK"

            marks_by_y = sorted(markers, key=lambda m: int(m.cy))
            marks_by_x = sorted(markers, key=lambda m: int(m.cx))
            prepared: List[Dict[str, int]] = []
            for i, q in enumerate(questions):
                if not isinstance(q, dict):
                    continue
                q_num = int(q.get("no", i + 1))
                choices_count = max(1, int(q.get("choices", 5)))

                if is_horizontal_target:
                    col_index = q.get("col_index")
                    row_in_col = q.get("row_in_col")
                    if col_index is None or row_in_col is None:
                        idx = int(q_num) - 1
                        if numbering_order == "row_major":
                            cols = int(layout_columns) if int(layout_columns) > 0 else 1
                            cols = max(1, cols)
                            col_index = idx % cols
                            row_in_col = idx // cols
                        else:
                            col_index = idx // rows_per_col
                            row_in_col = idx % rows_per_col
                    prepared.append(
                        {
                            "q_num": q_num,
                            "choices": choices_count,
                            "col_index": int(col_index),
                            "row_in_col": int(row_in_col),
                        }
                    )
                else:
                    row_index = q.get("row_index")
                    if row_index is None:
                        row_index = i
                    prepared.append(
                        {
                            "q_num": q_num,
                            "choices": choices_count,
                            "row_index": int(row_index),
                        }
                    )

            if not prepared:
                return "ERR", [], debug_img, "TIMING_MARK"

            scale_factor = 1.0
            if is_horizontal_target:
                needed_cols = sorted({int(item["col_index"]) for item in prepared})
                if not needed_cols or needed_cols[0] < 0:
                    return "ERR", [], debug_img, "TIMING_MARK"

                col_anchor_map: Dict[int, Marker] = {}
                fixed_anchor_mode = self._to_bool(layout.get("fixed_anchor_mode", False), False)
                raw_anchor_indices = layout.get("column_anchor_indices", [])
                anchor_index_base = int(layout.get("column_anchor_index_base", 1))
                use_fixed = fixed_anchor_mode and isinstance(raw_anchor_indices, list) and len(raw_anchor_indices) > 0
                base_marks_for_fixed = marks_by_x[(marker_start_index - 1) :] if (marker_start_index - 1) < len(marks_by_x) else []

                for col in needed_cols:
                    if use_fixed:
                        if col >= len(raw_anchor_indices):
                            return "ERR", [], debug_img, "TIMING_MARK"
                        try:
                            idx0 = int(raw_anchor_indices[col]) - anchor_index_base
                        except Exception:
                            return "ERR", [], debug_img, "TIMING_MARK"
                        if not (0 <= idx0 < len(base_marks_for_fixed)):
                            return "ERR", [], debug_img, "TIMING_MARK"
                        col_anchor_map[col] = base_marks_for_fixed[idx0]
                    else:
                        idx0 = (marker_start_index - 1) + col
                        if not (0 <= idx0 < len(marks_by_x)):
                            return "ERR", [], debug_img, "TIMING_MARK"
                        col_anchor_map[col] = marks_by_x[idx0]

                if use_fixed:
                    fixed_anchor_y_mode = str(layout.get("fixed_anchor_y_mode", "")).strip().lower()
                    if fixed_anchor_y_mode == "median" and col_anchor_map:
                        med_y = int(
                            round(
                                float(
                                    np.median(
                                        np.asarray([int(col_anchor_map[c].cy) for c in needed_cols], dtype=np.float32)
                                    )
                                )
                            )
                        )
                        for col in needed_cols:
                            m = col_anchor_map[col]
                            col_anchor_map[col] = Marker(
                                cx=int(m.cx),
                                cy=int(med_y),
                                interpolated=bool(getattr(m, "interpolated", False)),
                            )

                first_col = int(needed_cols[0])
                last_col = int(needed_cols[-1])
                measured_span = abs(float(col_anchor_map[last_col].cx) - float(col_anchor_map[first_col].cx))
                span_units = max(0, last_col - first_col)

                expected_span = 0.0
                expected_marker_span_cfg = layout.get("expected_marker_span", 0)
                try:
                    span_cfg_value = float(expected_marker_span_cfg)
                except Exception:
                    span_cfg_value = 0.0
                if span_cfg_value > 0.0:
                    expected_span = span_cfg_value * float(scale)
                else:
                    step_cfg_raw = layout.get("marker_dx", layout.get("marker_pitch", 0))
                    try:
                        step_cfg_value = float(step_cfg_raw)
                    except Exception:
                        step_cfg_value = 0.0
                    if step_cfg_value > 0.0 and span_units > 0:
                        expected_span = float(step_cfg_value) * float(scale) * float(span_units)

                if expected_span > 1e-6 and measured_span > 1e-6:
                    scale_factor = float(measured_span) / float(expected_span)
                    if not np.isfinite(scale_factor) or scale_factor <= 0.0:
                        scale_factor = 1.0
            else:
                needed_rows = sorted({int(item["row_index"]) for item in prepared})
                if not needed_rows or needed_rows[0] < 0:
                    return "ERR", [], debug_img, "TIMING_MARK"

                row_anchor_map: Dict[int, Marker] = {}
                for row_idx in needed_rows:
                    idx0 = (marker_start_index - 1) + row_idx
                    if not (0 <= idx0 < len(marks_by_y)):
                        return "ERR", [], debug_img, "TIMING_MARK"
                    row_anchor_map[row_idx] = marks_by_y[idx0]
                first_row = int(needed_rows[0])
                last_row = int(needed_rows[-1])
                measured_span = abs(float(row_anchor_map[last_row].cy) - float(row_anchor_map[first_row].cy))
                span_units = max(0, last_row - first_row)

                expected_span = 0.0
                expected_marker_span_cfg = layout.get("expected_marker_span", 0)
                try:
                    span_cfg_value = float(expected_marker_span_cfg)
                except Exception:
                    span_cfg_value = 0.0
                if span_cfg_value > 0.0:
                    expected_span = span_cfg_value * float(scale)
                else:
                    step_cfg_raw = layout.get("marker_dy", layout.get("marker_pitch", 0))
                    try:
                        step_cfg_value = float(step_cfg_raw)
                    except Exception:
                        step_cfg_value = 0.0
                    if step_cfg_value > 0.0 and span_units > 0:
                        expected_span = float(step_cfg_value) * float(scale) * float(span_units)

                if expected_span > 1e-6 and measured_span > 1e-6:
                    scale_factor = float(measured_span) / float(expected_span)
                    if not np.isfinite(scale_factor) or scale_factor <= 0.0:
                        scale_factor = 1.0

            # Axis-specific scaling uses explicit layout metadata only.
            # When metadata is absent, keep the base factor to avoid over-correction.
            x_scale_factor = float(scale_factor)
            y_scale_factor = float(scale_factor)

            try:
                layout_w_cfg = float(layout.get("width", layout.get("layout_width", 0)))
            except Exception:
                layout_w_cfg = 0.0
            if layout_w_cfg > 0.0:
                expected_w = layout_w_cfg * float(scale)
                measured_w = float(work_img.shape[1])
                if expected_w > 1e-6 and measured_w > 1e-6:
                    x_scale = float(measured_w) / float(expected_w)
                    if np.isfinite(x_scale) and x_scale > 0.0:
                        x_scale_factor = x_scale

            if is_horizontal_target:
                try:
                    layout_h_cfg = float(layout.get("height", layout.get("layout_height", 0)))
                except Exception:
                    layout_h_cfg = 0.0
                try:
                    layout_top_y_cfg = float(layout.get("top_marker_y", layout.get("anchor_top_y", 0)))
                except Exception:
                    layout_top_y_cfg = 0.0
                if layout_h_cfg > layout_top_y_cfg and layout_top_y_cfg > 0.0:
                    current_top_y = float(np.mean(np.asarray([float(m.cy) for m in marks_by_x], dtype=np.float32)))
                    current_height = float(work_img.shape[0])
                    measured_span_y = current_height - current_top_y
                    expected_span_y = (layout_h_cfg - layout_top_y_cfg) * float(scale)
                    if expected_span_y > 1e-6 and measured_span_y > 1e-6:
                        y_scale = float(measured_span_y) / float(expected_span_y)
                        if np.isfinite(y_scale) and y_scale > 0.0:
                            y_scale_factor = y_scale
            else:
                try:
                    layout_h_cfg = float(layout.get("height", layout.get("layout_height", 0)))
                except Exception:
                    layout_h_cfg = 0.0
                if layout_h_cfg > 0.0:
                    expected_h = layout_h_cfg * float(scale)
                    measured_h = float(work_img.shape[0])
                    if expected_h > 1e-6 and measured_h > 1e-6:
                        y_scale = float(measured_h) / float(expected_h)
                        if np.isfinite(y_scale) and y_scale > 0.0:
                            y_scale_factor = y_scale

            x_scale_factor = float(np.clip(x_scale_factor, 0.92, 1.08))
            y_scale_factor = float(np.clip(y_scale_factor, 0.92, 1.08))

            geom_scale_x = float(scale) * float(x_scale_factor)
            geom_scale_y = float(scale) * float(y_scale_factor)

            # Unified geometry:
            # target = anchor + (config_offset * global_scale) + (config_offset * section_offset)
            x_offset = self._scaled_config_offset("question", float(layout.get("x_offset", 600)), geom_scale_x)
            choice_dx = self._scaled_config_offset("question", float(layout.get("choice_dx", 70)), geom_scale_x)
            box_w = max(1, int(round(float(layout.get("box_w", 40)) * geom_scale_x)))
            box_h = max(1, int(round(float(layout.get("box_h", 40)) * geom_scale_y)))
            row_offset_y = self._scaled_config_offset("question", float(layout.get("row_offset_y", 0)), geom_scale_y)
            row_start_y = self._scaled_config_offset("question", float(layout.get("row_start_y", 360)), geom_scale_y)
            row_dy = self._scaled_config_offset("question", float(layout.get("row_dy", 70)), geom_scale_y)
            question_off_x, question_off_y = self._combined_offset("question")

            # Global Y-scale tuning (single factor for all rows) to reduce cumulative drift.
            row_linear_scale = 1.0
            adaptive_linear_scaling = self._to_bool(layout.get("adaptive_linear_scaling", True), True)
            if adaptive_linear_scaling and is_horizontal_target and prepared and col_anchor_map:
                try:
                    min_s = float(layout.get("row_scale_min", 0.9))
                except Exception:
                    min_s = 0.9
                try:
                    max_s = float(layout.get("row_scale_max", 1.1))
                except Exception:
                    max_s = 1.1
                if not np.isfinite(min_s) or not np.isfinite(max_s):
                    min_s, max_s = 0.9, 1.1
                if min_s > max_s:
                    min_s, max_s = max_s, min_s
                min_s = max(0.85, min_s)
                max_s = min(1.15, max_s)
                candidates = np.linspace(min_s, max_s, 11).tolist()

                def _score(scale_mul: float) -> Tuple[int, int]:
                    normals = 0
                    penalty = 0
                    for item in prepared:
                        col_index = int(item["col_index"])
                        base_mark = col_anchor_map.get(col_index)
                        if base_mark is None:
                            penalty += 3
                            continue
                        base_cx = float(base_mark.cx)
                        row_in_col = int(item.get("row_in_col", 0))
                        if row_start_from_marker:
                            base_cy_local = float(base_mark.cy) + (float(row_start_y) * float(scale_mul)) + (
                                float(row_in_col) * float(row_dy) * float(scale_mul)
                            )
                        else:
                            base_cy_local = (float(row_start_y) * float(scale_mul)) + (
                                float(row_in_col) * float(row_dy) * float(scale_mul)
                            )
                        start_y_local = int(
                            round(base_cy_local + (float(row_offset_y) * float(scale_mul)) + float(question_off_y) - (box_h / 2.0))
                        )

                        choices_count_local = int(item["choices"])
                        hits = 0
                        for c_idx in range(choices_count_local):
                            rx_local = int(
                                round(
                                    float(base_cx)
                                    + float(x_offset)
                                    + (float(c_idx) * float(choice_dx))
                                    + float(question_off_x)
                                )
                            )
                            marked, _, _, _ = self.image_processor.check_roi(
                                processed_img, rx_local, start_y_local, int(box_w), int(box_h), self.pixel_threshold
                            )
                            if marked:
                                hits += 1
                        if hits == 1:
                            normals += 1
                        else:
                            penalty += abs(hits - 1) + 1
                    return normals, penalty

                best_s = 1.0
                best_normals, best_penalty = _score(1.0)
                for s in candidates:
                    normals, penalty = _score(float(s))
                    if (normals > best_normals) or (normals == best_normals and penalty < best_penalty):
                        best_s = float(s)
                        best_normals = normals
                        best_penalty = penalty
                row_linear_scale = float(best_s)

            results: List[QuestionResult] = []
            has_error = False
            error_reason = ""

            for item in prepared:
                q_num = int(item["q_num"])
                choices_count = int(item["choices"])

                if is_horizontal_target:
                    col_index = int(item["col_index"])
                    if col_index not in col_anchor_map:
                        return "ERR", [], debug_img, "TIMING_MARK"
                    base_mark = col_anchor_map[col_index]
                    base_cx = float(base_mark.cx)
                    row_in_col = int(item.get("row_in_col", 0))
                    if row_start_from_marker:
                        base_cy = float(base_mark.cy) + (float(row_start_y) * row_linear_scale) + (
                            (float(row_in_col) * float(row_dy) * row_linear_scale)
                        )
                    else:
                        base_cy = (float(row_start_y) * row_linear_scale) + (
                            (float(row_in_col) * float(row_dy) * row_linear_scale)
                        )
                    target_cy = base_cy + (float(row_offset_y) * row_linear_scale) + float(question_off_y)
                    start_y = int(round(target_cy - (box_h / 2.0)))
                else:
                    row_index = int(item["row_index"])
                    if row_index not in row_anchor_map:
                        return "ERR", [], debug_img, "TIMING_MARK"
                    base_mark = row_anchor_map[row_index]
                    base_cx = float(base_mark.cx)
                    if row_start_from_marker:
                        base_cy = float(base_mark.cy) + (float(row_start_y) * row_linear_scale)
                    else:
                        base_cy = (float(row_start_y) * row_linear_scale) + (float(row_index) * float(row_dy) * row_linear_scale)
                    target_cy = base_cy + (float(row_offset_y) * row_linear_scale) + float(question_off_y)
                    start_y = int(round(target_cy - (box_h / 2.0)))

                rois: List[Tuple[int, int, int, int]] = []
                for c_idx in range(choices_count):
                    target_x = float(base_cx) + float(x_offset) + (float(c_idx) * float(choice_dx)) + float(question_off_x)
                    rx = int(round(target_x))
                    rois.append((rx, int(start_y), int(box_w), int(box_h)))

                marked_indices: List[int] = []
                for r_idx, (rx, ry, rw, rh) in enumerate(rois):
                    if self._check_roi(processed_img, rx, ry, rw, rh, debug_img, (0, 255, 0)):
                        marked_indices.append(int(r_idx))

                status = self._determine_status(marked_indices)
                if status != "정상":
                    has_error = True
                    if not error_reason:
                        error_reason = f"{status}(Q{q_num})"
                    self._draw_error_box(debug_img, rois)

                results.append(QuestionResult(q_num=q_num, marked=marked_indices, status=status))

            return ("ERR" if has_error else "OK"), [r.as_dict() for r in results], debug_img, error_reason
        except Exception as exc:
            logger.exception("[MarkerQ] exception: %s", exc)
            return "ERR", [], None, "EXCEPTION"

    def _decode_single_choice(
        self,
        processed_img: Optional[np.ndarray],
        cfg: Dict[str, Any],
        scale: float,
        debug_img: Optional[np.ndarray],
        section_key: str = "question",
    ) -> Tuple[bool, str]:
        if processed_img is None:
            return False, ""
        choices = cfg.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return False, ""
        prepared: List[Dict[str, Any]] = []
        for ch in choices:
            if not isinstance(ch, dict):
                continue
            prepared.append(
                {
                    "x": float(ch.get("x", 0)),
                    "y": float(ch.get("y", 0)),
                    "w": max(1, int(float(ch.get("w", 20)) * float(scale))),
                    "h": max(1, int(float(ch.get("h", 20)) * float(scale))),
                    "label": str(ch.get("label", "")),
                }
            )
        if not prepared:
            return False, ""

        off_x, off_y = self._combined_offset(section_key)
        anchor_y = float(min(float(item["y"]) for item in prepared))
        row_linear_scale = self._fixed_row_linear_scale(cfg)
        auto_dy_scale = self._to_bool(cfg.get("auto_dy_scale", False), False)

        def _evaluate(scale_mul: float, draw: bool) -> Tuple[int, str]:
            hits_local = 0
            picked_local = ""
            for item in prepared:
                x = int(round(float(item["x"]) * float(scale) + float(off_x)))
                rel_y = float(item["y"]) - float(anchor_y)
                y_cfg = float(anchor_y) + (float(rel_y) * float(scale_mul))
                y = int(round(float(y_cfg) * float(scale) + float(off_y)))
                w = int(item["w"])
                h = int(item["h"])
                if draw:
                    marked = self._check_roi(processed_img, x, y, w, h, debug_img, (255, 0, 255))
                else:
                    marked, _, _, _ = self.image_processor.check_roi(
                        processed_img, x, y, w, h, self.pixel_threshold
                    )
                if marked:
                    hits_local += 1
                    picked_local = str(item["label"])
            return hits_local, picked_local

        if auto_dy_scale:
            try:
                min_s = float(cfg.get("row_scale_min", 0.9))
            except Exception:
                min_s = 0.9
            try:
                max_s = float(cfg.get("row_scale_max", 1.1))
            except Exception:
                max_s = 1.1
            if not np.isfinite(min_s) or not np.isfinite(max_s):
                min_s, max_s = 0.9, 1.1
            if min_s > max_s:
                min_s, max_s = max_s, min_s
            min_s = max(0.85, min_s)
            max_s = min(1.15, max_s)
            candidates = np.linspace(min_s, max_s, 11).tolist()

            best_s = float(row_linear_scale)
            best_hits, _ = _evaluate(best_s, draw=False)
            best_penalty = 0 if best_hits == 1 else (abs(best_hits - 1) + 1)
            for s in candidates:
                hits, _ = _evaluate(float(s), draw=False)
                penalty = 0 if hits == 1 else (abs(hits - 1) + 1)
                if (penalty < best_penalty) or (
                    penalty == best_penalty and abs(float(s) - 1.0) < abs(best_s - 1.0)
                ):
                    best_s = float(s)
                    best_penalty = penalty
                    best_hits = hits
            row_linear_scale = float(best_s)

        hits, picked = _evaluate(float(row_linear_scale), draw=True)
        return (hits == 1), (picked if hits == 1 else "")

    def _decode_marker_digit_columns(
        self,
        processed_img: Optional[np.ndarray],
        markers: Sequence[Marker],
        cfg: Dict[str, Any],
        scale: float,
        debug_img: Optional[np.ndarray],
        section_key: str = "question",
        global_scale_x: Optional[float] = None,
        global_scale_y: Optional[float] = None,
    ) -> Tuple[bool, str]:
        if processed_img is None or not markers or not isinstance(cfg, dict):
            return False, ""

        marker_start_index = int(cfg.get("marker_start_index", 1)) - 1
        digits = int(cfg.get("digits", 0))
        if digits <= 0:
            return False, ""

        rows_default = int(cfg.get("rows", 10))
        rows_per_digit = cfg.get("rows_per_digit", [])
        if not isinstance(rows_per_digit, list):
            rows_per_digit = []

        scale_x = float(scale if global_scale_x is None else global_scale_x)
        scale_y = float(scale if global_scale_y is None else global_scale_y)
        x_offset = self._scaled_config_offset(section_key, float(cfg.get("x_offset", 0)), scale_x)
        y_offset = self._scaled_config_offset(section_key, float(cfg.get("y_offset", 0)), scale_y)
        row_dy = self._scaled_config_offset(section_key, float(cfg.get("row_dy", cfg.get("row_h", 20))), scale_y)
        box_w = max(1, int(round(float(cfg.get("box_w", 40)) * float(scale_x))))
        box_h = max(1, int(round(float(cfg.get("box_h", 40)) * float(scale_y))))
        off_x, off_y = self._combined_offset(section_key)

        row_linear_scale = self._fixed_row_linear_scale(cfg)
        marker_span_x = 0.0
        marker_span_y = 0.0
        if len(markers) >= 2:
            marker_span_x = float(max(int(m.cx) for m in markers) - min(int(m.cx) for m in markers))
            marker_span_y = float(max(int(m.cy) for m in markers) - min(int(m.cy) for m in markers))
        is_horizontal_axis = marker_span_x >= marker_span_y
        anchor_y_mode = str(cfg.get("anchor_y_mode", "median")).strip().lower()
        median_anchor_y = float(np.median(np.asarray([float(m.cy) for m in markers], dtype=np.float32))) if markers else 0.0

        auto_dy_scale = self._to_bool(cfg.get("auto_dy_scale", False), False)
        if auto_dy_scale:
            try:
                min_s = float(cfg.get("row_scale_min", 0.9))
            except Exception:
                min_s = 0.9
            try:
                max_s = float(cfg.get("row_scale_max", 1.1))
            except Exception:
                max_s = 1.1
            if not np.isfinite(min_s) or not np.isfinite(max_s):
                min_s, max_s = 0.9, 1.1
            if min_s > max_s:
                min_s, max_s = max_s, min_s
            min_s = max(0.85, min_s)
            max_s = min(1.15, max_s)
            candidates = np.linspace(min_s, max_s, 11).tolist()

            def _score(scale_mul: float) -> Tuple[int, int]:
                normals = 0
                penalty = 0
                for digit_idx_local in range(digits):
                    m_idx_local = marker_start_index + digit_idx_local
                    if m_idx_local < 0 or m_idx_local >= len(markers):
                        penalty += 2
                        continue
                    rows_local = rows_default
                    if digit_idx_local < len(rows_per_digit):
                        try:
                            rows_local = int(rows_per_digit[digit_idx_local])
                        except Exception:
                            rows_local = rows_default
                    if rows_local <= 0:
                        penalty += 2
                        continue

                    base_local = markers[m_idx_local]
                    center_x_local = int(round(float(base_local.cx) + float(x_offset) + float(off_x)))
                    base_cy_local = float(base_local.cy)
                    if is_horizontal_axis and anchor_y_mode == "median":
                        base_cy_local = float(median_anchor_y)

                    hits_local = 0
                    for r_idx_local in range(rows_local):
                        center_y_local = int(
                            round(
                                float(base_cy_local)
                                + (float(y_offset) * float(scale_mul))
                                + (float(r_idx_local) * float(row_dy) * float(scale_mul))
                                + float(off_y)
                            )
                        )
                        rx_local = int(center_x_local - (box_w // 2))
                        ry_local = int(center_y_local - (box_h // 2))
                        marked_local, _, _, _ = self.image_processor.check_roi(
                            processed_img, rx_local, ry_local, box_w, box_h, self.pixel_threshold
                        )
                        if marked_local:
                            hits_local += 1

                    if hits_local == 1:
                        normals += 1
                    else:
                        penalty += abs(hits_local - 1) + 1
                return normals, penalty

            best_s = float(row_linear_scale)
            best_normals, best_penalty = _score(best_s)
            for s in candidates:
                normals, penalty = _score(float(s))
                if (normals > best_normals) or (normals == best_normals and penalty < best_penalty):
                    best_s = float(s)
                    best_normals = normals
                    best_penalty = penalty
            row_linear_scale = float(best_s)

        result: List[str] = []
        overall_ok = True
        for digit_idx in range(digits):
            m_idx = marker_start_index + digit_idx
            if m_idx < 0 or m_idx >= len(markers):
                overall_ok = False
                continue

            rows = rows_default
            if digit_idx < len(rows_per_digit):
                try:
                    rows = int(rows_per_digit[digit_idx])
                except Exception:
                    rows = rows_default
            if rows <= 0:
                overall_ok = False
                continue

            base = markers[m_idx]
            center_x = int(round(float(base.cx) + float(x_offset) + float(off_x)))
            base_cy = float(base.cy)
            if is_horizontal_axis and anchor_y_mode == "median":
                base_cy = float(median_anchor_y)
            best_r = -1
            best_ratio = -1.0
            best_y = int(round(float(base_cy) + float(y_offset) + float(off_y)))
            hits = 0
            draw_rows = max(rows_default, rows)
            for r_idx in range(draw_rows):
                center_y = int(
                    round(
                        float(base_cy)
                        + (float(y_offset) * float(row_linear_scale))
                        + (float(r_idx) * float(row_dy) * float(row_linear_scale))
                        + float(off_y)
                    )
                )
                local_best = -1.0
                local_y = center_y
                if r_idx < rows:
                    rx = int(center_x - (box_w // 2))
                    ry = int(center_y - (box_h // 2))
                    clamped = self.image_processor.clamp_roi(processed_img, rx, ry, box_w, box_h)
                    if clamped is not None:
                        x1, y1, w1, h1 = clamped
                        roi = processed_img[y1 : y1 + h1, x1 : x1 + w1]
                        local_best = float(cv2.countNonZero(roi)) / float(w1 * h1) if (w1 * h1) > 0 else 0.0
                if debug_img is not None:
                    rx = int(center_x - (box_w // 2))
                    ry = int(local_y - (box_h // 2))
                    color = (0, 255, 0) if local_best > self.pixel_threshold else (0, 0, 255)
                    cv2.rectangle(debug_img, (rx, ry), (rx + box_w, ry + box_h), color, 1)
                if r_idx < rows and local_best > self.pixel_threshold:
                    hits += 1
                    if local_best > best_ratio:
                        best_ratio = local_best
                        best_r = r_idx
                        best_y = local_y
            if debug_img is not None and best_r >= 0:
                rx = int(center_x - (box_w // 2))
                ry = int(best_y - (box_h // 2))
                color = (0, 255, 0) if hits == 1 else (0, 0, 255)
                cv2.rectangle(debug_img, (rx, ry), (rx + box_w, ry + box_h), color, 2)
            if hits == 1 and best_r >= 0:
                result.append(str(best_r))
            else:
                overall_ok = False
        if overall_ok and len(result) == digits:
            return True, "".join(result)
        return False, ""

    def _decode_marker_single_choice_column(
        self,
        processed_img: Optional[np.ndarray],
        markers: Sequence[Marker],
        cfg: Dict[str, Any],
        scale: float,
        debug_img: Optional[np.ndarray],
        section_key: str = "question",
        global_scale_x: Optional[float] = None,
        global_scale_y: Optional[float] = None,
    ) -> Tuple[bool, str]:
        if processed_img is None or not markers or not isinstance(cfg, dict):
            return False, ""
        marker_index = int(cfg.get("marker_index", 1)) - 1
        if marker_index < 0 or marker_index >= len(markers):
            return False, ""

        raw_choices = cfg.get("choices", [])
        labels: List[str] = []
        per_choice_offsets: List[Optional[float]] = []
        if isinstance(raw_choices, list):
            for ch in raw_choices:
                if isinstance(ch, dict):
                    labels.append(str(ch.get("label", "")))
                    try:
                        per_choice_offsets.append(None if ch.get("y_offset") is None else float(ch.get("y_offset")))
                    except Exception:
                        per_choice_offsets.append(None)
                else:
                    labels.append(str(ch))
                    per_choice_offsets.append(None)
        labels = [lb for lb in labels if lb != ""]
        if not labels:
            return False, ""

        scale_x = float(scale if global_scale_x is None else global_scale_x)
        scale_y = float(scale if global_scale_y is None else global_scale_y)
        x_offset = self._scaled_config_offset(section_key, float(cfg.get("x_offset", 0)), scale_x)
        y_offset = self._scaled_config_offset(section_key, float(cfg.get("y_offset", 0)), scale_y)
        choice_dy = self._scaled_config_offset(
            section_key,
            float(cfg.get("choice_dy", cfg.get("row_dy", 40))),
            scale_y,
        )
        raw_choice_offsets = cfg.get("choice_y_offsets", [])
        choice_offsets: List[float] = []
        if isinstance(raw_choice_offsets, list):
            for value in raw_choice_offsets:
                try:
                    choice_offsets.append(
                        self._scaled_config_offset(section_key, float(value), scale_y)
                    )
                except Exception:
                    continue
        box_w = max(1, int(round(float(cfg.get("box_w", 40)) * float(scale_x))))
        box_h = max(1, int(round(float(cfg.get("box_h", 40)) * float(scale_y))))
        off_x, off_y = self._combined_offset(section_key)

        base = markers[marker_index]
        center_x = int(round(float(base.cx) + float(x_offset) + float(off_x)))
        row_linear_scale = self._fixed_row_linear_scale(cfg)
        marker_span_x = 0.0
        marker_span_y = 0.0
        if len(markers) >= 2:
            marker_span_x = float(max(int(m.cx) for m in markers) - min(int(m.cx) for m in markers))
            marker_span_y = float(max(int(m.cy) for m in markers) - min(int(m.cy) for m in markers))
        is_horizontal_axis = marker_span_x >= marker_span_y
        anchor_y_mode = str(cfg.get("anchor_y_mode", "median")).strip().lower()
        base_cy = float(base.cy)
        if is_horizontal_axis and anchor_y_mode == "median":
            base_cy = float(np.median(np.asarray([float(m.cy) for m in markers], dtype=np.float32)))

        auto_dy_scale = self._to_bool(cfg.get("auto_dy_scale", False), False)
        if auto_dy_scale:
            try:
                min_s = float(cfg.get("row_scale_min", 0.9))
            except Exception:
                min_s = 0.9
            try:
                max_s = float(cfg.get("row_scale_max", 1.1))
            except Exception:
                max_s = 1.1
            if not np.isfinite(min_s) or not np.isfinite(max_s):
                min_s, max_s = 0.9, 1.1
            if min_s > max_s:
                min_s, max_s = max_s, min_s
            min_s = max(0.85, min_s)
            max_s = min(1.15, max_s)
            candidates = np.linspace(min_s, max_s, 11).tolist()

            def _rel_y(idx_local: int) -> float:
                if idx_local < len(choice_offsets):
                    return float(choice_offsets[idx_local])
                if idx_local < len(per_choice_offsets) and per_choice_offsets[idx_local] is not None:
                    return self._scaled_config_offset(section_key, float(per_choice_offsets[idx_local]), scale_y)
                return float(idx_local) * float(choice_dy)

            def _score(scale_mul: float) -> Tuple[int, int]:
                hits_local = 0
                for idx_local, _ in enumerate(labels):
                    rel_y_local = _rel_y(idx_local)
                    center_y_local = int(
                        round(
                            float(base_cy)
                            + (float(y_offset) * float(scale_mul))
                            + (float(rel_y_local) * float(scale_mul))
                            + float(off_y)
                        )
                    )
                    rx_local = int(center_x - (box_w // 2))
                    ry_local = int(center_y_local - (box_h // 2))
                    marked_local, _, _, _ = self.image_processor.check_roi(
                        processed_img, rx_local, ry_local, box_w, box_h, self.pixel_threshold
                    )
                    if marked_local:
                        hits_local += 1
                normals = 1 if hits_local == 1 else 0
                penalty = 0 if hits_local == 1 else (abs(hits_local - 1) + 1)
                return normals, penalty

            best_s = float(row_linear_scale)
            best_normals, best_penalty = _score(best_s)
            for s in candidates:
                normals, penalty = _score(float(s))
                if (normals > best_normals) or (normals == best_normals and penalty < best_penalty):
                    best_s = float(s)
                    best_normals = normals
                    best_penalty = penalty
            row_linear_scale = float(best_s)

        base_y = int(round(float(base_cy) + (float(y_offset) * float(row_linear_scale)) + float(off_y)))
        hits = 0
        picked = ""
        for idx, label in enumerate(labels):
            if idx < len(choice_offsets):
                rel_y = float(choice_offsets[idx])
            elif idx < len(per_choice_offsets) and per_choice_offsets[idx] is not None:
                rel_y = self._scaled_config_offset(section_key, float(per_choice_offsets[idx]), scale_y)
            else:
                rel_y = float(idx) * float(choice_dy)
            center_y = int(round(float(base_y) + (float(rel_y) * float(row_linear_scale))))
            rx = center_x - (box_w // 2)
            ry = center_y - (box_h // 2)
            if self._check_roi(
                processed_img,
                rx,
                ry,
                box_w,
                box_h,
                debug_img,
                (255, 0, 255),
                draw_unmarked=True,
            ):
                hits += 1
                picked = label
        return (hits == 1), (picked if hits == 1 else "")

    def analyze_candidate_info(
        self,
        original_img: Optional[np.ndarray],
        config: Dict[str, Any],
        scale: float = 1.0,
    ) -> Tuple[bool, Dict[str, Any], Optional[np.ndarray]]:
        if original_img is None or not config:
            return False, {}, None
        fields: List[Dict[str, Any]] = []
        for key in ("exam_no", "birth", "name", "subject"):
            raw = config.get(key)
            if not isinstance(raw, dict):
                continue
            field_cfg = dict(raw)
            field_cfg.setdefault("name", key)
            f_type = str(field_cfg.get("type", "")).strip().lower()
            if not f_type:
                f_type = "marker_single_choice_column" if key == "subject" else "marker_digit_columns"
            if f_type == "grid":
                f_type = "marker_digit_columns"
            if f_type == "single_choice":
                f_type = "marker_single_choice_column"
            field_cfg["type"] = f_type
            if f_type in ("marker_digit_columns", "marker_single_choice_column"):
                field_cfg.setdefault("anchor_y_mode", "median")
                field_cfg.setdefault("auto_dy_scale", True)
                field_cfg.setdefault("row_scale_min", 0.9)
                field_cfg.setdefault("row_scale_max", 1.1)
            field_cfg.setdefault("section", key)
            fields.append(field_cfg)

        if not fields:
            return False, {}, None
        return self.analyze_custom_fields(original_img, fields, scale=scale)

    def analyze_custom_fields(
        self,
        original_img: Optional[np.ndarray],
        fields: Sequence[Dict[str, Any]],
        scale: float = 1.0,
    ) -> Tuple[bool, Dict[str, Any], Optional[np.ndarray]]:
        if original_img is None or not fields:
            return False, {}, None

        marker_field_types = {"marker_digit_columns", "marker_single_choice_column"}
        normalized_fields: List[Dict[str, Any]] = []
        for field in fields:
            if not isinstance(field, dict):
                continue
            cfg = dict(field)
            eff_type = self._effective_field_type(cfg)
            cfg["type"] = eff_type
            if eff_type in marker_field_types:
                cfg.setdefault("anchor_y_mode", "median")
                cfg.setdefault("auto_dy_scale", True)
                cfg.setdefault("row_scale_min", 0.9)
                cfg.setdefault("row_scale_max", 1.1)
            normalized_fields.append(cfg)

        marker_fields = [
            f
            for f in normalized_fields
            if str(f.get("type", "")).strip().lower() in marker_field_types
        ]
        marker_field = next(
            (
                f
                for f in normalized_fields
                if str(f.get("type", "")).strip().lower() in marker_field_types
            ),
            None,
        )

        marker_location = "left"
        axis_key = "cy"
        marker_axis: List[Marker] = []
        base_img = original_img
        if marker_field is not None:
            marker_location = str(marker_field.get("marker_location", "left")).strip().lower()
            base_img, markers = self.marker_detector.normalize_orientation(
                original_img,
                expected_location=marker_location,
                min_count=3,
            )
            if base_img is None:
                return False, {}, None
            axis_key = "cx" if marker_location in ("top", "bottom") else "cy"
            marker_axis = sorted(
                list(markers or []),
                key=lambda m: int(getattr(m, axis_key, 0)),
            )
            required_idx = self._required_marker_index_for_fields(normalized_fields)
            if required_idx > 0 and len(marker_axis) < required_idx:
                cluster_axis = self._select_contiguous_marker_cluster(
                    marker_axis,
                    axis_key=axis_key,
                    required_count=required_idx,
                    prefer_low_axis=True,
                )
                if cluster_axis:
                    marker_axis = cluster_axis

        work_img, processed_img = self.image_processor.preprocess(base_img)
        if work_img is None or processed_img is None:
            return False, {}, None
        debug_img = np.zeros_like(work_img)
        info: Dict[str, Any] = {}
        is_ok = True
        marker_axis_for_decode = list(marker_axis)

        if marker_axis_for_decode and marker_fields:
            max_required_idx = self._required_marker_index_for_fields(marker_fields)
            allow_interp_shared = any(
                self._to_bool(f.get("use_marker_interpolation", False), False) for f in marker_fields
            )
            if allow_interp_shared and max_required_idx > len(marker_axis_for_decode):
                interp_axis = self.marker_detector.interpolate_missing_marks(marker_axis_for_decode)
                if len(interp_axis) > len(marker_axis_for_decode):
                    marker_axis_for_decode = sorted(interp_axis, key=lambda m: int(getattr(m, axis_key, 0)))

        scale_cfg = marker_field if isinstance(marker_field, dict) else {}
        global_scale_x, global_scale_y = self._compute_global_scale_factors(
            work_img,
            marker_axis_for_decode,
            marker_location,
            scale,
            cfg=scale_cfg,
        )

        def _decode_marker_field(
            field_cfg: Dict[str, Any],
            draw_img: Optional[np.ndarray],
            section_key: str,
        ) -> Tuple[bool, str]:
            if not marker_axis_for_decode:
                return False, ""
            field_type = str(field_cfg.get("type", "")).strip().lower()
            cfg = dict(field_cfg)
            if field_type == "marker_digit_columns":
                return self._decode_marker_digit_columns(
                    processed_img,
                    marker_axis_for_decode,
                    cfg,
                    scale,
                    draw_img,
                    section_key=section_key,
                    global_scale_x=global_scale_x,
                    global_scale_y=global_scale_y,
                )
            if field_type == "marker_single_choice_column":
                return self._decode_marker_single_choice_column(
                    processed_img,
                    marker_axis_for_decode,
                    cfg,
                    scale,
                    draw_img,
                    section_key=section_key,
                    global_scale_x=global_scale_x,
                    global_scale_y=global_scale_y,
                )
            return False, ""

        for field in normalized_fields:
            if not isinstance(field, dict):
                continue
            f_name = field.get("name")
            f_type = str(field.get("type", "")).strip().lower()
            if not f_name or not f_type:
                continue
            section_key = self._infer_field_section(field)
            if f_type == "marker_digit_columns":
                if not marker_axis_for_decode:
                    ok, val = False, ""
                else:
                    ok, val = _decode_marker_field(field, debug_img, section_key=section_key)
            elif f_type == "marker_single_choice_column":
                if not marker_axis_for_decode:
                    ok, val = False, ""
                else:
                    ok, val = _decode_marker_field(field, debug_img, section_key=section_key)
            else:
                # Marker-only mode: non-marker field types are intentionally unsupported.
                ok, val = False, ""

            if ok:
                info[str(f_name)] = val
            else:
                is_ok = False
        return is_ok, info, debug_img



