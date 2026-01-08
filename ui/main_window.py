from PyQt5.QtWidgets import (QMainWindow, QToolBar, QAction, QMessageBox, QLabel, 
                             QStatusBar, QStackedWidget, QWidget, QVBoxLayout)
from PyQt5.QtCore import Qt
from ui.settings.file_setting import FileSettingsDialog
# ★ 이름이 바뀐 뷰(View) import
from ui.scanner.scan_window import ScannerReadingView

class OMRScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("김세윤의 omr_project")
        self.resize(1200, 800) # 기본 크기 설정
        
        # ★ 화면을 겹쳐놓는 스택 위젯 생성 (화면 전환용)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack) 

        # UI 초기화
        self.init_ui()

    def init_ui(self):
        # ---------------------------------------------------------
        # 1. 상단 툴바 생성 (사용자님 디자인 유지)
        # ---------------------------------------------------------
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon) # 아이콘 아래 텍스트
        self.addToolBar(toolbar)

        # 2. 툴바 메뉴 목록
        menu_items = [
            "파일설정", "스캐너설정", "양식설정", "기표수설정", "경로설정", 
            "고사장설정", "스캐너판독", "개표결과", "판독자료", "판독매수", "작업종료"
        ]

        # 3. 버튼 생성 및 툴바에 추가
        for item in menu_items:
            action = QAction(f"📂\n{item}", self) # 임시 아이콘
            # 버튼 클릭 시 on_menu_click 함수로 연결
            action.triggered.connect(lambda checked, x=item: self.on_menu_click(x))
            toolbar.addAction(action)
            toolbar.addSeparator()

        # ---------------------------------------------------------
        # 4. 화면 스택 구성 (홈 화면 + 스캐너 화면)
        # ---------------------------------------------------------
        
        # [페이지 0] 홈 화면 (기본 대기 화면 - 회색 배경)
        self.home_widget = QWidget()
        self.home_widget.setStyleSheet("background-color: #A0A0A0;")
        # (원하시면 여기에 배경 로고 등을 넣을 수 있습니다)
        
        # [페이지 1] 스캐너 판독 화면
        self.scanner_view = ScannerReadingView()
        # 스캐너 화면에서 '닫기' 버튼 누르면 -> 홈 화면(0번)으로 돌아오게 연결
        self.scanner_view.closed_signal.connect(self.show_home)

        # 스택에 추가
        self.stack.addWidget(self.home_widget)   # 인덱스 0
        self.stack.addWidget(self.scanner_view)  # 인덱스 1

        # ---------------------------------------------------------
        # 5. 상태바
        # ---------------------------------------------------------
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("시스템 준비 완료")

    def on_menu_click(self, menu_name):
        """툴바 버튼 클릭 처리"""
        print(f"클릭된 메뉴: {menu_name}")
        
        if menu_name == "작업종료":
            self.close()

        elif menu_name == "파일설정":
            # 파일 설정은 팝업창으로 띄움 (Dialog)
            dlg = FileSettingsDialog(self)
            dlg.db_selected_signal.connect(self.on_db_changed)
            dlg.exec_() # 팝업 실행

        elif menu_name == "스캐너판독":
            # ★ 핵심: 팝업(exec_) 대신 화면 전환(setCurrentIndex) 사용
            self.stack.setCurrentIndex(1) 
            self.statusbar.showMessage("스캐너 판독 화면으로 전환되었습니다.")

        else:
            # 다른 버튼 누르면 일단 홈으로 복귀 (나중에 기능 연결)
            self.stack.setCurrentIndex(0)
            self.statusbar.showMessage(f"'{menu_name}' 버튼이 클릭되었습니다.")

    def show_home(self):
        """홈 화면으로 돌아오기"""
        self.stack.setCurrentIndex(0)
        self.statusbar.showMessage("메인 화면으로 복귀했습니다.")

    def on_db_changed(self, path, title):
        self.setWindowTitle(f"김세윤omr_project - [{title}]")
        self.statusbar.showMessage(f"현재 열린 DB: {path}")