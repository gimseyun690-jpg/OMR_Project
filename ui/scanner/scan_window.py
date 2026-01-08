import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QFrame, QGroupBox, QComboBox, QSplitter,
                             QTableWidget, QHeaderView, QAbstractItemView, QMessageBox, QTableWidgetItem)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QThread

# 기존 UI 컴포넌트 import (유지)
from ui.scanner.components.control_panel import ControlPanel
from ui.scanner.components.data_grid import DataGrid
from logic.scanner_core import ScannerDevice

# ★ 기능 연결을 위해 추가된 모듈
from logic.omr_engine import OMREngine
from database import DBManager

# =========================================================
# [스캔 워커 스레드] - 백그라운드에서 스캐너 돌리기 (유지)
# =========================================================
class ScanWorker(QThread):
    image_scanned = pyqtSignal(str)
    scan_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, hwnd): 
        super().__init__()
        self.hwnd = hwnd
        self.scanner = ScannerDevice()
        self.is_running = True

    def run(self):
        try:
            # 1. 연결
            success, msg = self.scanner.connect(self.hwnd)
            if not success:
                self.error_occurred.emit(f"스캐너 연결 실패: {msg}")
                return

            # 2. 장비 열기
            success, msg = self.scanner.open_scanner()
            if not success:
                self.error_occurred.emit(f"장비 열기 실패: {msg}")
                return

            # 3. 용지 확인
            if not self.scanner.check_paper():
                self.error_occurred.emit("급지대에 용지가 없습니다.")
                return

            # 4. 스캔 루프
            for image_path in self.scanner.scan():
                if not self.is_running: break
                self.image_scanned.emit(image_path)
            
            self.scan_finished.emit()

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.scanner.close()

    def stop(self):
        self.is_running = False


