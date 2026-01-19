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
    form_data 기반 ROI 생성
    - vote: agree_x / disagree_x
    - exam: choice_x 리스트 (자동/수동 모두 대응)
    """
    rois = []

    roi_cfg = form_data.get("roi", {})
    questions = int(form_data.get("questions", 0) or 0)

    start_y = int(roi_cfg.get("start_y", 0))
    gap_y = int(roi_cfg.get("gap_y", 0))
    w = int(roi_cfg.get("w", 30))
    h = int(roi_cfg.get("h", 30))

    if questions <= 0:
        return rois

    # ---------------------------
    # 1️⃣ 시험 OMR (choice_x)
    # ---------------------------
    if "choice_x" in roi_cfg:
        choice_x = roi_cfg.get("choice_x", [])
        if not choice_x:
            return rois

        for i in range(questions):
            y = start_y + i * gap_y
            row = []
            for x in choice_x:
                row.append((int(x), int(y), w, h))
            rois.append(row)

        return rois

    # ---------------------------
    # 2️⃣ 투표 OMR (찬성/반대)
    # ---------------------------
    agree_x = roi_cfg.get("agree_x")
    disagree_x = roi_cfg.get("disagree_x")

    if agree_x is None or disagree_x is None:
        return rois

    for i in range(questions):
        y = start_y + i * gap_y
        rois.append([
            (int(agree_x), int(y), w, h),
            (int(disagree_x), int(y), w, h),
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
