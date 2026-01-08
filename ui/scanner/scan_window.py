import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QFrame, QGroupBox, QComboBox, QSplitter,
                             QTableWidget, QHeaderView, QAbstractItemView, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QThread

# 부품 및 로직 import
from ui.scanner.components.control_panel import ControlPanel
from ui.scanner.components.data_grid import DataGrid
from logic.scanner_core import ScannerDevice  # ★ 스캐너 로직 추가

#저장된 파일 가져오기
class ScannerReadingView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.connect_signals()
        
        # 내부 변수 초기화
        self.total_read = 0
        self.worker = None
        
        # [추가] 시작하자마자 기존 파일 불러오기
        self.load_saved_images() 

    # ... 기존 init_ui, connect_signals 등 유지 ...

    # [★ 새로 추가할 함수] 폴더에 있는 이미지 읽어서 표에 채우기
    def load_saved_images(self):
        # 1. 경로 설정 (사용자님 경로 그대로 + r 붙임)
        scan_folder = r"C:\Users\김세윤1\Desktop\OMR_Project\data\scan_images"
        
        # [진단 1] 폴더가 있는지 검사
        if not os.path.exists(scan_folder):
            QMessageBox.critical(self, "오류", f"폴더를 찾을 수 없습니다!\n\n경로: {scan_folder}")
            return

        # 2. 파일 목록 읽기
        try:
            files = os.listdir(scan_folder)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"파일 목록을 읽을 수 없습니다.\n{e}")
            return

        # 3. 이미지 파일만 골라내기
        img_files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.bmp', '.png'))]
        img_files.sort()

        # [진단 2] 파일 개수 확인 팝업 (여기가 핵심!)
        if len(img_files) == 0:
            QMessageBox.warning(self, "알림", f"경로는 찾았는데 이미지 파일이 없습니다.\n\n발견된 전체 파일: {files}")
            return
        else:
            # 성공 시 안내 메시지 (테스트 후 주석 처리 가능)
            QMessageBox.information(self, "성공", f"이미지 {len(img_files)}개를 찾았습니다!\n표에 추가를 시작합니다.")

        # 4. 표에 추가하기
        self.main_grid.setRowCount(0)
        self.total_read = 0
        
        for filename in img_files:
            self.total_read += 1
            full_path = os.path.join(scan_folder, filename)
            
            row_data = [
                str(self.total_read),      # 판독번호
                "1",                       # 용지코드
                "스캐너1",                 # 고사장
                "1",                       # 시험실
                "불러옴",                  # 표기오류
                "대기",                    # 점검구분
                "-",                       # 표기내용
                full_path,                 # 앞면경로
                filename                   # 파일명
            ]
            self.main_grid.add_row_data(row_data)

        # 5. UI 갱신
        self.lbl_total.setText(str(self.total_read))
        self.lbl_cur_cnt.setText(str(self.total_read))
        self.control_panel.txt_temp.setText(str(self.total_read))
        self.main_grid.scrollToBottom()
# =========================================================
# [0] 스캔 작업을 담당할 일꾼 (백그라운드 스레드)
# =========================================================
class ScanWorker(QThread):
    image_scanned = pyqtSignal(str)
    scan_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    # [수정 1] 초기화할 때 윈도우 핸들(hwnd)을 받도록 변경
    def __init__(self, hwnd): 
        super().__init__()
        self.hwnd = hwnd # 핸들 저장
        self.scanner = ScannerDevice()
        self.is_running = True

    def run(self):
        try:
            # [수정 2] 저장해둔 핸들로 진짜 연결 시도!
            # scanner_core.py의 connect 함수는 (성공여부, 메시지)를 리턴함
            success, msg = self.scanner.connect(self.hwnd)
            
            if not success:
                self.error_occurred.emit(f"스캐너 연결 실패: {msg}")
                return

            # [수정 3] 장비 열기 (기본 장비)
            success, msg = self.scanner.open_scanner()
            if not success:
                self.error_occurred.emit(f"장비 열기 실패: {msg}")
                return

            # 4. 용지 감지
            if not self.scanner.check_paper():
                self.error_occurred.emit("급지대에 용지가 없습니다.")
                return

            # 5. 스캔 실행
            for image_path in self.scanner.scan():
                if not self.is_running: break
                self.image_scanned.emit(image_path)
            
            self.scan_finished.emit()

        except Exception as e:
            self.error_occurred.emit(str(e))
        
        finally:
            # 스캔 끝나면 연결 해제 (중요)
            self.scanner.close()

    def stop(self):
        self.is_running = False