# =========================================================
# [메인 스캔 화면] - 디자인은 원래대로 복구됨
# =========================================================
class ScannerReadingView(QWidget):
    closed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 내부 변수 초기화
        self.total_read = 0
        self.worker = None
        
        # ★ 엔진 & DB 매니저 생성
        self.engine = OMREngine()
        self.db = DBManager()
        self.current_db_path = None # 현재 열린 DB 경로

        # UI 초기화 (원래 디자인 함수 호출)
        self.init_ui()
        self.connect_signals()

    # -------------------------------------------------------------------------
    # [1] UI 디자인 (사용자님 원래 코드 100% 복구)
    # -------------------------------------------------------------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # === 1. 상단 정보/설정 패널 ===
        top_frame = QFrame()
        top_frame.setFixedHeight(120)
        top_frame.setStyleSheet("background-color: #F0F0F0; border-bottom: 1px solid #A0A0A0;")
        
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(10)

        # (1-1) 좌측: 판독/점검 카운터 그룹
        grp_cnt = QGroupBox()
        grp_cnt.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_cnt = QGridLayout(grp_cnt)
        grid_cnt.setContentsMargins(5, 5, 5, 5)
        grid_cnt.setVerticalSpacing(0)

        st_label = "color: black; font-weight: bold; font-size: 11px; border: none;"
        st_blue_num = "color: blue; font-weight: bold; font-size: 20px; border: none;"
        st_red_num = "color: red; font-weight: bold; font-size: 20px; border: none;"

        grid_cnt.addWidget(QLabel("총판독매수", styleSheet=st_label), 0, 0, alignment=Qt.AlignCenter)
        grid_cnt.addWidget(QLabel("총점검매수", styleSheet=st_label), 0, 1, alignment=Qt.AlignCenter)
        
        self.lbl_total = QLabel("0", styleSheet=st_blue_num)
        grid_cnt.addWidget(self.lbl_total, 1, 0, alignment=Qt.AlignCenter)
        
        self.lbl_check = QLabel("0", styleSheet=st_red_num)
        grid_cnt.addWidget(self.lbl_check, 1, 1, alignment=Qt.AlignCenter)

        # 구분선
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #ccc;")
        grid_cnt.addWidget(line, 2, 0, 1, 2)

        # 현재 고사장/시험실 정보
        lbl_cur_title = QLabel("현재 고사장/시험실 판독매수", styleSheet="font-size:10px; font-weight:bold; color:#555; border:none;")
        grid_cnt.addWidget(lbl_cur_title, 3, 0, 1, 2)

        sub_layout = QGridLayout()
        sub_layout.addWidget(QLabel("현재 고사장 :", styleSheet="font-size:11px; border:none;"), 0, 0)
        sub_layout.addWidget(QLabel("스캐너1", styleSheet="color:blue; font-weight:bold; border:none;"), 0, 1)
        
        sub_layout.addWidget(QLabel("현재 시험실 :", styleSheet="font-size:11px; border:none;"), 1, 0)
        self.lbl_cur_room = QLabel("1", styleSheet="color:blue; font-weight:bold; font-size:14px; border:none;")
        sub_layout.addWidget(self.lbl_cur_room, 1, 1)

        sub_layout.addWidget(QLabel("현재 판독매수", styleSheet="font-size:11px; border:none;"), 0, 2, 2, 1)
        self.lbl_cur_cnt = QLabel("0", styleSheet="color:red; font-weight:bold; font-size:18px; border:none;")
        sub_layout.addWidget(self.lbl_cur_cnt, 0, 3, 2, 1)

        grid_cnt.addLayout(sub_layout, 4, 0, 1, 2)

        # (1-2) 중앙: 설정 (양식, 고사장)
        grp_set = QGroupBox()
        grp_set.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_set = QGridLayout(grp_set)
        
        st_blue_lbl = "color: blue; font-weight: bold; font-size: 12px; border: none;"
        st_combo = "QComboBox { border: 1px solid #999; padding: 2px; font-size: 12px; font-weight: bold; color: black; }"
        
        self.cb_form = QComboBox(); self.cb_form.addItem("OMR_Project"); self.cb_form.setStyleSheet(st_combo)
        self.cb_place = QComboBox(); self.cb_place.addItem("스캐너1"); self.cb_place.setStyleSheet(st_combo)
        self.cb_room = QComboBox(); self.cb_room.addItem("1"); self.cb_room.setStyleSheet(st_combo)

        grid_set.addWidget(QLabel("스캔OMR양식 :", styleSheet=st_blue_lbl), 0, 0)
        grid_set.addWidget(self.cb_form, 0, 1)
        grid_set.addWidget(QLabel("판독 고사장 :", styleSheet="font-weight:bold; border:none;"), 1, 0)
        grid_set.addWidget(self.cb_place, 1, 1)
        grid_set.addWidget(QLabel("판독 시험실 :", styleSheet="font-weight:bold; border:none;"), 2, 0)
        grid_set.addWidget(self.cb_room, 2, 1)

        # (1-3) 우측: 오류점검 설정
        grp_err = QGroupBox("오류점검")
        grp_err.setStyleSheet("background-color: white; border: 1px solid #999; font-size: 11px;")
        grid_err = QGridLayout(grp_err)
        
        self.cb_err_opt = QComboBox(); self.cb_err_opt.addItem("이미지오류(저장안함) 스캔시보기 / 표기오류 스캔완료후보기")
        self.cb_stop_opt = QComboBox(); self.cb_stop_opt.addItem("모든오류 스캔중단")
        
        grid_err.addWidget(QLabel("스캔시 오류점검창 보기 :", styleSheet="border:none;"), 0, 0)
        grid_err.addWidget(self.cb_err_opt, 0, 1)
        grid_err.addWidget(QLabel("오류점검시 스캔중단 :", styleSheet="border:none;"), 1, 0)
        grid_err.addWidget(self.cb_stop_opt, 1, 1)

        # (1-4) 우측 끝: 체크박스
        grp_chk = QGroupBox("오류점검")
        grp_chk.setStyleSheet("background-color: white; border: 1px solid #999; font-size: 11px;")
        v_chk = QVBoxLayout(grp_chk)
        v_chk.addWidget(QLabel("☑ 전체공란 무효표 점검"))
        v_chk.addWidget(QLabel("☑ 기타 무효표 점검"))

        # 레이아웃 비율 설정
        top_layout.addWidget(grp_cnt, 25)
        top_layout.addWidget(grp_set, 30)
        top_layout.addWidget(grp_err, 35)
        top_layout.addWidget(grp_chk, 10)

        main_layout.addWidget(top_frame)

        # === 2. 하단 3단 분리 (좌측 표 | 중앙 표 | 우측 컨트롤) ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ccc; }")

        # (2-1) 좌측: 요약 테이블
        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(3)
        self.summary_table.setHorizontalHeaderLabels(["판독고사장", "판독시험실", "판독매수"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setStyleSheet("""
            QHeaderView::section { background-color: #D1E8FF; border: 1px solid #999; font-weight: bold; font-size: 11px; }
            QTableWidget { gridline-color: #ccc; font-size: 11px; }
        """)
        # 초기 행 추가
        self.summary_table.insertRow(0)
        self.summary_table.setItem(0, 0, self._item("스캐너1"))
        self.summary_table.setItem(0, 1, self._item("1"))
        self.summary_table.setItem(0, 2, self._item("0"))

        # (2-2) 중앙: 메인 데이터 그리드 (DataGrid 부품 사용)
        self.main_grid = DataGrid()

        # (2-3) 우측: 컨트롤 패널 (ControlPanel 부품 사용)
        self.control_panel = ControlPanel()

        splitter.addWidget(self.summary_table)
        splitter.addWidget(self.main_grid)
        splitter.addWidget(self.control_panel)

        # 초기 너비 비율
        splitter.setSizes([200, 1200, 260])
        splitter.setCollapsible(2, False)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    # -------------------------------------------------------------------------
    # [2] 헬퍼 및 설정 함수 (로직 연결용)
    # -------------------------------------------------------------------------
    def _item(self, text):
        """테이블 아이템 생성 헬퍼"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def set_current_db(self, db_path):
        """메인 윈도우에서 DB 경로를 받아옴"""
        self.current_db_path = db_path
        print(f"스캐너 화면: DB 경로 설정됨 -> {db_path}")

    def get_rois(self):
        """(임시) OMR 판독 좌표"""
        w, h = 35, 35       
        x_agree = 1130      
        x_disagree = 1275   
        start_y = 515       
        gap_y = 90          

        rois = []
        for i in range(5):
            y = start_y + (i * gap_y)
            rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])
        return rois

    # -------------------------------------------------------------------------
    # [3] 이벤트 연결 및 핸들러 (버튼 동작)
    # -------------------------------------------------------------------------
    def connect_signals(self):
        # 닫기 버튼 -> 홈으로 복귀
        self.control_panel.btn_close.clicked.connect(self.go_back_home)
        # 스캔 버튼 -> start_scan 실행
        self.control_panel.btn_scan.clicked.connect(self.start_scan)

    def go_back_home(self):
        self.closed_signal.emit()

    @pyqtSlot()
    def start_scan(self):
        """스캔 버튼 클릭 시"""
        # DB 선택 여부 확인
        if self.current_db_path is None:
            QMessageBox.warning(self, "경고", "먼저 '파일 설정' 메뉴에서 사용할 DB 파일을 선택(열기)해주세요!")
            return

        # 윈도우 핸들 가져오기 (TWAIN 통신용)
        my_hwnd = int(self.winId())
        
        # 워커 스레드 생성 및 실행
        self.worker = ScanWorker(my_hwnd)
        self.worker.image_scanned.connect(self.on_image_received)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        
        # 버튼 잠금
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_scan.setText("스캔중...")
        
        self.worker.start()

    @pyqtSlot(str)
    def on_image_received(self, image_path):
        """★ 핵심: 이미지 스캔 직후 호출됨"""
        self.total_read += 1
        
        # 1. OMR 엔진 판독
        rois = self.get_rois() 
        status, results, _ = self.engine.analyze_sheet(image_path, rois)
        
        # 2. 결과 문자열 생성 (예: "10100")
        result_str = "".join(["1" if len(r['marked']) > 0 else "0" for r in results])
        
        # 3. DB 저장용 데이터 구성
        current_place = self.cb_place.currentText()
        current_room = self.cb_room.currentText()
        
        save_data = {
            'read_num': self.total_read,
            'place': current_place,
            'room': current_room,
            'path': image_path,
            'sheet_code': 'OMR_V1',
            'mark_result': result_str,
            'is_valid': 1 if status == "정상" else 0
        }
        
        # 4. DB 저장
        if self.current_db_path:
            self.db.insert_scan_result(self.current_db_path, save_data)
        
        # 5. UI 테이블 업데이트
        row_data = [
            str(self.total_read),   # 판독번호
            "OMR_V1",               # 용지코드
            current_place,          # 고사장
            current_room,           # 시험실
            status,                 # 표기오류
            "완료",                 # 점검구분
            result_str,             # 표기내용
            image_path,             # 경로
            os.path.basename(image_path) # 파일명
        ]
        self.main_grid.add_row_data(row_data)
        
        # 6. 상단 카운터 업데이트
        self.lbl_total.setText(str(self.total_read))
        self.lbl_cur_cnt.setText(str(self.total_read))
        self.summary_table.setItem(0, 2, self._item(str(self.total_read)))
        self.control_panel.txt_temp.setText(str(self.total_read))
        self.main_grid.scrollToBottom()

    @pyqtSlot()
    def on_finished(self):
        QMessageBox.information(self, "완료", "스캔 작업이 완료되었습니다.")
        self.reset_ui_state()

    @pyqtSlot(str)
    def on_error(self, msg):
        QMessageBox.warning(self, "오류", msg)
        self.reset_ui_state()

    def reset_ui_state(self):
        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_scan.setText("📄 현재시험실 스캔(R)")