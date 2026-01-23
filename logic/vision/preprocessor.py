import cv2
import numpy as np
from typing import Tuple, List, Union

def rotate_image_keep_size(img: np.ndarray, angle_deg: float, bg_color=(255, 255, 255)) -> Tuple[np.ndarray, np.ndarray]:
    """
    이미지 중심 기준으로 회전하되, 원본 크기(w, h)를 유지합니다.
    
    [수정 사항]
    1. borderMode: BORDER_REPLICATE(늘이기) -> BORDER_CONSTANT(단색 채우기)
       - 문서 스캔 시 회전하면 가장자리가 지저분하게 늘어나는 것을 방지하고, 
       - 깔끔하게 흰색(또는 지정색)으로 채웁니다.
    """
    h, w = img.shape[:2]
    center = (w / 2.0, h / 2.0)

    # 회전 매트릭스 생성
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    
    # 이미지 회전
    rotated = cv2.warpAffine(
        img, M, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, # 빈 공간을 단색으로 채움
        borderValue=bg_color            # 기본값: 흰색
    )
    return rotated, M


def warp_to_form(image_cv: np.ndarray, src_pts: List[Tuple[int, int]], dst_pts: List[Tuple[int, int]], out_size: Tuple[int, int], bg_color=(255, 255, 255)) -> Tuple[np.ndarray, np.ndarray]:
    """
    4개의 점을 기준으로 투시 변환(Perspective Transform)을 수행합니다.
    
    [수정 사항]
    1. 입력 점 데이터를 np.array로 안전하게 변환
    2. borderMode를 흰색(BORDER_CONSTANT)으로 변경하여 문서 깔끔하게 처리
    """
    src = np.array(src_pts, dtype=np.float32)
    dst = np.array(dst_pts, dtype=np.float32)

    # 투시 변환 행렬 계산 (3x3 Matrix)
    M = cv2.getPerspectiveTransform(src, dst)
    
    # 변환 적용
    warped = cv2.warpPerspective(
        image_cv, M, out_size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, # 빈 공간 흰색
        borderValue=bg_color
    )
    return warped, M


def apply_transform_to_point(M: np.ndarray, x: float, y: float) -> Tuple[int, int]:
    """
    [핵심 수정] 
    행렬 M의 종류(2x3 Affine 또는 3x3 Perspective)를 자동 감지하여 
    점을 올바르게 변환합니다.
    
    - 이전 함수는 Affine(회전)만 됐지만, 이 함수는 Warp(투시변환) 좌표도 계산 가능합니다.
    """
    # 점을 벡터 형태로 변환 [x, y, 1]
    vec = np.array([x, y, 1.0])

    if M.shape == (2, 3): 
        # Affine 변환 (회전/이동) - 단순 행렬 곱
        # [x'] = [m00 m01 m02] * [x]
        # [y']   [m10 m11 m12]   [y]
        #                        [1]
        res = M @ vec
        return int(round(res[0])), int(round(res[1]))
    
    elif M.shape == (3, 3):
        # Perspective 변환 (투시) - 호모그래피 좌표계
        # [x']   [m00 m01 m02]   [x]
        # [y'] = [m10 m11 m12] * [y]
        # [w']   [m20 m21 m22]   [1]
        # 최종 좌표 = (x'/w', y'/w') -> 원근법 적용 시 w로 나누는 게 필수!
        res = M @ vec
        w_val = res[2]
        if w_val != 0:
            return int(round(res[0] / w_val)), int(round(res[1] / w_val))
        else:
            return 0, 0 # 예외 처리
            
    else:
        raise ValueError(f"지원하지 않는 행렬 크기입니다: {M.shape}")