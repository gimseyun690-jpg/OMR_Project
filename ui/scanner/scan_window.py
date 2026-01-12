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
from ui.scanner.popups.error_editor import ErrorCorrectionDialog # 팝업창

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
        
        # [중요] 기준점 좌표 (find.py로 잰 검은 네모 위치) - 필요시 수정하세요
        self.ref_anchor = (100, 500) 

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

        # (1-1) 좌측: 카운터 그룹
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

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #ccc;")
        grid_cnt.addWidget(line, 2, 0, 1, 2)

        # [수정] 현재 고사장/시험실 라벨 변수화
        lbl_cur_title = QLabel("현재 고사장/시험실 판독매수", styleSheet="font-size:10px; font-weight:bold; color:#555; border:none;")
        grid_cnt.addWidget(lbl_cur_title, 3, 0, 1, 2)

        sub_layout = QGridLayout()
        sub_layout.addWidget(QLabel("현재 고사장 :", styleSheet="font-size:11px; border:none;"), 0, 0)
        # ★ 여기를 변수(self.lbl_cur_place)로 변경
        self.lbl_cur_place = QLabel("스캐너1", styleSheet="color:blue; font-weight:bold; border:none;")
        sub_layout.addWidget(self.lbl_cur_place, 0, 1)
        
        sub_layout.addWidget(QLabel("현재 시험실 :", styleSheet="font-size:11px; border:none;"), 1, 0)
        self.lbl_cur_room = QLabel("1", styleSheet="color:blue; font-weight:bold; font-size:14px; border:none;")
        sub_layout.addWidget(self.lbl_cur_room, 1, 1)

        sub_layout.addWidget(QLabel("현재 판독매수", styleSheet="font-size:11px; border:none;"), 0, 2, 2, 1)
        self.lbl_cur_cnt = QLabel("0", styleSheet="color:red; font-weight:bold; font-size:18px; border:none;")
        sub_layout.addWidget(self.lbl_cur_cnt, 0, 3, 2, 1)

        grid_cnt.addLayout(sub_layout, 4, 0, 1, 2)

        # (1-2) 중앙: 설정
        grp_set = QGroupBox()
        grp_set.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_set = QGridLayout(grp_set)
        
        st_blue_lbl = "color: blue; font-weight: bold; font-size: 12px; border: none;"
        st_combo = "QComboBox { border: 1px solid #999; padding: 2px; font-size: 12px; font-weight: bold; color: black; }"
        
        self.cb_form = QComboBox(); self.cb_form.addItem("OMR_Project"); self.cb_form.setStyleSheet(st_combo)
        
        # [수정] 스캐너 1~10 목록 채우기
        self.cb_place = QComboBox(); self.cb_place.setStyleSheet(st_combo)
        for i in range(1, 11):
            self.cb_place.addItem(f"스캐너{i}")

        # [수정] 시험실 1~100 목록 채우기
        self.cb_room = QComboBox(); self.cb_room.setStyleSheet(st_combo)
        for i in range(1, 1000):
            self.cb_room.addItem(str(i))

        grid_set.addWidget(QLabel("스캔OMR양식 :", styleSheet=st_blue_lbl), 0, 0)
        grid_set.addWidget(self.cb_form, 0, 1)
        grid_set.addWidget(QLabel("판독 고사장 :", styleSheet="font-weight:bold; border:none;"), 1, 0)
        grid_set.addWidget(self.cb_place, 1, 1)
        grid_set.addWidget(QLabel("판독 시험실 :", styleSheet="font-weight:bold; border:none;"), 2, 0)
        grid_set.addWidget(self.cb_room, 2, 1)

        # (1-3) 우측: 오류점검 (기존 유지)
        grp_err = QGroupBox("오류점검")
        grp_err.setStyleSheet("background-color: white; border: 1px solid #999; font-size: 11px;")
        grid_err = QGridLayout(grp_err)
        self.cb_err_opt = QComboBox(); self.cb_err_opt.addItem("이미지오류(저장안함) 스캔시보기 / 표기오류 스캔완료후보기")
        self.cb_stop_opt = QComboBox(); self.cb_stop_opt.addItem("모든오류 스캔중단")
        grid_err.addWidget(QLabel("스캔시 오류점검창 보기 :", styleSheet="border:none;"), 0, 0)
        grid_err.addWidget(self.cb_err_opt, 0, 1)
        grid_err.addWidget(QLabel("오류점검시 스캔중단 :", styleSheet="border:none;"), 1, 0)
        grid_err.addWidget(self.cb_stop_opt, 1, 1)

        # (1-4) 우측 끝: 체크박스 (기존 유지)
        grp_chk = QGroupBox("오류점검")
        grp_chk.setStyleSheet("background-color: white; border: 1px solid #999; font-size: 11px;")
        v_chk = QVBoxLayout(grp_chk)
        v_chk.addWidget(QLabel("☑ 전체공란 무효표 점검"))
        v_chk.addWidget(QLabel("☑ 기타 무효표 점검"))

        top_layout.addWidget(grp_cnt, 25)
        top_layout.addWidget(grp_set, 30)
        top_layout.addWidget(grp_err, 35)
        top_layout.addWidget(grp_chk, 10)
        main_layout.addWidget(top_frame)

        # === 2. 하단 3단 분리 (기존 유지) ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ccc; }")

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(3)
        self.summary_table.setHorizontalHeaderLabels(["판독고사장", "판독시험실", "판독매수"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setStyleSheet("QHeaderView::section { background-color: #D1E8FF; border: 1px solid #999; font-weight: bold; font-size: 11px; } QTableWidget { gridline-color: #ccc; font-size: 11px; }")
        self.summary_table.insertRow(0)
        self.summary_table.setItem(0, 0, self._item("스캐너1"))
        self.summary_table.setItem(0, 1, self._item("1"))
        self.summary_table.setItem(0, 2, self._item("0"))

        self.main_grid = DataGrid()
        self.control_panel = ControlPanel()

        splitter.addWidget(self.summary_table)
        splitter.addWidget(self.main_grid)
        splitter.addWidget(self.control_panel)
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
        # DB 연결되면 바로 통계 갱신
        self.update_statistics()
        print(f"스캐너 화면: DB 경로 설정됨 -> {db_path}")

    def get_rois(self):
        """OMR 판독 좌표 (사용자님 지정 값 유지)"""
        w, h = 35, 35       
        x_agree = 954       
        x_disagree = 1103   
        start_y = 771       
        gap_y = 100         

        rois = []
        for i in range(5):
            y = start_y + (i * gap_y)
            rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])
        return rois

    # -------------------------------------------------------------------------
    # [3] 이벤트 연결 및 핸들러 (버튼 동작)
    # -------------------------------------------------------------------------
    def connect_signals(self):
        # 기존 버튼 연결
        self.control_panel.btn_close.clicked.connect(self.go_back_home)
        self.control_panel.btn_scan.clicked.connect(self.start_scan)
        self.control_panel.btn_check.clicked.connect(self.open_error_check)
        
        # [추가] 콤보박스 변경 시 상단 라벨 자동 업데이트
        self.cb_place.currentTextChanged.connect(self.lbl_cur_place.setText)
        self.cb_room.currentTextChanged.connect(self.lbl_cur_room.setText)

    def go_back_home(self):
        self.closed_signal.emit()

    @pyqtSlot()
    def start_scan(self):
        """스캔 버튼 클릭 시"""
        if self.current_db_path is None:
            QMessageBox.warning(self, "경고", "먼저 '파일 설정' 메뉴에서 사용할 DB 파일을 선택(열기)해주세요!")
            return

        # [추가] 이번 스캔 세션(시험실)의 카운트 초기화
        self.current_session_count = 0

        my_hwnd = int(self.winId())
        self.worker = ScanWorker(my_hwnd)
        self.worker.image_scanned.connect(self.on_image_received)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_scan.setText("스캔중...")
        
        self.worker.start()

    @pyqtSlot(str)
    def on_image_received(self, image_path):
        """★ 핵심: 이미지 스캔 직후 호출됨"""
        self.total_read += 1
        self.current_session_count += 1  # [추가] 이번 시험실 매수 증가
        
        # 1. OMR 엔진 판독 (기준점 보정 포함)
        rois = self.get_rois() 
        status, results, _ = self.engine.analyze_sheet(image_path, rois, self.ref_anchor)
        
        # 2. 결과 문자열 생성
        result_str = ""
        for r in results:
            if len(r['marked']) == 0: val = "0"
            elif len(r['marked']) > 1: val = "3" # 중복
            elif 0 in r['marked']: val = "1"     # 찬성
            elif 1 in r['marked']: val = "2"     # 반대
            else: val = "0"
            result_str += val
        
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
        
        # 5. UI 테이블 업데이트 (가운데 표)
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
        # self.summary_table 업데이트는 완료 시점에 하므로 여기서는 뺌
        self.control_panel.txt_temp.setText(str(self.total_read))
        self.main_grid.scrollToBottom()
        
        # 7. DB 통계도 즉시 갱신
        self.update_statistics()

    # ---------------------------------------------------------
    # [핵심] 오류 점검 및 수정 로직
    # ---------------------------------------------------------
    def open_error_check(self):
        """오류(is_valid=0)인 항목을 찾아 팝업을 띄움"""
        if not self.current_db_path: return

        # 1. DB에서 모든 데이터 가져오기
        all_rows = self.db.get_all_scans(self.current_db_path)
        
        # 2. 오류인 것만 찾기
        error_row = None
        for row in all_rows:
            # row[7]이 is_valid (0이면 오류)
            if row[7] == 0: 
                error_row = row
                break
        
        if not error_row:
            QMessageBox.information(self, "알림", "점검할 오류 항목이 없습니다!")
            return

        # 3. 팝업 데이터 준비 (문자열 '103' -> 리스트 변환)
        result_str = error_row[6]
        scan_results = []
        for i, char in enumerate(result_str):
            marked = []
            if char == '1': marked = [0]
            elif char == '2': marked = [1]
            elif char == '3': marked = [0, 1]
            
            status = "정상"
            if char == '0': status = "공란"
            elif char == '3': status = "중복"
            
            scan_results.append({'q_num': i+1, 'marked': marked, 'status': status})

        # 4. 이미지 로드
        import cv2
        import numpy as np
        try:
            img_array = np.fromfile(error_row[4], np.uint8) 
            image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except:
            image_cv = None

        # 5. 팝업 실행
        dlg = ErrorCorrectionDialog(self, image_cv, scan_results, error_row[4])
        if dlg.exec_():
            # [저장 버튼 누름] -> 수정된 데이터 DB 업데이트
            new_result_str = ""
            for r in dlg.scan_results:
                if len(r['marked']) == 0: val = "0"
                elif len(r['marked']) > 1: val = "3"
                elif 0 in r['marked']: val = "1"
                elif 1 in r['marked']: val = "2"
                new_result_str += val
            
            read_num = error_row[1]
            self.db.update_scan_result(self.current_db_path, read_num, new_result_str, 1) # 강제 유효(1)
            
            self.update_statistics()
            QMessageBox.information(self, "완료", f"{read_num}번 자료가 수정되었습니다.")

    def update_statistics(self):
        """DB 통계(총매수, 오류매수) 갱신"""
        if not self.current_db_path: return
        total, normal, error = self.db.get_statistics(self.current_db_path)
        
        self.lbl_total.setText(str(total))
        self.lbl_check.setText(str(error)) 
        self.control_panel.txt_temp.setText(str(total))

    @pyqtSlot()
    def on_finished(self):
        # [기존 기능] 왼쪽 요약 테이블 추가
        place = self.cb_place.currentText()
        room = self.cb_room.currentText()
        count = str(self.current_session_count)
        
        row = self.summary_table.rowCount()
        self.summary_table.insertRow(row)
        self.summary_table.setItem(row, 0, self._item(place))
        self.summary_table.setItem(row, 1, self._item(room))
        self.summary_table.setItem(row, 2, self._item(count))
        
        # [수정] 시험실 번호 자동 증가 (콤보박스 인덱스 변경)
        current_idx = self.cb_room.currentIndex()
        # 다음 번호가 있으면(마지막 번호가 아니면) 하나 올림
        if current_idx < self.cb_room.count() - 1:
            self.cb_room.setCurrentIndex(current_idx + 1)
            # 상단 파란색 라벨도 갱신
            self.lbl_cur_room.setText(self.cb_room.currentText())

        QMessageBox.information(self, "완료", f"{place} - {room} 시험실 스캔 완료\n(총 {count}매)")
        self.reset_ui_state()
    @pyqtSlot(str)
    def on_error(self, msg):
        QMessageBox.warning(self, "오류", msg)
        self.reset_ui_state()

    def reset_ui_state(self):
        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_scan.setText("📄 현재시험실 스캔(R)")