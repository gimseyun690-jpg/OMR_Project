from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from logic.geometry import GeometryManager
from logic.marker_detector import MarkerDetector
from logic.omr_types import Marker
from logic.scanner import ImageProcessor, OMRScanner


class OMREngine:
    def __init__(self):
        self.width = 1240
        self.height = 1754

        self.block_size = 15
        self.C = 7
        self.pixel_threshold = 0.05
        self.marker_thresh = 215
        # Legacy alias for older code paths that still refer to threshold_value.
        self.threshold_value = self.marker_thresh
        self.global_offset_x = 0
        self.global_offset_y = 0
        self.exam_no_offset_x = 0
        self.exam_no_offset_y = 0
        self.birth_offset_x = 0
        self.birth_offset_y = 0
        self.name_offset_x = 0
        self.name_offset_y = 0
        self.subject_offset_x = 0
        self.subject_offset_y = 0
        self.question_offset_x = 0
        self.question_offset_y = 0
        self.exam_no_offset = 0.0
        self.birth_offset = 0.0
        self.name_offset = 0.0
        self.subject_offset = 0.0
        self.questions_offset = 0.0
        self.marker_detection: Dict[str, Any] = {}

        self.image_processor = ImageProcessor(block_size=self.block_size, c_value=self.C)
        self.geometry_manager = GeometryManager(width=self.width, height=self.height)
        self.marker_detector = MarkerDetector(marker_thresh=self.marker_thresh)
        self.scanner = OMRScanner(
            image_processor=self.image_processor,
            marker_detector=self.marker_detector,
            geometry_manager=self.geometry_manager,
            pixel_threshold=self.pixel_threshold,
            global_offset_x=self.global_offset_x,
            global_offset_y=self.global_offset_y,
        )

    def configure(
        self,
        *args: Any,
        block_size: Optional[int] = None,
        pixel_ratio: Optional[float] = None,
        marker_thresh: Optional[int] = None,
        C: Optional[int] = None,
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
        marker_detection: Optional[Dict[str, Any]] = None,
        threshold: Optional[int] = None,
        c_value: Optional[int] = None,
    ) -> None:
        if len(args) > 4:
            raise TypeError(f"configure() takes up to 4 positional arguments but {len(args)} were given")

        positional = list(args)
        if positional and len(positional) in (1, 2) and marker_thresh is None and threshold is None:
            try:
                first_value = int(float(positional[0]))
            except Exception:
                first_value = None
            # Legacy pattern: configure(threshold, pixel_ratio)
            if first_value is not None and first_value >= 50:
                threshold = first_value
                if len(positional) >= 2 and pixel_ratio is None:
                    pixel_ratio = float(positional[1])
                positional = []

        if positional:
            if len(positional) >= 1 and block_size is None:
                block_size = positional[0]
            if len(positional) >= 2 and pixel_ratio is None:
                pixel_ratio = positional[1]
            if len(positional) >= 3 and marker_thresh is None:
                marker_thresh = positional[2]
            if len(positional) >= 4 and C is None:
                C = positional[3]

        if threshold is not None and marker_thresh is None:
            marker_thresh = threshold
        if c_value is not None and C is None:
            C = c_value

        if block_size is not None:
            b = int(block_size)
            if b % 2 == 0:
                b += 1
            self.block_size = max(3, b)
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
        if exam_no_offset_x is not None:
            self.exam_no_offset_x = int(exam_no_offset_x)
        if exam_no_offset_y is not None:
            self.exam_no_offset_y = int(exam_no_offset_y)
        if birth_offset_x is not None:
            self.birth_offset_x = int(birth_offset_x)
        if birth_offset_y is not None:
            self.birth_offset_y = int(birth_offset_y)
        if name_offset_x is not None:
            self.name_offset_x = int(name_offset_x)
        if name_offset_y is not None:
            self.name_offset_y = int(name_offset_y)
        if subject_offset_x is not None:
            self.subject_offset_x = int(subject_offset_x)
        if subject_offset_y is not None:
            self.subject_offset_y = int(subject_offset_y)
        if question_offset_x is not None:
            self.question_offset_x = int(question_offset_x)
        if question_offset_y is not None:
            self.question_offset_y = int(question_offset_y)
        if exam_no_offset is not None:
            self.exam_no_offset = float(exam_no_offset)
        if birth_offset is not None:
            self.birth_offset = float(birth_offset)
        if name_offset is not None:
            self.name_offset = float(name_offset)
        if subject_offset is not None:
            self.subject_offset = float(subject_offset)
        if questions_offset is not None:
            self.questions_offset = float(questions_offset)
        if isinstance(marker_detection, dict):
            self.marker_detection = dict(marker_detection)
        self.threshold_value = int(self.marker_thresh)

        self.image_processor.configure(block_size=self.block_size, c_value=self.C)
        self.marker_detector.configure(marker_thresh=self.marker_thresh)
        self.scanner.configure(
            pixel_threshold=self.pixel_threshold,
            global_offset_x=self.global_offset_x,
            global_offset_y=self.global_offset_y,
            exam_no_offset_x=self.exam_no_offset_x,
            exam_no_offset_y=self.exam_no_offset_y,
            birth_offset_x=self.birth_offset_x,
            birth_offset_y=self.birth_offset_y,
            name_offset_x=self.name_offset_x,
            name_offset_y=self.name_offset_y,
            subject_offset_x=self.subject_offset_x,
            subject_offset_y=self.subject_offset_y,
            question_offset_x=self.question_offset_x,
            question_offset_y=self.question_offset_y,
            exam_no_offset=self.exam_no_offset,
            birth_offset=self.birth_offset,
            name_offset=self.name_offset,
            subject_offset=self.subject_offset,
            questions_offset=self.questions_offset,
        )

    def load_image(self, image_path: str) -> Optional[np.ndarray]:
        if not os.path.exists(image_path):
            return None
        img_array = np.fromfile(image_path, np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)

    def parse_config(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(config, dict):
            return []
        layout_defaults = config.get("layout_defaults", {})
        if not isinstance(layout_defaults, dict):
            layout_defaults = {}
        question_groups = config.get("question_groups", [])
        if not isinstance(question_groups, list):
            return []

        expanded: List[Dict[str, Any]] = []
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

            group_overrides = {k: v for k, v in group.items() if k not in ("start_no", "count", "start_row_index")}
            for i in range(count):
                q = dict(layout_defaults)
                q.update(group_overrides)
                q["no"] = start_no + i
                q["row_index"] = start_row_index + i
                expanded.append(q)
        return expanded

    @staticmethod
    def reorder(my_points: np.ndarray) -> np.ndarray:
        pts = my_points.reshape((4, 2))
        pts_new = np.zeros((4, 1, 2), np.int32)
        add = pts.sum(1)
        pts_new[0] = pts[np.argmin(add)]
        pts_new[2] = pts[np.argmax(add)]
        diff = np.diff(pts, axis=1)
        pts_new[1] = pts[np.argmin(diff)]
        pts_new[3] = pts[np.argmax(diff)]
        return pts_new

    def align_image(
        self,
        img: Optional[np.ndarray],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[np.ndarray], bool, str]:
        del json_data
        return self.geometry_manager.align_image(img)

    def align_image_warp(self, img: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], bool, str]:
        return self.align_image(img)

    def _clamp_roi(self, image: Optional[np.ndarray], x: int, y: int, w: int, h: int) -> Optional[Tuple[int, int, int, int]]:
        return self.image_processor.clamp_roi(image, x, y, w, h)

    def _roi_fill_ratio(
        self,
        processed_img: Optional[np.ndarray],
        x: int,
        y: int,
        w: int,
        h: int,
        inner_ratio: float = 0.18,
    ) -> Tuple[Optional[float], Optional[Tuple[int, int, int, int]]]:
        return self.image_processor.roi_fill_ratio(processed_img, x, y, w, h, inner_ratio=inner_ratio)

    def _preprocess_image(self, img: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        return self.image_processor.preprocess(img)

    def get_marking_score(self, image: Optional[np.ndarray], x: int, y: int, w: int, h: int) -> int:
        clamped = self._clamp_roi(image, x, y, w, h)
        if clamped is None:
            return 0
        rx, ry, rw, rh = clamped
        roi = image[ry : ry + rh, rx : rx + rw]
        if roi is None or roi.size == 0:
            return 0
        if len(roi.shape) == 2:
            gray_roi = roi
        else:
            gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray_roi, int(self.threshold_value), 255, cv2.THRESH_BINARY_INV)
        return int(cv2.countNonZero(mask))

    @staticmethod
    def _markers_to_dict(markers: Iterable[Marker]) -> List[Dict[str, Any]]:
        return [m.as_dict() for m in markers]

    @staticmethod
    def _markers_from_any(markers: Iterable[Any]) -> List[Marker]:
        return [Marker.from_obj(m) for m in markers]

    def find_markers(self, image: Optional[np.ndarray], location: str = "left", min_count: int = 3) -> List[Dict[str, Any]]:
        markers = self.marker_detector.find_markers(image, location=location, min_count=min_count)
        return self._markers_to_dict(markers)

    def find_side_markers(
        self,
        image: Optional[np.ndarray],
        min_area: Optional[int] = None,
        max_area: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        del min_area, max_area
        return self.find_markers(image, location="left", min_count=3)

    def normalize_orientation(
        self,
        image: Optional[np.ndarray],
        expected_location: str = "left",
        min_count: int = 3,
    ) -> Tuple[Optional[np.ndarray], List[Dict[str, Any]]]:
        rotated, markers = self.marker_detector.normalize_orientation(image, expected_location=expected_location, min_count=min_count)
        return rotated, self._markers_to_dict(markers)

    def ensure_correct_orientation(
        self,
        image: Optional[np.ndarray],
        expected_location: str = "left",
        min_keep: int = 3,
        prefer_multiplier: float = 1.3,
    ) -> Tuple[Optional[np.ndarray], List[Dict[str, Any]]]:
        del min_keep, prefer_multiplier
        return self.normalize_orientation(image, expected_location=expected_location, min_count=3)

    def ensure_gross_rotation(self, original_img: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], int, List[Dict[str, Any]]]:
        rotated, markers = self.normalize_orientation(original_img, expected_location="left", min_count=3)
        return rotated, 0, markers

    def _interpolate_missing_marks(self, markers: Sequence[Any]) -> List[Dict[str, Any]]:
        marker_objs = self._markers_from_any(markers or [])
        return self._markers_to_dict(self.marker_detector.interpolate_missing_marks(marker_objs))

    def _sample_markers_evenly(
        self,
        markers_sorted: Sequence[Any],
        target_count: int,
        axis_key: str = "cx",
    ) -> List[Dict[str, Any]]:
        marker_objs = self._markers_from_any(markers_sorted or [])
        sampled = self.marker_detector.sample_evenly(marker_objs, target_count=target_count, axis_key=axis_key)
        return self._markers_to_dict(sampled)

    def correct_rotation_by_markers(
        self,
        image: Optional[np.ndarray],
        rows: Sequence[float],
        xs_list: Sequence[float],
    ) -> Optional[np.ndarray]:
        return self.geometry_manager.deskew_from_rows(image, rows, xs_list)

    def deskew_by_markers(
        self,
        image: Optional[np.ndarray],
        markers: Sequence[Any],
        marker_location: str = "left",
    ) -> Optional[np.ndarray]:
        marker_objs = self._markers_from_any(markers or [])
        return self.geometry_manager.deskew_by_markers(image, marker_objs, marker_location=marker_location)

    def _fit_marker_line(self, rows: Sequence[float], xs_list: Sequence[float]) -> Optional[Dict[str, Any]]:
        return self.geometry_manager._fit_marker_line(rows, xs_list)

    def analyze_sheet_cv(
        self,
        original_img: Optional[np.ndarray],
        questions_rois: Sequence[Sequence[Tuple[int, int, int, int]]],
        ref_anchor: Optional[Any] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray]]:
        return self.scanner.analyze_sheet_cv(original_img, questions_rois, ref_anchor=ref_anchor)

    def analyze_marker_questions(
        self,
        original_img: Optional[np.ndarray],
        questions: Sequence[Dict[str, Any]],
        layout: Dict[str, Any],
        scale: float = 1.0,
        marker_location: str = "left",
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray], str]:
        return self.scanner.analyze_marker_questions(
            original_img=original_img,
            questions=questions,
            layout=layout or {},
            scale=scale,
            marker_location=marker_location,
        )

    def analyze_candidate_info(
        self,
        original_img: Optional[np.ndarray],
        config: Dict[str, Any],
        scale: float = 1.0,
    ) -> Tuple[bool, Dict[str, Any], Optional[np.ndarray]]:
        return self.scanner.analyze_candidate_info(original_img, config, scale=scale)

    def analyze_custom_fields(
        self,
        original_img: Optional[np.ndarray],
        fields: Sequence[Dict[str, Any]],
        scale: float = 1.0,
        layout: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Dict[str, Any], Optional[np.ndarray]]:
        return self.scanner.analyze_custom_fields(original_img, fields, scale=scale, layout=layout)

    def _check_roi(
        self,
        processed_img: Optional[np.ndarray],
        x: int,
        y: int,
        w: int,
        h: int,
        debug_img: Optional[np.ndarray],
        color: Tuple[int, int, int],
    ) -> bool:
        return self.scanner._check_roi(processed_img, x, y, w, h, debug_img, color)

    def _determine_status(self, marked_indices: Sequence[int]) -> str:
        return self.scanner._determine_status(marked_indices)

    def _draw_error_box(self, debug_img: Optional[np.ndarray], rois: Sequence[Tuple[int, int, int, int]]) -> None:
        self.scanner._draw_error_box(debug_img, rois)

    def _decode_single_choice(
        self,
        processed_img: Optional[np.ndarray],
        cfg: Dict[str, Any],
        scale: float,
        debug_img: Optional[np.ndarray],
    ) -> Tuple[bool, str]:
        return self.scanner._decode_single_choice(processed_img, cfg, scale, debug_img)

    def _decode_marker_digit_columns(
        self,
        processed_img: Optional[np.ndarray],
        markers: Sequence[Any],
        cfg: Dict[str, Any],
        scale: float,
        debug_img: Optional[np.ndarray],
    ) -> Tuple[bool, str]:
        marker_objs = self._markers_from_any(markers or [])
        return self.scanner._decode_marker_digit_columns(processed_img, marker_objs, cfg, scale, debug_img)

    def _decode_marker_single_choice_column(
        self,
        processed_img: Optional[np.ndarray],
        markers: Sequence[Any],
        cfg: Dict[str, Any],
        scale: float,
        debug_img: Optional[np.ndarray],
    ) -> Tuple[bool, str]:
        marker_objs = self._markers_from_any(markers or [])
        return self.scanner._decode_marker_single_choice_column(processed_img, marker_objs, cfg, scale, debug_img)

    def _legacy_analyze_sheet_cv(
        self,
        original_img: Optional[np.ndarray],
        questions_rois: Sequence[Sequence[Tuple[int, int, int, int]]],
        ref_anchor: Optional[Any] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray]]:
        return self.analyze_sheet_cv(original_img, questions_rois, ref_anchor=ref_anchor)

    def analyze_sheet(
        self,
        image_or_path: Any,
        rois: Sequence[Sequence[Tuple[int, int, int, int]]],
        ref_anchor: Optional[Any] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Optional[np.ndarray]]:
        if isinstance(image_or_path, str):
            img = self.load_image(image_or_path)
        else:
            img = image_or_path
        return self.analyze_sheet_cv(img, rois, ref_anchor=ref_anchor)
