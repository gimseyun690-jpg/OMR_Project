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
    def __init__(
        self,
        block_size: int = 15,
        c_value: int = 7,
        red_cutoff: int = 180,
        open_kernel: int = 3,
    ):
        self.block_size = int(block_size) if int(block_size) % 2 == 1 else int(block_size) + 1
        self.c_value = int(c_value)
        self.red_cutoff = int(np.clip(int(red_cutoff), 0, 255))
        kernel = int(open_kernel)
        if kernel <= 0:
            kernel = 1
        if kernel % 2 == 0:
            kernel += 1
        self.open_kernel = int(kernel)

    def configure(
        self,
        block_size: Optional[int] = None,
        c_value: Optional[int] = None,
        red_cutoff: Optional[int] = None,
        open_kernel: Optional[int] = None,
    ) -> None:
        if block_size is not None:
            b = int(block_size)
            if b % 2 == 0:
                b += 1
            self.block_size = max(3, b)
        if c_value is not None:
            self.c_value = int(c_value)
        if red_cutoff is not None:
            self.red_cutoff = int(np.clip(int(red_cutoff), 0, 255))
        if open_kernel is not None:
            k = int(open_kernel)
            if k <= 0:
                k = 1
            if k % 2 == 0:
                k += 1
            self.open_kernel = int(k)

    def preprocess(self, img: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        [Final] Red channel high-contrast pipeline.
        Removes red form lines while preserving dark pencil/pen marks.
        """
        if img is None:
            return None, None
        work_img = img.copy()

        if len(work_img.shape) == 3:
            # 1) Use red channel only.
            red_channel = work_img[:, :, 2]

            # 2) Hard cutoff: bright pixels (paper + red print) -> white.
            contrast_img = red_channel.copy()
            contrast_img[contrast_img > int(self.red_cutoff)] = 255
            img_gray = contrast_img
        else:
            # Grayscale input fallback.
            img_gray = cv2.add(work_img, 30)

        block_size = int(self.block_size)
        if block_size % 2 == 0:
            block_size += 1
        block_size = max(3, block_size)
        c_value = int(self.c_value)

        # 3) Binarization (configured block_size/C).
        binary_img = cv2.adaptiveThreshold(
            img_gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            c_value,
        )

        # 4) Small-noise cleanup.
        kernel_size = int(self.open_kernel)
        if kernel_size % 2 == 0:
            kernel_size += 1
        kernel_size = max(1, kernel_size)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
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

    def roi_weighted_score(
        self,
        processed_img: Optional[np.ndarray],
        x: int,
        y: int,
        w: int,
        h: int,
        inner_ratio: float = 0.18,
        center_ratio: float = 0.55,
        center_weight: float = 0.72,
    ) -> Tuple[
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[Tuple[int, int, int, int]],
        Optional[Tuple[int, int, int, int]],
    ]:
        clamped = self.clamp_roi(processed_img, x, y, w, h)
        if clamped is None:
            return None, None, None, None, None
        raw_ratio, eval_roi = self.roi_fill_ratio(processed_img, x, y, w, h, inner_ratio=inner_ratio)
        if raw_ratio is None or eval_roi is None:
            return None, None, None, clamped, eval_roi

        ex, ey, ew, eh = eval_roi
        roi = processed_img[ey : ey + eh, ex : ex + ew]
        if roi is None or roi.size == 0:
            return None, None, None, clamped, eval_roi

        cr = float(center_ratio)
        if not np.isfinite(cr):
            cr = 0.55
        cr = float(np.clip(cr, 0.25, 0.90))
        cw = float(center_weight)
        if not np.isfinite(cw):
            cw = 0.72
        cw = float(np.clip(cw, 0.0, 1.0))

        cxm = int(round((1.0 - cr) * float(ew) * 0.5))
        cym = int(round((1.0 - cr) * float(eh) * 0.5))
        cx1 = max(0, cxm)
        cy1 = max(0, cym)
        cx2 = min(ew, ew - cxm)
        cy2 = min(eh, eh - cym)
        if cx2 <= cx1 or cy2 <= cy1:
            center_roi = roi
            center_rect = eval_roi
        else:
            center_roi = roi[cy1:cy2, cx1:cx2]
            center_rect = (ex + cx1, ey + cy1, cx2 - cx1, cy2 - cy1)
        c_area = float(center_roi.shape[0] * center_roi.shape[1])
        center_fill = float(cv2.countNonZero(center_roi)) / c_area if c_area > 0 else float(raw_ratio)

        weighted = ((1.0 - cw) * float(raw_ratio)) + (cw * float(center_fill))
        return float(weighted), float(raw_ratio), float(center_fill), clamped, center_rect

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
        ratio, eval_roi = self.roi_fill_ratio(
            processed_img,
            x,
            y,
            w,
            h,
            inner_ratio=0.18,
        )
        if clamped is None:
            return False, 0.0, None, None
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

    @staticmethod
    def _parse_finite_float(
        value: Any,
        default: float,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        try:
            parsed = float(value)
        except Exception:
            parsed = float(default)
        if not np.isfinite(parsed):
            parsed = float(default)
        if min_value is not None:
            parsed = max(float(min_value), parsed)
        if max_value is not None:
            parsed = min(float(max_value), parsed)
        return float(parsed)

    def _apply_marker_deskew(
        self,
        image: Optional[np.ndarray],
        markers: Sequence[Marker],
        marker_location: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[np.ndarray], List[Marker], bool]:
        marker_list = list(markers or [])
        if image is None or len(marker_list) < 2:
            return image, marker_list, False

        cfg = config if isinstance(config, dict) else {}
        enabled = self._to_bool(cfg.get("deskew_with_markers", False), False)
        if not enabled:
            return image, marker_list, False

        max_deg = self._parse_finite_float(cfg.get("deskew_max_deg", 8.0), 8.0, min_value=0.2, max_value=25.0)
        min_deg = self._parse_finite_float(cfg.get("deskew_min_deg", 0.05), 0.05, min_value=0.0, max_value=max_deg)
        inlier_pct = self._parse_finite_float(
            cfg.get("deskew_inlier_percentile", 85.0),
            85.0,
            min_value=60.0,
            max_value=98.0,
        )

        deskewed = self.geometry_manager.deskew_by_markers(
            image,
            marker_list,
            marker_location=marker_location,
            max_abs_deg=max_deg,
            min_abs_deg=min_deg,
            inlier_percentile=inlier_pct,
        )
        if deskewed is None or deskewed is image:
            return image, marker_list, False

        refreshed = list(
            self.marker_detector.find_markers(
                deskewed,
                location=marker_location,
                min_count=3,
            )
            or []
        )

        before_count = len(marker_list)
        min_required = max(3, min(before_count, 6))
        if len(refreshed) < min_required:
            return image, marker_list, False
        if before_count >= 6 and (len(refreshed) + 2) < before_count:
            return image, marker_list, False

        return deskewed, refreshed, True

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

        # Additional axis factors over base scale.
        x_factor = 1.0
        y_factor = 1.0
        img_h, img_w = work_img.shape[:2]

        # Layout fallback: current image size over configured layout size.
        # When marker normalization rotates the working image (e.g. top/bottom layouts),
        # compare against the orientation that best matches the current canvas.
        try:
            layout_w = float(config.get("width", config.get("layout_width", 0.0)))
        except Exception:
            layout_w = 0.0
        try:
            layout_h = float(config.get("height", config.get("layout_height", 0.0)))
        except Exception:
            layout_h = 0.0

        if layout_w > 0.0 and layout_h > 0.0:
            exp_w_a = float(layout_w) * float(scale_value)
            exp_h_a = float(layout_h) * float(scale_value)
            exp_w_b = float(layout_h) * float(scale_value)
            exp_h_b = float(layout_w) * float(scale_value)

            if exp_w_a > 1e-6 and exp_h_a > 1e-6 and exp_w_b > 1e-6 and exp_h_b > 1e-6:
                err_a = (abs(float(img_w) - exp_w_a) / exp_w_a) + (abs(float(img_h) - exp_h_a) / exp_h_a)
                err_b = (abs(float(img_w) - exp_w_b) / exp_w_b) + (abs(float(img_h) - exp_h_b) / exp_h_b)
                if err_b < err_a:
                    expected_w = exp_w_b
                    expected_h = exp_h_b
                else:
                    expected_w = exp_w_a
                    expected_h = exp_h_a
                x_factor = float(img_w) / float(expected_w)
                y_factor = float(img_h) / float(expected_h)
        else:
            if layout_w > 0.0:
                expected_w = float(layout_w) * float(scale_value)
                if expected_w > 1e-6:
                    x_factor = float(img_w) / float(expected_w)
            if layout_h > 0.0:
                expected_h = float(layout_h) * float(scale_value)
                if expected_h > 1e-6:
                    y_factor = float(img_h) / float(expected_h)

        loc = str(marker_location or "left").strip().lower()
        ordered = list(markers or [])
        if len(ordered) >= 2:
            ordered_x = sorted(ordered, key=lambda m: int(m.cx))
            ordered_y = sorted(ordered, key=lambda m: int(m.cy))
            measured_span_x = abs(float(ordered_x[-1].cx) - float(ordered_x[0].cx))
            measured_span_y = abs(float(ordered_y[-1].cy) - float(ordered_y[0].cy))

            # Dynamic axis classification (no hard orientation assumption).
            has_top_bottom = loc in ("top", "bottom")
            has_left_right = loc in ("left", "right")
            if measured_span_x > (measured_span_y * 1.25):
                has_top_bottom = True
                has_left_right = False
            elif measured_span_y > (measured_span_x * 1.25):
                has_left_right = True
                has_top_bottom = False
            elif not has_top_bottom and not has_left_right:
                has_top_bottom = measured_span_x >= measured_span_y
                has_left_right = not has_top_bottom

            if has_top_bottom and measured_span_x > 1e-6:
                try:
                    expected_span_x = float(
                        config.get(
                            "expected_marker_span_x",
                            config.get("expected_marker_span", 0.0),
                        )
                    )
                except Exception:
                    expected_span_x = 0.0
                if expected_span_x <= 0.0:
                    try:
                        marker_dx = float(config.get("marker_dx", config.get("marker_pitch", 0.0)))
                    except Exception:
                        marker_dx = 0.0
                    if marker_dx > 0.0:
                        expected_span_x = float(marker_dx) * float(max(1, len(ordered_x) - 1))
                expected_span_x = float(expected_span_x) * float(scale_value)
                if expected_span_x > 1e-6:
                    x_factor = float(measured_span_x) / float(expected_span_x)

            if has_left_right and measured_span_y > 1e-6:
                try:
                    expected_span_y = float(
                        config.get(
                            "expected_marker_span_y",
                            config.get("expected_marker_span", 0.0),
                        )
                    )
                except Exception:
                    expected_span_y = 0.0
                if expected_span_y <= 0.0:
                    try:
                        marker_dy = float(config.get("marker_dy", config.get("marker_pitch", 0.0)))
                    except Exception:
                        marker_dy = 0.0
                    if marker_dy > 0.0:
                        expected_span_y = float(marker_dy) * float(max(1, len(ordered_y) - 1))
                expected_span_y = float(expected_span_y) * float(scale_value)
                if expected_span_y > 1e-6:
                    y_factor = float(measured_span_y) / float(expected_span_y)

        if not np.isfinite(x_factor) or x_factor <= 0.0:
            x_factor = 1.0
        if not np.isfinite(y_factor) or y_factor <= 0.0:
            y_factor = 1.0
        x_factor = float(np.clip(x_factor, 0.5, 1.5))
        y_factor = float(np.clip(y_factor, 0.5, 1.5))

        return float(scale_value * x_factor), float(scale_value * y_factor)

    @staticmethod
    def _resolve_scaled_layout_canvas(
        cfg: Optional[Dict[str, Any]],
        img_w: int,
        img_h: int,
        base_scale: float,
    ) -> Tuple[float, float]:
        config = cfg if isinstance(cfg, dict) else {}
        try:
            layout_w = float(config.get("width", config.get("layout_width", 0.0)))
        except Exception:
            layout_w = 0.0
        try:
            layout_h = float(config.get("height", config.get("layout_height", 0.0)))
        except Exception:
            layout_h = 0.0
        if layout_w <= 0.0 or layout_h <= 0.0:
            return 0.0, 0.0

        s = float(base_scale)
        if not np.isfinite(s) or s <= 0.0:
            s = 1.0

        exp_w_a = float(layout_w) * s
        exp_h_a = float(layout_h) * s
        exp_w_b = float(layout_h) * s
        exp_h_b = float(layout_w) * s
        if exp_w_a <= 1e-6 or exp_h_a <= 1e-6 or exp_w_b <= 1e-6 or exp_h_b <= 1e-6:
            return 0.0, 0.0

        err_a = (abs(float(img_w) - exp_w_a) / exp_w_a) + (abs(float(img_h) - exp_h_a) / exp_h_a)
        err_b = (abs(float(img_w) - exp_w_b) / exp_w_b) + (abs(float(img_h) - exp_h_b) / exp_h_b)
        if err_b < err_a:
            return float(exp_w_b), float(exp_h_b)
        return float(exp_w_a), float(exp_h_a)

    @staticmethod
    def _vertical_page_gain(
        anchor_y: float,
        img_h: int,
        expected_h_scaled: float,
        expected_anchor_scaled: float = 0.0,
    ) -> float:
        expected_span = float(expected_h_scaled) - float(expected_anchor_scaled)
        measured_span = float(img_h) - float(anchor_y)
        if expected_span <= 1e-6 or measured_span <= 1e-6:
            return 1.0
        gain = float(measured_span) / float(expected_span)
        if not np.isfinite(gain) or gain <= 0.0:
            return 1.0
        return float(np.clip(gain, 0.5, 1.5))

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
    def _indexed_axis_coord(
        anchor: float,
        axis_offset: float,
        axis_step: float,
        axis_index: int,
        section_offset: float = 0.0,
    ) -> int:
        """Common linear index mapping: coord = anchor + offset + (index * step) + section_offset."""
        return int(
            round(
                float(anchor)
                + float(axis_offset)
                + (float(axis_index) * float(axis_step))
                + float(section_offset)
            )
        )

    @staticmethod
    def _markers_span_is_horizontal(markers: Sequence[Marker]) -> bool:
        if len(markers) < 2:
            return False
        span_x = float(max(int(m.cx) for m in markers) - min(int(m.cx) for m in markers))
        span_y = float(max(int(m.cy) for m in markers) - min(int(m.cy) for m in markers))
        return span_x >= span_y

    def _marker_anchor_y(self, markers: Sequence[Marker], marker: Marker, anchor_y_mode: str = "median") -> float:
        mode = str(anchor_y_mode or "").strip().lower()
        if mode == "median" and self._markers_span_is_horizontal(markers):
            try:
                return float(np.median(np.asarray([float(m.cy) for m in markers], dtype=np.float32)))
            except Exception:
                return float(marker.cy)
        return float(marker.cy)

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

            rotated_img, markers, _ = self._apply_marker_deskew(
                rotated_img,
                markers,
                marker_location=marker_location,
                config=layout,
            )

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

            col_anchor_map: Dict[int, Marker] = {}
            row_anchor_map: Dict[int, Marker] = {}
            if is_horizontal_target:
                needed_cols = sorted({int(item["col_index"]) for item in prepared})
                if not needed_cols or needed_cols[0] < 0:
                    return "ERR", [], debug_img, "TIMING_MARK"

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
            else:
                needed_rows = sorted({int(item["row_index"]) for item in prepared})
                if not needed_rows or needed_rows[0] < 0:
                    return "ERR", [], debug_img, "TIMING_MARK"

                for row_idx in needed_rows:
                    idx0 = (marker_start_index - 1) + row_idx
                    if not (0 <= idx0 < len(marks_by_y)):
                        return "ERR", [], debug_img, "TIMING_MARK"
                    row_anchor_map[row_idx] = marks_by_y[idx0]
            marker_axis = marks_by_x if is_horizontal_target else marks_by_y
            geom_scale_x, geom_scale_y = self._compute_global_scale_factors(
                work_img,
                marker_axis,
                marker_location,
                scale,
                cfg=layout,
            )

            # Unified geometry:
            # target = anchor + (config_offset * global_scale) + (config_offset * section_offset)
            x_offset = self._scaled_config_offset("question", float(layout.get("x_offset", 600)), geom_scale_x)
            raw_choice_dx = float(layout.get("choice_dx", 70))
            effective_choice_dx = float(raw_choice_dx) * float(geom_scale_x)
            box_w = max(1, int(round(float(layout.get("box_w", 40)) * geom_scale_x)))
            box_h = max(1, int(round(float(layout.get("box_h", 40)) * geom_scale_y)))
            row_offset_y = self._scaled_config_offset("question", float(layout.get("row_offset_y", 0)), geom_scale_y)
            row_start_y = self._scaled_config_offset("question", float(layout.get("row_start_y", 360)), geom_scale_y)
            raw_row_dy = float(layout.get("row_dy", 70))
            effective_row_dy = float(raw_row_dy) * float(geom_scale_y)
            question_off_x, question_off_y = self._combined_offset("question")
            expected_w_scaled, expected_h_scaled = self._resolve_scaled_layout_canvas(
                layout,
                img_w=int(work_img.shape[1]),
                img_h=int(work_img.shape[0]),
                base_scale=float(scale),
            )
            try:
                expected_anchor_y = float(
                    layout.get(
                        "expected_anchor_y",
                        layout.get("top_marker_y", layout.get("anchor_top_y", 0.0)),
                    )
                )
            except Exception:
                expected_anchor_y = 0.0
            expected_anchor_y_scaled = float(expected_anchor_y) * float(geom_scale_y)
            use_page_end_y_correction = self._to_bool(
                layout.get("page_end_y_correction", is_horizontal_target),
                is_horizontal_target,
            )
            try:
                mark_threshold = float(layout.get("mark_threshold", self.pixel_threshold))
            except Exception:
                mark_threshold = float(self.pixel_threshold)
            if (not np.isfinite(mark_threshold)) or mark_threshold <= 0.0:
                mark_threshold = float(self.pixel_threshold)

            try:
                score_inner_ratio = float(layout.get("score_inner_ratio", 0.18))
            except Exception:
                score_inner_ratio = 0.18
            score_inner_ratio = float(np.clip(score_inner_ratio, 0.0, 0.45))

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
                    anchor_y = float(base_mark.cy) if row_start_from_marker else 0.0
                    relative_y = (float(row_start_y) + float(row_offset_y)) + (
                        float(row_in_col) * float(effective_row_dy)
                    )
                    if use_page_end_y_correction and expected_h_scaled > 1e-6:
                        page_gain = self._vertical_page_gain(
                            anchor_y=anchor_y,
                            img_h=int(work_img.shape[0]),
                            expected_h_scaled=float(expected_h_scaled),
                            expected_anchor_scaled=float(expected_anchor_y_scaled if row_start_from_marker else 0.0),
                        )
                        target_cy = int(round(anchor_y + (float(relative_y) * float(page_gain)) + float(question_off_y)))
                    else:
                        target_cy = self._indexed_axis_coord(
                            anchor=float(anchor_y),
                            axis_offset=(float(row_start_y) + float(row_offset_y)),
                            axis_step=float(effective_row_dy),
                            axis_index=row_in_col,
                            section_offset=float(question_off_y),
                        )
                    start_y = int(round(target_cy - (box_h / 2.0)))
                else:
                    row_index = int(item["row_index"])
                    if row_index not in row_anchor_map:
                        return "ERR", [], debug_img, "TIMING_MARK"
                    base_mark = row_anchor_map[row_index]
                    base_cx = float(base_mark.cx)
                    if row_start_from_marker:
                        target_cy = self._indexed_axis_coord(
                            anchor=float(base_mark.cy),
                            axis_offset=(float(row_start_y) + float(row_offset_y)),
                            axis_step=0.0,
                            axis_index=0,
                            section_offset=float(question_off_y),
                        )
                    else:
                        target_cy = self._indexed_axis_coord(
                            anchor=0.0,
                            axis_offset=(float(row_start_y) + float(row_offset_y)),
                            axis_step=float(effective_row_dy),
                            axis_index=row_index,
                            section_offset=float(question_off_y),
                        )
                    start_y = int(round(target_cy - (box_h / 2.0)))

                rois: List[Tuple[int, int, int, int]] = []
                for c_idx in range(choices_count):
                    rx = self._indexed_axis_coord(
                        anchor=float(base_cx),
                        axis_offset=float(x_offset),
                        axis_step=float(effective_choice_dx),
                        axis_index=c_idx,
                        section_offset=float(question_off_x),
                    )
                    rois.append((rx, int(start_y), int(box_w), int(box_h)))

                roi_scores: List[float] = []
                roi_clamped: List[Optional[Tuple[int, int, int, int]]] = []
                for r_idx, (rx, ry, rw, rh) in enumerate(rois):
                    clamped = self.image_processor.clamp_roi(processed_img, rx, ry, rw, rh)
                    ratio, _ = self.image_processor.roi_fill_ratio(
                        processed_img,
                        rx,
                        ry,
                        rw,
                        rh,
                        inner_ratio=score_inner_ratio,
                    )
                    score = float(ratio) if ratio is not None else 0.0
                    roi_scores.append(score)
                    roi_clamped.append(clamped)
                    if debug_img is not None and clamped is not None:
                        x1, y1, w1, h1 = clamped
                        color = (0, 255, 0) if score >= mark_threshold else (0, 0, 255)
                        cv2.rectangle(debug_img, (x1, y1), (x1 + w1, y1 + h1), color, 1)
                        cv2.putText(
                            debug_img,
                            f"{int(score * 100)}",
                            (x1, y1 + h1 - 2),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.3,
                            color,
                            1,
                        )

                marked_indices: List[int] = [int(i) for i, s in enumerate(roi_scores) if s >= mark_threshold]

                if debug_img is not None and marked_indices:
                    for mi in marked_indices:
                        if 0 <= int(mi) < len(roi_clamped):
                            rc = roi_clamped[int(mi)]
                            if rc is None:
                                continue
                            x1, y1, w1, h1 = rc
                            c = (0, 255, 0) if len(marked_indices) == 1 else (0, 165, 255)
                            cv2.rectangle(debug_img, (x1, y1), (x1 + w1, y1 + h1), c, 2)

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

        hits = 0
        picked = ""
        for item in prepared:
            x = int(round(float(item["x"]) * float(scale) + float(off_x)))
            y = int(round(float(item["y"]) * float(scale) + float(off_y)))
            w = int(item["w"])
            h = int(item["h"])
            if self._check_roi(processed_img, x, y, w, h, debug_img, (255, 0, 255)):
                hits += 1
                picked = str(item["label"])
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
        layout_cfg: Optional[Dict[str, Any]] = None,
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
        raw_row_dy = float(cfg.get("row_dy", cfg.get("row_h", 20)))
        effective_row_dy = float(raw_row_dy) * float(scale_y)
        box_w = max(1, int(round(float(cfg.get("box_w", 40)) * float(scale_x))))
        box_h = max(1, int(round(float(cfg.get("box_h", 40)) * float(scale_y))))
        off_x, off_y = self._combined_offset(section_key)

        anchor_y_mode = str(cfg.get("anchor_y_mode", "median")).strip().lower()
        expected_w_scaled, expected_h_scaled = self._resolve_scaled_layout_canvas(
            layout_cfg,
            img_w=int(processed_img.shape[1]),
            img_h=int(processed_img.shape[0]),
            base_scale=float(scale),
        )
        try:
            expected_anchor_y = float(
                cfg.get(
                    "expected_anchor_y",
                    (layout_cfg or {}).get(
                        "expected_anchor_y",
                        (layout_cfg or {}).get("top_marker_y", (layout_cfg or {}).get("anchor_top_y", 0.0)),
                    ),
                )
            )
        except Exception:
            expected_anchor_y = 0.0
        expected_anchor_y_scaled = float(expected_anchor_y) * float(scale_y)
        use_page_end_y_correction = self._to_bool(
            cfg.get("page_end_y_correction", self._markers_span_is_horizontal(markers)),
            self._markers_span_is_horizontal(markers),
        )

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
            base_cy = self._marker_anchor_y(markers, base, anchor_y_mode=anchor_y_mode)
            page_gain = 1.0
            if use_page_end_y_correction and expected_h_scaled > 1e-6:
                page_gain = self._vertical_page_gain(
                    anchor_y=float(base_cy),
                    img_h=int(processed_img.shape[0]),
                    expected_h_scaled=float(expected_h_scaled),
                    expected_anchor_scaled=float(expected_anchor_y_scaled),
                )
            best_r = -1
            best_ratio = -1.0
            best_rect: Optional[Tuple[int, int, int, int]] = None
            hits = 0
            for r_idx in range(rows):
                relative_y = float(y_offset) + (float(r_idx) * float(effective_row_dy))
                center_y = int(round(float(base_cy) + (float(relative_y) * float(page_gain)) + float(off_y)))
                rx = int(center_x - (box_w // 2))
                ry = int(center_y - (box_h // 2))
                marked, ratio, clamped, _ = self.image_processor.check_roi(
                    processed_img, rx, ry, box_w, box_h, self.pixel_threshold
                )
                if debug_img is not None:
                    if clamped is not None:
                        x1, y1, w1, h1 = clamped
                        color = (0, 255, 0) if marked else (0, 0, 255)
                        cv2.rectangle(debug_img, (x1, y1), (x1 + w1, y1 + h1), color, 1)
                if marked:
                    hits += 1
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_r = r_idx
                        best_rect = clamped
            if debug_img is not None and best_r >= 0 and best_rect is not None:
                x1, y1, w1, h1 = best_rect
                color = (0, 255, 0) if hits == 1 else (0, 0, 255)
                cv2.rectangle(debug_img, (x1, y1), (x1 + w1, y1 + h1), color, 2)
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
        layout_cfg: Optional[Dict[str, Any]] = None,
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
        raw_choice_dy = float(cfg.get("choice_dy", cfg.get("row_dy", 40)))
        effective_choice_dy = float(raw_choice_dy) * float(scale_y)
        raw_choice_offsets = cfg.get("choice_y_offsets", [])
        choice_offsets: List[float] = []
        if isinstance(raw_choice_offsets, list):
            for value in raw_choice_offsets:
                try:
                    choice_offsets.append(float(value) * float(scale_y))
                except Exception:
                    continue
        box_w = max(1, int(round(float(cfg.get("box_w", 40)) * float(scale_x))))
        box_h = max(1, int(round(float(cfg.get("box_h", 40)) * float(scale_y))))
        off_x, off_y = self._combined_offset(section_key)
        expected_w_scaled, expected_h_scaled = self._resolve_scaled_layout_canvas(
            layout_cfg,
            img_w=int(processed_img.shape[1]),
            img_h=int(processed_img.shape[0]),
            base_scale=float(scale),
        )
        try:
            expected_anchor_y = float(
                cfg.get(
                    "expected_anchor_y",
                    (layout_cfg or {}).get(
                        "expected_anchor_y",
                        (layout_cfg or {}).get("top_marker_y", (layout_cfg or {}).get("anchor_top_y", 0.0)),
                    ),
                )
            )
        except Exception:
            expected_anchor_y = 0.0
        expected_anchor_y_scaled = float(expected_anchor_y) * float(scale_y)
        use_page_end_y_correction = self._to_bool(
            cfg.get("page_end_y_correction", self._markers_span_is_horizontal(markers)),
            self._markers_span_is_horizontal(markers),
        )

        base = markers[marker_index]
        center_x = int(round(float(base.cx) + float(x_offset) + float(off_x)))
        anchor_y_mode = str(cfg.get("anchor_y_mode", "median")).strip().lower()
        base_cy = self._marker_anchor_y(markers, base, anchor_y_mode=anchor_y_mode)
        page_gain = 1.0
        if use_page_end_y_correction and expected_h_scaled > 1e-6:
            page_gain = self._vertical_page_gain(
                anchor_y=float(base_cy),
                img_h=int(processed_img.shape[0]),
                expected_h_scaled=float(expected_h_scaled),
                expected_anchor_scaled=float(expected_anchor_y_scaled),
            )
        hits = 0
        picked = ""
        for idx, label in enumerate(labels):
            relative_y = float(y_offset)
            if idx < len(choice_offsets):
                relative_y += float(choice_offsets[idx])
            elif idx < len(per_choice_offsets) and per_choice_offsets[idx] is not None:
                relative_y += float(per_choice_offsets[idx]) * float(scale_y)
            else:
                relative_y += float(idx) * float(effective_choice_dy)
            center_y = int(round(float(base_cy) + (float(relative_y) * float(page_gain)) + float(off_y)))
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
            field_cfg.setdefault("section", key)
            fields.append(field_cfg)

        if not fields:
            return False, {}, None
        return self.analyze_custom_fields(original_img, fields, scale=scale, layout=config)

    def analyze_custom_fields(
        self,
        original_img: Optional[np.ndarray],
        fields: Sequence[Dict[str, Any]],
        scale: float = 1.0,
        layout: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any], Optional[np.ndarray]]:
        if original_img is None or not fields:
            return False, {}, None

        full_layout = layout if isinstance(layout, dict) else {}
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

            deskew_cfg = dict(full_layout)
            for key in ("deskew_with_markers", "deskew_max_deg", "deskew_min_deg", "deskew_inlier_percentile"):
                if marker_field.get(key) is not None:
                    deskew_cfg[key] = marker_field.get(key)
            base_img, markers, _ = self._apply_marker_deskew(
                base_img,
                markers,
                marker_location=marker_location,
                config=deskew_cfg,
            )

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

        global_scale_x, global_scale_y = self._compute_global_scale_factors(
            work_img,
            marker_axis_for_decode,
            marker_location,
            scale,
            cfg=full_layout,
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
                    layout_cfg=full_layout,
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
                    layout_cfg=full_layout,
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
