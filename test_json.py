import sys
import os

# Ensure Qt plugins are found when using PySide2 dialogs
import PySide2
plugin_path = os.path.join(os.path.dirname(PySide2.__file__), "Qt", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path

import cv2
from PySide2.QtWidgets import QApplication

from logic.omr_engine import OMREngine
from logic.form_loader import build_rois_from_form
from utils.text_io import read_json

try:
    from ui.scanner.popups.error_editor import ErrorCorrectionDialog
except Exception:
    ErrorCorrectionDialog = None

# ------------------------------------------------------------
# Quick JSON-based test runner
# - Set FORM_JSON and IMAGE_PATH
# - Supports marker schema and legacy side_marker
# ------------------------------------------------------------
FORM_JSON = os.path.join("resources", "forms", "OMR_V1_vote_300dpi_4q.json")
IMAGE_PATH = os.path.join("data", "scan_images", "100001.jpg")
SHOW_UI = True
SAVE_DEBUG = True
DEBUG_OUT = "check_json.jpg"


def _get_scale(form_data: dict) -> float:
    base_dpi = int(form_data.get("dpi") or form_data.get("base_dpi") or 150)
    engine_base_dpi = 150
    if base_dpi <= 0:
        return 1.0
    return float(engine_base_dpi) / float(base_dpi)


def main():
    print("--- JSON test start ---")
    if not os.path.exists(FORM_JSON):
        print(f"[ERROR] form json not found: {FORM_JSON}")
        return
    if not os.path.exists(IMAGE_PATH):
        print(f"[ERROR] image not found: {IMAGE_PATH}")
        return

    form_data = read_json(FORM_JSON)
    if not isinstance(form_data, dict):
        print("[ERROR] invalid form json")
        return

    engine = OMREngine()
    img = engine.load_image(IMAGE_PATH)
    if img is None:
        print("[ERROR] failed to load image")
        return

    # Align to engine base size
    aligned_img, align_ok, align_reason = engine.align_image(img)
    if aligned_img is None:
        print(f"[ERROR] align failed: {align_reason}")
        return

    scale = _get_scale(form_data)
    layout_mode = form_data.get("layout_mode", "fixed")

    if layout_mode == "side_marker":
        questions = []
        raw_questions = form_data.get("questions", [])
        if isinstance(raw_questions, list):
            for i, q in enumerate(raw_questions):
                item = dict(q) if isinstance(q, dict) else {"no": i + 1, "type": "vote"}
                item.setdefault("no", i + 1)
                if item.get("row_index") is None and item.get("y") is None:
                    item["row_index"] = i
                item.setdefault("choices", 2)
                questions.append(item)

        roi_params = form_data.get("roi_params", {}) or {}
        dist_agree = float(roi_params.get("dist_agree") or roi_params.get("marker_to_agree_dist") or 100.0)
        dist_disagree = float(roi_params.get("dist_disagree") or roi_params.get("marker_to_disagree_dist") or 200.0)
        choice_dx = dist_disagree - dist_agree
        if abs(choice_dx) < 1e-6:
            choice_dx = 1.0
        marker_location = form_data.get("marker_location", "left")
        base_dpi = int(form_data.get("dpi") or form_data.get("base_dpi") or 150)
        if base_dpi <= 0:
            base_dpi = 150
        inferred_width = int(round(float(engine.width) * (float(base_dpi) / 150.0)))
        inferred_height = int(round(float(engine.height) * (float(base_dpi) / 150.0)))
        question_layout = {
            "width": int(form_data.get("width", inferred_width)),
            "height": int(form_data.get("height", inferred_height)),
            "x_offset": float(dist_agree),
            "choice_dx": float(choice_dx),
            "box_w": int(roi_params.get("box_w", 35)),
            "box_h": int(roi_params.get("box_h", 35)),
            "row_offset_y": 0,
            "row_start_y": 0,
            "row_start_from_marker": True,
            "row_dy": 0,
            "rows_per_col": max(1, len(questions)),
            "marker_start_index": 1,
            "columns": 1,
            "numbering_order": "column_major",
        }
        status, results, debug_img, error_reason = engine.analyze_marker_questions(
            aligned_img,
            questions,
            question_layout,
            scale=scale,
            marker_location=marker_location,
        )
        print(f"status={status}, error_reason={error_reason}")
    else:
        rois = build_rois_from_form(form_data, scale=scale)
        status, results, debug_img = engine.analyze_sheet_cv(aligned_img, rois)
        print(f"status={status}")

    print(f"results={results}")

    if SAVE_DEBUG and debug_img is not None:
        cv2.imwrite(DEBUG_OUT, debug_img)
        print(f"debug saved: {DEBUG_OUT}")

    if SHOW_UI and ErrorCorrectionDialog is not None:
        app = QApplication(sys.argv)
        dlg = ErrorCorrectionDialog(None, debug_img, results, IMAGE_PATH)
        dlg.exec_()


if __name__ == "__main__":
    main()
