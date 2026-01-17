import cv2
import numpy as np
from typing import Tuple

def rotate_image_keep_size(img: np.ndarray, angle_deg: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    이미지 중심 기준으로 회전, 원본 크기 유지.
    return: (rotated_img, M)
    """
    h, w = img.shape[:2]
    center = (w / 2.0, h / 2.0)

    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    rotated = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated, M


def apply_affine_to_point(M, x, y):
    """2x3 affine matrix M에 점 변환 적용"""
    nx = M[0, 0] * x + M[0, 1] * y + M[0, 2]
    ny = M[1, 0] * x + M[1, 1] * y + M[1, 2]
    return int(nx), int(ny)

def warp_to_form(image_cv, src_pts, dst_pts, out_size):
    """
    src_pts: (4,2) 실제 이미지에서 찾은 점들 (TL,TR,BR,BL 순서 추천)
    dst_pts: (4,2) 폼(기준) 좌표계에서의 기대 점들 (TL,TR,BR,BL)
    out_size: (width, height)
    """
    src = np.array(src_pts, dtype=np.float32)
    dst = np.array(dst_pts, dtype=np.float32)

    M = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        image_cv, M, out_size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE
    )
    return warped, M