import os
import json


# -------------------------------------------------
# 내부 유틸
# -------------------------------------------------
def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _forms_dir():
    return os.path.join(_project_root(), "resources", "forms")


# -------------------------------------------------
# 1. 폼 목록
# -------------------------------------------------
def list_forms():
    """
    return: [(form_id, display_name, path), ...]
    """
    forms = []
    base = _forms_dir()
    if not os.path.isdir(base):
        return forms

    for fn in os.listdir(base):
        if not fn.lower().endswith(".json"):
            continue

        path = os.path.join(base, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            form_id = data.get("form_id", fn)
            display = data.get("display_name", form_id)
            forms.append((form_id, display, path))
        except Exception:
            continue

    return forms


# -------------------------------------------------
# 2. 폼 로드
# -------------------------------------------------
def load_form(path: str) -> dict:
    """
    폼 JSON 로드
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------------------------------
# 3. ROI 생성
# -------------------------------------------------
def build_rois_from_form(form_data: dict):
    """
    form_data 기반으로 [(agree_roi, disagree_roi), ...] 생성
    """
    roi = form_data.get("roi", {})
    questions = int(form_data.get("questions", 0))

    start_y = int(roi.get("start_y", 0))
    gap_y = int(roi.get("gap_y", 0))
    w = int(roi.get("w", 0))
    h = int(roi.get("h", 0))
    agree_x = int(roi.get("agree_x", 0))
    disagree_x = int(roi.get("disagree_x", 0))

    rois = []
    for i in range(questions):
        y = start_y + i * gap_y
        rois.append([
            (agree_x, y, w, h),
            (disagree_x, y, w, h)
        ])

    return rois


# -------------------------------------------------
# 4. 타이밍 마크
# -------------------------------------------------
def get_timing_marks(form_data: dict):
    return form_data.get("timing_marks", [])


# -------------------------------------------------
# 5. Anchor
# -------------------------------------------------
def get_anchor_from_form(form_data: dict):
    anchor = form_data.get("anchor", {})
    return (
        int(anchor.get("x", 0)),
        int(anchor.get("y", 0))
    )


# -------------------------------------------------
# 6. OMR 파라미터
# -------------------------------------------------
def get_omr_params(form_data: dict):
    omr = form_data.get("omr", {})
    thresh = int(omr.get("threshold", 140))
    ratio = float(omr.get("pixel_ratio", 0.25))
    return thresh, ratio


# -------------------------------------------------
# 7. Sheet code
# -------------------------------------------------
def get_sheet_code(form_data: dict):
    return form_data.get("sheet_code") or form_data.get("form_id", "UNKNOWN")
