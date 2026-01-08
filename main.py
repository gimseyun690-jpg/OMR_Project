import sys
import os

# ========================================================
# [중요] 32비트 PyQt5 플러그인 경로 강제 지정
# (Windows에서 "Could not find Qt platform plugin" 에러 방지)
# ========================================================
import PyQt5
plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
# ========================================================

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

# 우리가 만든 UI 파일 가져오기
from ui.main_window import OMRScannerApp

def main():
    app = QApplication(sys.argv)
    
    # 1. 전역 폰트 설정 (맑은 고딕 등)
    font = QFont("Malgun Gothic", 11)
    app.setFont(font)
    
    # 2. 메인 윈도우 생성 및 표시
    window = OMRScannerApp()
    window.showMaximized() # 꽉찬화면
    
    # 3. 앱 실행 루프
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()