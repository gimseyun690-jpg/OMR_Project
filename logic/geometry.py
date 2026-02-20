from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from logic.omr_types import Marker

class GeometryManager:
    def __init__(self, width: int = 1240, height: int = 1754):
        self.width = int(width)
        self.height = int(height)

    def configure(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        if width is not None and int(width) > 0:
            self.width = int(width)
        if height is not None and int(height) > 0:
            self.height = int(height)

    def align_image(self, img: Optional[np.ndarray]) -> Tuple[Optional[np.ndarray], bool, str]:
        if img is None:
            return None, False, "image_none"
        if len(img.shape) < 2:
            return None, False, "invalid_shape"

        target_w, target_h = int(self.width), int(self.height)
        target_ratio = float(target_w) / float(target_h) if target_h > 0 else 1.0

        work = img
        h, w = work.shape[:2]
        if w <= 0 or h <= 0:
            return None, False, "invalid_size"

        if w == target_w and h == target_h:
            return work, True, "original"

        # If the scan orientation is opposite to the expected page ratio,
        # rotate first so downstream marker logic starts from a stable pose.
        ratio_now = float(w) / float(h)
        ratio_rot = float(h) / float(w)
        rotated = False
        if abs(ratio_rot - target_ratio) + 1e-6 < abs(ratio_now - target_ratio):
            work = cv2.rotate(work, cv2.ROTATE_90_CLOCKWISE)
            rotated = True
            h, w = work.shape[:2]

        scale = min(float(target_w) / float(w), float(target_h) / float(h))
        new_w = max(1, int(round(float(w) * scale)))
        new_h = max(1, int(round(float(h) * scale)))
        interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        resized = cv2.resize(work, (new_w, new_h), interpolation=interp)

        aspect_diff = abs((float(w) / float(h)) - target_ratio)
        if new_w == target_w and new_h == target_h:
            return resized, True, ("rotated_resized" if rotated else "resized")
        if aspect_diff <= 0.03:
            stretched = cv2.resize(resized, (target_w, target_h), interpolation=interp)
            return stretched, True, ("rotated_resized" if rotated else "resized")

        if resized.ndim == 2:
            canvas = np.full((target_h, target_w), 255, dtype=resized.dtype)
        else:
            canvas = np.full((target_h, target_w, resized.shape[2]), 255, dtype=resized.dtype)
        x0 = max(0, (target_w - new_w) // 2)
        y0 = max(0, (target_h - new_h) // 2)
        x1 = min(target_w, x0 + new_w)
        y1 = min(target_h, y0 + new_h)
        canvas[y0:y1, x0:x1] = resized[0 : (y1 - y0), 0 : (x1 - x0)]
        return canvas, True, ("rotated_padded" if rotated else "padded")

    @staticmethod
    def _fit_marker_line(rows: Sequence[float], xs_list: Sequence[float]) -> Optional[Dict[str, Any]]:
        try:
            rows_arr = np.asarray(rows, dtype=np.float32)
            xs_arr = np.asarray(xs_list, dtype=np.float32)
            valid = np.isfinite(rows_arr) & np.isfinite(xs_arr)
            rows_arr = rows_arr[valid]
            xs_arr = xs_arr[valid]
        except Exception:
            return None

        if len(rows_arr) < 2:
            return None

        order = np.argsort(rows_arr)
        rows_arr = rows_arr[order]
        xs_arr = xs_arr[order]
        try:
            slope, intercept = np.polyfit(rows_arr, xs_arr, 1)
            preds = slope * rows_arr + intercept
            residuals = xs_arr - preds
            rms = float(np.sqrt(np.mean(residuals**2))) if len(residuals) > 0 else 0.0
        except Exception:
            return None
        return {
            "rows": rows_arr,
            "xs": xs_arr,
            "slope": float(slope),
            "intercept": float(intercept),
            "rms": float(rms),
            "count": int(len(rows_arr)),
        }

    @staticmethod
    def deskew_from_rows(
        image: Optional[np.ndarray],
        rows: Sequence[float],
        xs_list: Sequence[float],
        max_abs_deg: float = 12.0,
        min_abs_deg: float = 0.05,
        inlier_percentile: float = 85.0,
    ) -> Optional[np.ndarray]:
        if image is None or rows is None or xs_list is None:
            return image
        if len(rows) < 2 or len(xs_list) < 2 or len(rows) != len(xs_list):
            return image

        h, w = image.shape[:2]
        if h < 2 or w < 2:
            return image

        try:
            max_abs_deg_f = float(max_abs_deg)
        except Exception:
            max_abs_deg_f = 12.0
        if not np.isfinite(max_abs_deg_f):
            max_abs_deg_f = 12.0
        max_abs_deg_f = float(np.clip(abs(max_abs_deg_f), 0.2, 45.0))

        try:
            min_abs_deg_f = float(min_abs_deg)
        except Exception:
            min_abs_deg_f = 0.05
        if not np.isfinite(min_abs_deg_f):
            min_abs_deg_f = 0.05
        min_abs_deg_f = float(np.clip(abs(min_abs_deg_f), 0.0, max_abs_deg_f))

        try:
            inlier_pct = float(inlier_percentile)
        except Exception:
            inlier_pct = 85.0
        if not np.isfinite(inlier_pct):
            inlier_pct = 85.0
        inlier_pct = float(np.clip(inlier_pct, 60.0, 98.0))

        try:
            y = np.asarray(rows, dtype=np.float32).reshape(-1)
            x = np.asarray(xs_list, dtype=np.float32).reshape(-1)
            valid = np.isfinite(x) & np.isfinite(y)
            x = x[valid]
            y = y[valid]
        except Exception:
            return image

        if len(x) < 2:
            return image

        order = np.argsort(y)
        x = x[order]
        y = y[order]
        pts = np.stack([x, y], axis=1).astype(np.float32).reshape(-1, 1, 2)

        def _fit_line(points: np.ndarray) -> Tuple[float, float, float, float]:
            vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
            return float(vx), float(vy), float(x0), float(y0)

        try:
            vx, vy, x0, y0 = _fit_line(pts)
            if abs(vy) < 1e-6:
                return image

            n0, n1 = -vy, vx
            denom = (n0**2 + n1**2) ** 0.5 + 1e-9
            d = np.abs((pts[:, 0, 0] - x0) * n0 + (pts[:, 0, 1] - y0) * n1) / denom
            if len(d) > 5:
                keep_thr = np.percentile(d, inlier_pct)
                inliers = pts[d <= keep_thr]
                if len(inliers) >= 2:
                    vx, vy, x0, y0 = _fit_line(inliers)
                    if abs(vy) < 1e-6:
                        return image

            angle_deg = float(np.degrees(np.arctan2(vy, vx)))
            rotate_deg = 90.0 - angle_deg
            if rotate_deg > 90.0:
                rotate_deg -= 180.0
            elif rotate_deg < -90.0:
                rotate_deg += 180.0

            if abs(rotate_deg) > max_abs_deg_f or abs(rotate_deg) < min_abs_deg_f:
                return image

            pivot_y = float(np.clip(np.median(y), 0.0, float(h - 1)))
            k = float(vx / vy)
            pivot_x = float(np.clip(x0 + ((pivot_y - y0) * k), 0.0, float(w - 1)))
            center = (pivot_x, pivot_y)

            rot_m = cv2.getRotationMatrix2D(center, rotate_deg, 1.0)
            return cv2.warpAffine(
                image,
                rot_m,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
        except Exception:
            return image

    def deskew_by_markers(
        self,
        image: Optional[np.ndarray],
        markers: Sequence[Marker],
        marker_location: str,
        max_abs_deg: float = 12.0,
        min_abs_deg: float = 0.05,
        inlier_percentile: float = 85.0,
    ) -> Optional[np.ndarray]:
        if image is None or not markers or len(markers) < 2:
            return image
        loc = str(marker_location or "left").strip().lower()
        if loc in ("top", "bottom"):
            rows = [float(m.cx) for m in markers]
            xs_list = [float(m.cy) for m in markers]
        else:
            rows = [float(m.cy) for m in markers]
            xs_list = [float(m.cx) for m in markers]
        return self.deskew_from_rows(
            image,
            rows,
            xs_list,
            max_abs_deg=max_abs_deg,
            min_abs_deg=min_abs_deg,
            inlier_percentile=inlier_percentile,
        )



