import sys
import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QAction, 
                             QStatusBar, QToolBar, QStackedWidget, QMessageBox, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

# 1. 기존 화면 및 설정
from ui.settings.file_setting import FileSettingsDialog
from ui.scanner.scan_window import ScannerReadingView

# 2. 결과 화면들
from ui.results.vote_count import VoteCountView
from ui.results.scan_data import ScanDataView
from ui.results.scan_stats import ScanStatsView

# ★ 3. [추가] 상세 설정 창들 Import
from ui.settings.form_setting import FormSettingsDialog
from ui.settings.mark_setting import MarkSettingsDialog
from ui.settings.path_setting import PathSettingsDialog
from ui.settings.site_setting import SiteSettingsDialog

class OMRScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("김세윤omr_project")
        self.resize(1200, 800)
        self.init_ui()

    def init_ui(self):
        # ---------------------------------------------------------
        # ★ 0. 상단 메뉴바 (MenuBar) - 설정 메뉴 추가
        # ---------------------------------------------------------
        menubar = self.menuBar()
        
        # [환경설정] 메뉴
        menu_settings = menubar.addMenu('환경설정(S)')
        
        act_form = QAction('양식/좌표 설정', self)
        act_form.triggered.connect(self.open_form_setting)
        menu_settings.addAction(act_form)

        act_mark = QAction('기표 인식 설정', self)
        act_mark.triggered.connect(self.open_mark_setting)
        menu_settings.addAction(act_mark)

        act_path = QAction('저장 경로 설정', self)
        act_path.triggered.connect(self.open_path_setting)
        menu_settings.addAction(act_path)
        
        menu_settings.addSeparator() # 구분선

        act_site = QAction('고사장/시험실 설정', self)
        act_site.triggered.connect(self.open_site_setting)
        menu_settings.addAction(act_site)

        # ---------------------------------------------------------
        # 1. 툴바 (메뉴 버튼들)
        # ---------------------------------------------------------
        toolbar = QToolBar("메인 툴바")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        menus = [
            ("파일설정", "folder.png"),
            ("스캐너판독", "scanner.png"),
            ("개표결과", "vote.png"),
            ("판독자료", "excel.png"),
            ("판독매수", "chart.png"),
            ("작업종료", "exit.png")
        ]

        for name, icon_file in menus:
            action = QAction(name, self)
            action.setStatusTip(f"{name} 화면으로 이동합니다.")
            action.triggered.connect(lambda checked, n=name: self.on_menu_click(n))
            toolbar.addAction(action)

        # ---------------------------------------------------------
        # 2. 메인 화면 영역 (스택 위젯)
        # ---------------------------------------------------------
        self.stack = QStackedWidget()
        
        # (0) 홈
        self.home_widget = QLabel("상단 메뉴를 선택하여 작업을 시작하세요.")
        self.home_widget.setAlignment(Qt.AlignCenter)
        self.home_widget.setStyleSheet("font-size: 20px; color: #555;")
        
        # (1) 스캐너
        self.scanner_view = ScannerReadingView()
        self.scanner_view.closed_signal.connect(lambda: self.stack.setCurrentIndex(0))

        # (2) 결과 화면들
        self.vote_view = VoteCountView()
        self.data_view = ScanDataView()
        self.stats_view = ScanStatsView()

        self.stack.addWidget(self.home_widget)   # 0
        self.stack.addWidget(self.scanner_view)  # 1
        self.stack.addWidget(self.vote_view)     # 2
        self.stack.addWidget(self.data_view)     # 3
        self.stack.addWidget(self.stats_view)    # 4

        self.setCentralWidget(self.stack)

        # ---------------------------------------------------------
        # 3. 상태바
        # ---------------------------------------------------------
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.showMessage("준비")

    # =============================================================
    # [메뉴 동작 처리]
    # =============================================================
    def on_menu_click(self, menu_name):
        current_db = getattr(self.scanner_view, 'current_db_path', None)
        
        if menu_name == "작업종료":
            self.close()

        elif menu_name == "파일설정":
            dlg = FileSettingsDialog(self)
            dlg.db_selected_signal.connect(self.on_db_changed)
            dlg.exec_()

        elif menu_name == "스캐너판독":
            self.stack.setCurrentIndex(1)
            self.statusbar.showMessage("스캐너 판독 화면")

        elif menu_name == "개표결과":
            self.vote_view.set_db_path(current_db) 
            self.stack.setCurrentIndex(2)
            self.statusbar.showMessage("개표 결과 집계")

        elif menu_name == "판독자료":
            self.data_view.set_db_path(current_db)
            self.stack.setCurrentIndex(3)
            self.statusbar.showMessage("전체 판독 자료 조회")

        elif menu_name == "판독매수":
            self.stats_view.set_db_path(current_db)
            self.stack.setCurrentIndex(4)
            self.statusbar.showMessage("고사장별 판독 매수 통계")

        else:
            self.stack.setCurrentIndex(0)

    def on_db_changed(self, path, title):
        self.setWindowTitle(f"김세윤omr_project - [{title}]")
        self.statusbar.showMessage(f"현재 열린 DB: {path}")
        self.scanner_view.set_current_db(path)

    # =============================================================
    # ★ [추가] 설정창 열기 함수들
    # =============================================================
    def get_current_db(self):
        """현재 열려있는 DB 경로 반환 (없으면 경고)"""
        db_path = getattr(self.scanner_view, 'current_db_path', None)
        if not db_path:
            QMessageBox.warning(self, "경고", "먼저 DB파일을 선택(파일설정)해주세요.")
            return None
        return db_path

    def open_form_setting(self):
        db_path = self.get_current_db()
        if db_path:
            FormSettingsDialog(self, db_path).exec_()

    def open_mark_setting(self):
        db_path = self.get_current_db()
        if db_path:
            MarkSettingsDialog(self, db_path).exec_()

    def open_path_setting(self):
        db_path = self.get_current_db()
        if db_path:
            PathSettingsDialog(self, db_path).exec_()

    def open_site_setting(self):
        db_path = self.get_current_db()
        if db_path:
            SiteSettingsDialog(self, db_path).exec_()

    def on_db_changed(self, path, title):
        self.setWindowTitle(f"김세윤omr_project - [{title}]")
        self.statusbar.showMessage(f"현재 열린 DB: {path}")

        # ✅ 추가: 스캐너 화면에 현재 프로젝트 DB 경로 전달
        self.scanner_view.set_project_db(path)
