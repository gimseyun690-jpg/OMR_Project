import sys
import os

# ========================================================
# [1] 고해상도(4K) 모니터 대응 (글자 깨짐/작게 나옴 방지)
# ========================================================
try:
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    sys.argv += ['--style', 'Fusion'] 
except Exception as e:
    print(f"[InitWarn] Qt scaling/style 설정 실패: {e}")

# ========================================================
# [2] PySide2 플러그인 경로 강제 지정 (오류 방지)
# ========================================================
import PySide2
plugin_path = os.path.join(os.path.dirname(PySide2.__file__), "Qt", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
# ========================================================

from PySide2.QtWidgets import QApplication
from PySide2.QtGui import QFont

# 우리가 만든 메인 화면 가져오기
from ui.main_window import OMRScannerApp

def main():
    app = QApplication(sys.argv)

    # 3. 전역 폰트 설정 (깔끔한 맑은 고딕)
    # 글씨가 너무 크면 10, 적당하면 11로 하세요
    font = QFont("Malgun Gothic", 10) 
    app.setFont(font)

    # 4. 메인 윈도우 생성 및 표시
    window = OMRScannerApp()
    window.showMaximized() # 시작할 때 전체화면으로
    
    # 5. 앱 실행
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

