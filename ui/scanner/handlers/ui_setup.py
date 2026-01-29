from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QFrame, QGroupBox, QComboBox, QSplitter, QPushButton,
                               QHeaderView, QAbstractItemView, QMessageBox, QTableWidgetItem,
                               QFileDialog, QCheckBox, QMenu, QInputDialog)
from ui.scanner.components.control_panel import ControlPanel
from ui.scanner.components.status_panel import ScannerStatusPanel
from ui.scanner.components.session_summary_widget import SessionSummaryWidget
from ui.scanner.components.paged_result_grid import PagedResultGrid
from ui.scanner.components.styles import SPLITTER_HANDLE, ERROR_MSG
from logic.form_loader import list_forms, load_form, build_rois_from_form, get_anchor_from_form, get_omr_params, get_sheet_code
from utils.path_utils import data_path


class UiSetupMixin:
    """UI 초기화/연결 믹스인."""

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # === 1. 상태/설정 패널 ===
        self.status_panel = ScannerStatusPanel()
        self.lbl_total = self.status_panel.lbl_total
        self.lbl_check = self.status_panel.lbl_check
        self.lbl_cur_place = self.status_panel.lbl_cur_place
        self.lbl_cur_room = self.status_panel.lbl_cur_room
        self.lbl_cur_cnt = self.status_panel.lbl_cur_cnt
        self.lbl_review_detail = self.status_panel.lbl_review_detail
        self.cb_form = self.status_panel.cb_form
        self.cb_place = self.status_panel.cb_place
        self.cb_room = self.status_panel.cb_room
        self.cb_err_opt = self.status_panel.cb_err_opt
        self.cb_stop_opt = self.status_panel.cb_stop_opt
        self.chk_all_blank = self.status_panel.chk_all_blank
        self.chk_etc_error = self.status_panel.chk_etc_error
        main_layout.addWidget(self.status_panel)

        # === 2. 하단 3분할 ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(SPLITTER_HANDLE)

        self.summary_widget = SessionSummaryWidget()
        self.summary_table = self.summary_widget.table
        self.summary_table.itemSelectionChanged.connect(self._on_summary_selected)

        self.grid_widget = PagedResultGrid()
        self.main_grid = self.grid_widget.grid
        self.main_grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.main_grid.customContextMenuRequested.connect(self._on_grid_context_menu)
        self.main_grid.itemChanged.connect(self._on_main_grid_item_changed)

        self.control_panel = ControlPanel()

        splitter.addWidget(self.summary_widget)
        splitter.addWidget(self.grid_widget)
        splitter.addWidget(self.control_panel)
        splitter.setSizes([200, 1200, 260])
        splitter.setCollapsible(2, False)

        main_layout.addWidget(splitter, 1)
        self.setLayout(main_layout)

    # -------------------------------------------------------------------------
    # [2] 입력/설정 함수
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # [2] 드롭다운 로직: 오류 이동(Next/Prev)
    # -------------------------------------------------------------------------
    def connect_signals(self):
        # 기존 버튼 연결
        self.control_panel.btn_close.clicked.connect(self.go_back_home)
        self.control_panel.btn_scan.clicked.connect(self.start_scan)
        self.control_panel.btn_check.clicked.connect(self.open_error_check)
        self.control_panel.btn_demo.clicked.connect(self.run_demo_folder)
        self.control_panel.btn_next.clicked.connect(self.scan_next_room)
        self.control_panel.btn_stop.clicked.connect(self.stop_scan)
        self.control_panel.btn_retry.clicked.connect(self.retry_last_scan)

        
        # [추가] 콤보박스 변경 시 상단 라벨 자동 업데이트
        self.cb_place.currentTextChanged.connect(self.lbl_cur_place.setText)
        self.cb_room.currentTextChanged.connect(self.lbl_cur_room.setText)

        self.cb_form.currentIndexChanged.connect(self.on_form_changed)
        self.on_form_changed()  # 초기 1회 적용


    def on_form_changed(self):
        self.pipeline.set_form_path(self.cb_form.currentData())


    def go_back_home(self):
        self.closed_signal.emit()

    def showEvent(self, event):
        super().showEvent(event)
        if self.current_db_path and not self.scan_in_progress:
            self._load_summary_from_db()


    # 1. 좌표 가져오기(DB 연동 버전)
    def get_rois(self):
        """DB에서 좌표 설정값을 불러 ROIs 생성."""
        if not self.current_db_path:
            # DB가 없으면 기본값 반환
            return self.get_default_rois()

        try:
            # (1) DB에서 값 불러오기 (없으면 기본값 사용)
            start_y = int(self.controller.get_setting(self.current_db_path, "roi_start_y", "515"))
            gap_y = int(self.controller.get_setting(self.current_db_path, "roi_gap_y", "90"))
            w = int(self.controller.get_setting(self.current_db_path, "roi_w", "35"))
            h = int(self.controller.get_setting(self.current_db_path, "roi_h", "35"))
            x_agree = int(self.controller.get_setting(self.current_db_path, "roi_agree_x", "1130"))
            x_disagree = int(self.controller.get_setting(self.current_db_path, "roi_disagree_x", "1275"))
            
            # (2) 좌표 리스트 생성
            rois = []
            for i in range(5):
                y = start_y + (i * gap_y)
                rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])
            return rois
            
        except Exception as e:
            print(f"좌표 로드 오류: {e}")
            return self.get_default_rois()

    def get_default_rois(self):
        """기본 좌표."""
        w, h = 35, 35
        x_agree = 1130; x_disagree = 1275
        start_y = 515; gap_y = 90
        rois = []
        for i in range(5):
            y = start_y + (i * gap_y)
            rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])
        return rois

    # -------------------------------------------------------------------------
    # [3] 이벤트 연결 핸들러(버튼 동작)
    # -------------------------------------------------------------------------
    def set_current_db(self, db_path):
        self.current_db_path = db_path
        self.pipeline.set_project(db_path)

        try:
            self.update_statistics()
            self._load_summary_from_db()
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"통계 갱신 중 오류:\n{e}")


