import argparse
import glob
import os
import sys
from collections import Counter

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from logic.omr_engine import OMREngine
from logic.pipeline import ScanPipeline
from utils.text_io import read_json


def _iter_images(pattern: str):
    paths = sorted(glob.glob(pattern))
    for p in paths:
        if os.path.isfile(p):
            yield p


def main():
    parser = argparse.ArgumentParser(description="Regression check for top-marker OMR forms")
    parser.add_argument("--form", required=True, help="Path to form JSON")
    parser.add_argument("--images", required=True, help="Glob pattern for input images")
    args = parser.parse_args()

    form_data = read_json(args.form)
    if not isinstance(form_data, dict):
        raise SystemExit("Invalid form JSON")

    images = list(_iter_images(args.images))
    if not images:
        raise SystemExit("No images matched pattern")

    pipe = ScanPipeline()
    pipe.set_form_path(args.form)

    omr = form_data.get("omr", {}) if isinstance(form_data.get("omr"), dict) else {}
    marker_location = str(form_data.get("marker_location", "left"))
    questions = pipe.engine.parse_config(form_data)
    layout = form_data.get("question_layout", {}) if isinstance(form_data.get("question_layout"), dict) else {}
    scale = pipe._get_scale_factor()

    print(f"[FORM] {args.form}")
    print(f"[MARKER_LOCATION] {marker_location}")
    print(f"[QUESTIONS] {len(questions)}")
    print(f"[OMR] threshold={omr.get('threshold')} pixel_ratio={omr.get('pixel_ratio')}")

    total = Counter()
    for p in images:
        img = pipe.engine.load_image(p)
        aligned, ok, reason = pipe.engine.align_image_warp(img)
        if not ok or aligned is None:
            print(f"[FAIL_ALIGN] {os.path.basename(p)} reason={reason}")
            continue

        status, results, _, err = pipe.engine.analyze_marker_questions(
            aligned,
            questions,
            layout,
            scale=scale,
            marker_location=marker_location,
        )
        counts = Counter(len(r.get("marked", [])) for r in results if isinstance(r, dict))
        single = counts.get(1, 0)
        blank = counts.get(0, 0)
        multi = sum(v for k, v in counts.items() if k > 1)
        total["single"] += single
        total["blank"] += blank
        total["multi"] += multi
        total["images"] += 1
        print(
            f"[IMG] {os.path.basename(p)} align={reason} status={status} err={err} "
            f"single={single} blank={blank} multi={multi}"
        )

    print(
        f"[TOTAL] images={total['images']} single={total['single']} "
        f"blank={total['blank']} multi={total['multi']}"
    )


if __name__ == "__main__":
    main()
