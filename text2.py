import sys
import os

# ========================================================
# [중요] 32비트/64비트 PyQt5 플러그인 경로 강제 지정
# (이 코드가 없으면 "Could not find the Qt platform plugin" 오류 발생)
# ========================================================
import PyQt5
plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
# ========================================================

import cv2
from PyQt5.QtWidgets import QApplication
from logic.omr_engine import OMREngine
from ui.scanner.popups.error_editor import ErrorCorrectionDialog

# ==========================================
# 테스트할 좌표 설정 (해상도에 따라 수정 필요)
# ==========================================
def get_test_rois():
    # 제공해주신 이미지에 맞춘 대략적인 임시 좌표입니다.
    # 실행 후 'check_this.jpg'를 보고 박스가 밀려있으면 숫자를 조정하세요.
    w, h = 35, 35       # 박스 크기
    x_agree = 1130      # 찬성 박스 X좌표 (임시 추정)
    x_disagree = 1275   # 반대 박스 X좌표 (임시 추정)
    
    start_y = 515       # 1번 문항 Y좌표 시작점
    gap_y = 90          # 문항 간 간격

    rois = []
    for i in range(5):
        y = start_y + (i * gap_y)
        q_rois = [
            (x_agree, y, w, h),    # 찬성
            (x_disagree, y, w, h)  # 반대
        ]
        rois.append(q_rois)
    return rois

def main():
    print("--- [1] 프로그램 시작 ---")
    app = QApplication(sys.argv)
    
    # 1. 경로 확인
    # 테스트할 파일명을 여기에 적어주세요.
    target_filename = "100000004.jpg" 
    img_path = os.path.join("data", "scan_images", target_filename)
    
    print(f"--- [2] 이미지 찾는 중: {os.path.abspath(img_path)}")

    if not os.path.exists(img_path):
        print(f"\n❌ [오류 발생] 파일을 찾을 수 없습니다!")
        print(f"1. 'data/scan_images' 폴더 안에 사진이 있는지 확인하세요.")
        print(f"2. 파일명 '{target_filename}'이 정확한지 확인하세요.")
        return

    print("--- [3] 이미지 발견! 엔진 구동 시작 ---")
    
    engine = OMREngine()
    rois = get_test_rois()

    # 2. 엔진 분석
    try:
        status, results, res_img = engine.analyze_sheet(img_path, rois)
        print(f"--- [4] 분석 완료. 상태: {status}")
        
        # 좌표 확인용 이미지 저장
        cv2.imwrite("check_this.jpg", res_img)
        print("--- [Tip] 좌표 확인용 이미지 'check_this.jpg'를 저장했습니다.")

    except Exception as e:
        print(f"❌ [오류 발생] 분석 중 에러: {e}")
        return

    # 3. 팝업창 띄우기
    print("--- [5] 팝업창 생성 시도 ---")
    try:
        dlg = ErrorCorrectionDialog(None, res_img, results, img_path)
        print("   >>> 창을 띄웁니다. 화면을 확인하세요.")
        dlg.exec_()
        print("--- [6] 팝업창이 닫혔습니다. 종료합니다. ---")
    except Exception as e:
        print(f"❌ [오류 발생] UI 표시 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()