# =========================================================
# [1] 메인 뷰 (디자인 유지 + 기능 연결)
# =========================================================
class ScannerReadingView(QWidget):
    # 메인 윈도우로 돌아가는 신호
    closed_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.connect_signals()
        
        # 내부 변수
        self.total_read = 0
        self.total_check = 0
        self.worker = None # 스레드 변수

    # ★★★ 디자인 코드는 사용자님이 주신 그대로 유지 ★★★
    def init_ui(self):
        # 전체 수직 레이아웃
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # =========================================================
        # [1] 상단 정보 패널 (Top Area) - 스크린샷과 동일한 디자인
        # =========================================================
        top_frame = QFrame()
        top_frame.setFixedHeight(120) # 높이 고정
        top_frame.setStyleSheet("background-color: #F0F0F0; border-bottom: 1px solid #A0A0A0;")
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(5)

        # --- (1-1) 좌측: 카운터 그룹 ---
        grp_cnt = QGroupBox()
        grp_cnt.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_cnt = QGridLayout(grp_cnt)
        grid_cnt.setContentsMargins(5, 5, 5, 5)
        grid_cnt.setVerticalSpacing(0)

        # 스타일
        st_label = "color: black; font-weight: bold; font-size: 11px; border: none;"
        st_blue_num = "color: blue; font-weight: bold; font-size: 20px; border: none;"
        st_red_num = "color: red; font-weight: bold; font-size: 20px; border: none;"
        st_box = "border: 1px solid #ccc; background-color: #fafafa;"

        # 총판독/총점검
        grid_cnt.addWidget(QLabel("총판독매수", styleSheet=st_label), 0, 0, alignment=Qt.AlignCenter)
        grid_cnt.addWidget(QLabel("총점검매수", styleSheet=st_label), 0, 1, alignment=Qt.AlignCenter)
        self.lbl_total = QLabel("0", styleSheet=st_blue_num); grid_cnt.addWidget(self.lbl_total, 1, 0, alignment=Qt.AlignCenter)
        self.lbl_check = QLabel("0", styleSheet=st_red_num); grid_cnt.addWidget(self.lbl_check, 1, 1, alignment=Qt.AlignCenter)
        
        # 구분선 역할의 빈 라벨
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #ccc;")
        grid_cnt.addWidget(line, 2, 0, 1, 2)

        # 현재 고사장/시험실/판독매수
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

        # --- (1-2) 중앙: 설정 (양식, 고사장) ---
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

        # --- (1-3) 우측: 오류점검 설정 ---
        grp_err = QGroupBox("오류점검")
        grp_err.setStyleSheet("background-color: white; border: 1px solid #999; font-size: 11px;")
        grid_err = QGridLayout(grp_err)
        
        self.cb_err_opt = QComboBox(); self.cb_err_opt.addItem("이미지오류(저장안함) 스캔시보기 / 표기오류 스캔완료후보기")
        self.cb_stop_opt = QComboBox(); self.cb_stop_opt.addItem("모든오류 스캔중단")
        
        grid_err.addWidget(QLabel("스캔시 오류점검창 보기 :", styleSheet="border:none;"), 0, 0)
        grid_err.addWidget(self.cb_err_opt, 0, 1)
        grid_err.addWidget(QLabel("오류점검시 스캔중단 :", styleSheet="border:none;"), 1, 0)
        grid_err.addWidget(self.cb_stop_opt, 1, 1)

        # --- (1-4) 우측 끝: 체크박스 ---
        grp_chk = QGroupBox("오류점검")
        grp_chk.setStyleSheet("background-color: white; border: 1px solid #999; font-size: 11px;")
        v_chk = QVBoxLayout(grp_chk)
        v_chk.addWidget(QLabel("☑ 전체공란 무효표 점검")) # QCheckBox 대신 디자인용 라벨로 처리
        v_chk.addWidget(QLabel("☑ 기타 무효표 점검"))
        
        # 레이아웃 비율 설정
        top_layout.addWidget(grp_cnt, 20)
        top_layout.addWidget(grp_set, 35)
        top_layout.addWidget(grp_err, 35)
        top_layout.addWidget(grp_chk, 10)
        
        main_layout.addWidget(top_frame)

        # =========================================================
        # [2] 하단 3단 분리 (좌측 표 | 중앙 표 | 우측 컨트롤)
        # =========================================================
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(3)
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
        # 테스트 데이터
        self.summary_table.insertRow(0)
        self.summary_table.setItem(0, 0, self._item("스캐너1"))
        self.summary_table.setItem(0, 1, self._item("1"))
        self.summary_table.setItem(0, 2, self._item("1"))

        # (2-2) 중앙: 메인 데이터 그리드 (부품 사용)
        self.main_grid = DataGrid()

        # (2-3) 우측: 컨트롤 패널 (부품 사용)
        self.control_panel = ControlPanel()

        splitter.addWidget(self.summary_table)
        splitter.addWidget(self.main_grid)
        splitter.addWidget(self.control_panel)

        # 초기 너비 비율 (픽셀 단위)
        splitter.setSizes([200, 1200, 260])
        splitter.setCollapsible(2, False) # 우측 패널은 안 접히게

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)
    
    # -------------------------------------------------------------
    # 여기 아래부터는 로직 연결 함수입니다 (디자인 영향 없음)
    # -------------------------------------------------------------

    def _item(self, text):
        """테이블 아이템 생성 헬퍼"""
        from PyQt5.QtWidgets import QTableWidgetItem
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def connect_signals(self):
        """버튼 기능 연결"""
        # 우측 패널의 [닫기] 버튼 -> 메인 화면 복귀
        self.control_panel.btn_close.clicked.connect(self.go_back_home)
        
        # [스캔] 버튼 -> 실제 스캔 시작 함수로 연결 (기존 run_scan_test 대체)
        self.control_panel.btn_scan.clicked.connect(self.start_scan)

    def go_back_home(self):
        self.closed_signal.emit()

    @pyqtSlot()
    def start_scan(self):
        """스캔 버튼 눌렀을 때 실행되는 실제 로직"""
        
        # [수정 4] 내 창의 핸들(ID)을 알아냄
        my_hwnd = int(self.winId())
        
        # [수정 5] 일꾼한테 핸들을 쥐여줌
        self.worker = ScanWorker(my_hwnd)
        
        # 신호 연결
        self.worker.image_scanned.connect(self.on_image_received)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        
        # UI 상태 변경
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_scan.setText("스캔중...")
        
        # 일 시작!
        self.worker.start()

    @pyqtSlot(str)
    def on_image_received(self, image_path):
        """이미지가 한 장 스캔될 때마다 호출됨"""
        self.total_read += 1
        
        # 1. 상단 숫자 갱신
        self.lbl_total.setText(str(self.total_read))
        self.lbl_cur_cnt.setText(str(self.total_read))
        self.control_panel.txt_temp.setText(str(self.total_read))

        # 2. 중앙 표에 데이터 추가
        # (실제로는 여기서 DB 저장 및 OMR 판독 결과를 넣어야 함)
        row_data = [
            str(self.total_read), # 판독번호
            "1",                  # 용지코드
            "스캐너1",            # 고사장
            "1",                  # 시험실
            "정상",               # 표기오류
            "완료",               # 점검구분
            "11111",              # 표기내용(테스트)
            image_path,           # 앞면경로
            "scan_img.jpg"        # 파일명
        ]
        self.main_grid.add_row_data(row_data)
        self.main_grid.scrollToBottom()

    @pyqtSlot()
    def on_finished(self):
        """스캔 완료 시"""
        QMessageBox.information(self, "완료", "스캔 작업이 완료되었습니다.")
        self.reset_ui_state()

    @pyqtSlot(str)
    def on_error(self, msg):
        """에러 발생 시"""
        QMessageBox.warning(self, "오류", msg)
        self.reset_ui_state()

    def reset_ui_state(self):
        """버튼 상태 원래대로 복구"""
        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_scan.setText("📄 현재시험실 스캔(R)")

