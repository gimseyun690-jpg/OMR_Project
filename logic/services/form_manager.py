from __future__ import annotations

from utils.text_io import read_json
from logic.form_loader import build_rois_from_form


class FormManager:
    """폼 로딩 + ROI 생성(DPI 스케일 반영) 담당."""
    def __init__(self):
        self.form_path: str | None = None
        self.form_data: dict | None = None

    def load(self, form_path: str | None):
        self.form_path = form_path
        self.form_data = None
        if form_path:
            self.form_data = read_json(form_path)
        return self.form_data

    def get_layout_mode(self) -> str:
        if isinstance(self.form_data, dict):
            return self.form_data.get("layout_mode", "fixed")
        return "fixed"

    def get_sheet_code(self) -> str:
        if isinstance(self.form_data, dict):
            return (
                self.form_data.get("form_no")
                or self.form_data.get("sheet_code")
                or self.form_data.get("form_id")
                or "Unknown"
            )
        return "Unknown"

    def get_omr_params(self) -> tuple[int, float]:
        if isinstance(self.form_data, dict):
            omr = self.form_data.get("omr", {}) if isinstance(self.form_data.get("omr", {}), dict) else {}
            thresh = int(float(omr.get("threshold", 140)))
            ratio = float(omr.get("pixel_ratio", 0.05))
            return thresh, ratio
        return 140, 0.05

    def get_base_dpi(self) -> int:
        if isinstance(self.form_data, dict):
            val = self.form_data.get("dpi") or self.form_data.get("base_dpi")
            try:
                return int(val)
            except Exception:
                return 150
        return 150

    def get_fixed_rois(self, scale: float = 1.0):
        if not isinstance(self.form_data, dict):
            return []
        return build_rois_from_form(self.form_data, scale=scale)

    def get_side_marker_params(self, scale: float = 1.0):
        if not isinstance(self.form_data, dict):
            return 40, 40, 600, 750
        roi_params = self.form_data.get("roi_params", {})
        if not isinstance(roi_params, dict):
            roi_params = {}
        box_w = int(roi_params.get("box_w", 40))
        box_h = int(roi_params.get("box_h", 40))
        dist_agree = int(roi_params.get("marker_to_agree_dist", 600))
        dist_disagree = int(roi_params.get("marker_to_disagree_dist", 750))
        if scale != 1.0:
            box_w = int(round(box_w * scale))
            box_h = int(round(box_h * scale))
            dist_agree = int(round(dist_agree * scale))
            dist_disagree = int(round(dist_disagree * scale))
        return box_w, box_h, dist_agree, dist_disagree
