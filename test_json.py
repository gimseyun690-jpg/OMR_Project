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
# - Supports both layout_mode: fixed and side_marker
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
        questions = form_data.get("questions", [])
        roi_params = form_data.get("roi_params", {})
        status, results, debug_img, error_reason = engine.analyze_side_marker_sheet(
            aligned_img, questions, roi_params, scale=scale
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
