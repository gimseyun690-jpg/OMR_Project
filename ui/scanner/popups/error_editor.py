import cv2
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTableWidget, QTableWidgetItem, QPushButton, 
                             QHeaderView, QSplitter, QCheckBox, QWidget, 
                             QAbstractItemView, QGroupBox, QGridLayout, QFrame, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont

class ErrorCorrectionDialog(QDialog):
    # 메인 윈도우에게 "다음/이전 파일 보여줘"라고 요청하는 신호
    request_next = pyqtSignal()
    request_prev = pyqtSignal()

    def __init__(self, parent=None, image_cv=None, scan_results=None, image_path=""):
        super().__init__(parent)
        self.setWindowTitle("조회/수정 점검 상태")
        
        # 윈도우 설정
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(1600, 900)
        
        self.image_cv = image_cv
        self.scan_results = scan_results # 리스트 딕셔너리 [{'q_num':1, 'marked':[0], 'status':'정상'}...]
        self.image_path = image_path
        self.exit_code = 0

        self.init_ui()
        self.connect_signals() # ★ 버튼 기능 연결
        self.showMaximized()
        
        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # [1] 상단 패널
        top_panel = QFrame()
        top_panel.setFixedHeight(100)
        top_panel.setStyleSheet("background-color: #F0F0F0; border-bottom: 1px solid #999;")
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(5, 5, 5, 5)

        # (1-1) 자료순번
        grp_idx = QGroupBox("자료순번")
        grp_idx.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #aaa; background: white; }")
        grid_idx = QVBoxLayout(grp_idx)
        self.lbl_idx = QLabel("1") # 나중에 실제 순번으로 교체 가능
        self.lbl_idx.setAlignment(Qt.AlignCenter)
        self.lbl_idx.setStyleSheet("color: red; font-size: 24px; font-weight: bold;")
        grid_idx.addWidget(self.lbl_idx)
        top_layout.addWidget(grp_idx)

        # (1-2) 이동/검색
        grp_nav = QGroupBox("이동/검색")
        grp_nav.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #aaa; background: white; }")
        grid_nav = QGridLayout(grp_nav)
        
        self.btn_prev = QPushButton("◀ 이전자료")
        self.btn_next = QPushButton("다음자료 ▶")
        self.btn_prev.setStyleSheet("padding: 5px;")
        self.btn_next.setStyleSheet("padding: 5px;")
        
        grid_nav.addWidget(self.btn_prev, 0, 0)
        grid_nav.addWidget(self.btn_next, 0, 1)
        top_layout.addWidget(grp_nav)

        # (1-3) 일괄 처리
        grp_batch = QGroupBox("일괄 처리")
        grp_batch.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #aaa; background: white; }")
        grid_batch = QGridLayout(grp_batch)
        
        self.btn_all_agree = QPushButton("✔ 전체찬성처리(1)")
        self.btn_all_agree.setStyleSheet("background-color: #E3F2FD; color: blue; font-weight: bold;")
        self.btn_all_disagree = QPushButton("✔ 전체반대처리(2)")
        self.btn_all_disagree.setStyleSheet("background-color: #E3F2FD; color: blue; font-weight: bold;")
        
        grid_batch.addWidget(self.btn_all_agree, 0, 0)
        grid_batch.addWidget(self.btn_all_disagree, 0, 1)
        top_layout.addWidget(grp_batch)

        # (1-4) 저장 버튼
        grp_save = QGroupBox("완료")
        grp_save.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #aaa; background: #E8F5E9; }")
        v_save = QVBoxLayout(grp_save)
        
        self.btn_save = QPushButton("확인/저장/다음점검(S)")
        self.btn_save.setFixedHeight(40)
        self.btn_save.setStyleSheet("""
            QPushButton { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #388E3C);
                color: white; font-weight: bold; font-size: 14px; border-radius: 5px;
            }
            QPushButton:hover { background: #66BB6A; }
        """)
        v_save.addWidget(self.btn_save)
        top_layout.addWidget(grp_save)

        main_layout.addWidget(top_panel)

        # [2] 중앙 작업 영역
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ccc; }")

        # 왼쪽: 이미지
        frame_left = QFrame()
        frame_left.setStyleSheet("background-color: #555;")
        layout_left = QVBoxLayout(frame_left)
        layout_left.setContentsMargins(0,0,0,0)
        
        self.lbl_info = QLabel(f"  📄 파일명: {self.image_path}")
        self.lbl_info.setFixedHeight(30)
        self.lbl_info.setStyleSheet("background-color: #333; color: white; font-weight: bold; padding: 5px;")
        layout_left.addWidget(self.lbl_info)

        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        layout_left.addWidget(self.lbl_image)
        splitter.addWidget(frame_left)

        # 오른쪽: 데이터
        frame_right = QWidget()
        layout_right = QVBoxLayout(frame_right)
        layout_right.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["안건", "찬성(1)", "반대(2)"])
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QHeaderView::section {
                background-color: #E0E0E0; padding: 6px; border: 1px solid #BDBDBD;
                font-weight: bold; font-size: 13px; color: black;
            }
            QTableWidget { 
                gridline-color: #BDBDBD; font-size: 14px; selection-background-color: #D1E8FF; selection-color: black;
            }
        """)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout_right.addWidget(self.table)

        self.lbl_log = QLabel()
        self.lbl_log.setFixedHeight(100)
        self.lbl_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_log.setStyleSheet("""
            background-color: white; border-top: 2px solid #aaa; 
            padding: 10px; color: #D32F2F; font-weight: bold; font-size: 13px;
        """)
        self.lbl_log.setText("오류 내용 대기중...")
        layout_right.addWidget(self.lbl_log)

        splitter.addWidget(frame_right)
        splitter.setSizes([1000, 600])

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def connect_signals(self):
        """버튼 기능 연결"""
        self.btn_save.clicked.connect(self.save_and_close)
        self.btn_prev.clicked.connect(self.on_prev)
        self.btn_next.clicked.connect(self.on_next)
        
        # 일괄 처리 버튼 연결
        self.btn_all_agree.clicked.connect(lambda: self.batch_process(0))    # 0: 찬성
        self.btn_all_disagree.clicked.connect(lambda: self.batch_process(1)) # 1: 반대

    def load_data(self):
        """데이터를 화면에 뿌리기"""
        self.update_image()

        if not self.scan_results:
            return

        self.table.setRowCount(len(self.scan_results))
        error_logs = []

        for row, data in enumerate(self.scan_results):
            # (1) 번호
            item_no = QTableWidgetItem(str(data['q_num']))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            # (2) 체크박스
            chk_agree = QCheckBox()
            chk_disagree = QCheckBox()
            chk_agree.setStyleSheet("QCheckBox::indicator { width: 20px; height: 20px; }")
            chk_disagree.setStyleSheet("QCheckBox::indicator { width: 20px; height: 20px; }")

            # 체크 상태 설정
            if 0 in data['marked']: chk_agree.setChecked(True)
            if 1 in data['marked']: chk_disagree.setChecked(True)

            # ★ 중요: 사용자가 체크를 바꾸면 데이터도 바뀌게 연결
            # lambda를 써서 현재 row와 어떤 체크박스인지(0 or 1) 넘겨줌
            chk_agree.clicked.connect(lambda checked, r=row: self.on_checkbox_click(r, 0, checked))
            chk_disagree.clicked.connect(lambda checked, r=row: self.on_checkbox_click(r, 1, checked))

            # 레이아웃에 넣기
            w1 = QWidget(); l1 = QHBoxLayout(w1); l1.addWidget(chk_agree); l1.setAlignment(Qt.AlignCenter); l1.setContentsMargins(0,0,0,0)
            w2 = QWidget(); l2 = QHBoxLayout(w2); l2.addWidget(chk_disagree); l2.setAlignment(Qt.AlignCenter); l2.setContentsMargins(0,0,0,0)
            self.table.setCellWidget(row, 1, w1)
            self.table.setCellWidget(row, 2, w2)

            # (3) 오류 강조
            status = data['status']
            if status != "정상":
                error_logs.append(f"[{data['q_num']}번 안건] {status} 오류")
                
                bg_color = QColor(255, 255, 255)
                txt_color = QColor(0, 0, 0)
                if status == "중복":
                    bg_color = QColor(0, 0, 255); txt_color = QColor(255, 255, 255)
                elif status == "공란":
                    bg_color = QColor(255, 200, 200); txt_color = QColor(255, 0, 0)
                
                item_no.setBackground(bg_color)
                item_no.setForeground(txt_color)

        if error_logs:
            self.lbl_log.setText("🚨 오류 내역:\n" + "\n".join(error_logs))
        else:
            self.lbl_log.setText("✅ 모든 항목이 정상입니다.")
            self.lbl_log.setStyleSheet("background-color: #E8F5E9; border-top: 2px solid #4CAF50; padding: 10px; color: #2E7D32; font-weight: bold; font-size: 13px;")

    def on_checkbox_click(self, row, col_type, checked):
        """체크박스를 누르면 실제 데이터(self.scan_results)를 업데이트"""
        target_list = self.scan_results[row]['marked']
        
        # 체크함
        if checked:
            if col_type not in target_list:
                target_list.append(col_type)
        # 체크 해제함
        else:
            if col_type in target_list:
                target_list.remove(col_type)
        
        target_list.sort() # 정렬
        
        # 상태 재판단 (정상/중복/공란)
        if len(target_list) == 0:
            self.scan_results[row]['status'] = "공란"
        elif len(target_list) == 1:
            self.scan_results[row]['status'] = "정상"
        else:
            self.scan_results[row]['status'] = "중복"
            
        # (선택사항) 상태가 바뀌었으니 테이블 색상도 즉시 갱신하고 싶다면:
        # self.load_data() # 하지만 깜빡거릴 수 있으므로, 로그 정도만 업데이트해도 됨

    def batch_process(self, target_val):
        """일괄 처리 로직"""
        # 모든 데이터 수정
        for data in self.scan_results:
            data['marked'] = [target_val] # [0] 또는 [1] 로 덮어쓰기
            data['status'] = "정상"       # 강제 정상 처리
        
        # 화면 새로고침
        self.load_data()
        QMessageBox.information(self, "알림", "일괄 처리가 완료되었습니다.")

    def keyPressEvent(self, event):
        """키보드 단축키 처리"""
        key = event.key()
        
        # 현재 선택된 행 가져오기
        current_row = self.table.currentRow()
        if current_row < 0:
            current_row = 0 # 선택 안됐으면 0번부터
            self.table.selectRow(0)

        # 1번 키: 찬성 체크
        if key == Qt.Key_1:
            self.scan_results[current_row]['marked'] = [0]
            self.scan_results[current_row]['status'] = "정상"
            self.load_data()
            # 다음 줄로 자동 이동 (편의 기능)
            if current_row < self.table.rowCount() - 1:
                self.table.selectRow(current_row + 1)

        # 2번 키: 반대 체크
        elif key == Qt.Key_2:
            self.scan_results[current_row]['marked'] = [1]
            self.scan_results[current_row]['status'] = "정상"
            self.load_data()
            if current_row < self.table.rowCount() - 1:
                self.table.selectRow(current_row + 1)

        # S 키: 저장 (Ctrl+S 아님, 그냥 S)
        elif key == Qt.Key_S:
            self.save_and_close()

        else:
            super().keyPressEvent(event)

    # =========================================================
    # ★ 핵심 수정 부분: exit_code 설정하여 메인에 알림
    # =========================================================
    def save_and_close(self):
        """저장(S) 버튼"""
        self.exit_code = 1 # 1 = 저장하고 다음으로
        self.accept()      # 창 닫기

    def on_prev(self):
        """이전 버튼"""
        self.exit_code = 2 # 2 = 저장 안 하고 이전으로
        self.request_prev.emit() # (선택사항) 신호도 보내고
        self.accept()      # 창 닫기

    def on_next(self):
        """다음 버튼"""
        self.exit_code = 3 # 3 = 저장 안 하고 다음으로
        self.request_next.emit() # (선택사항) 신호도 보내고
        self.accept()      # 창 닫기

    def update_image(self):
        if self.image_cv is not None:
            try:
                h, w, ch = self.image_cv.shape
                bytes_per_line = ch * w
                rgb_img = cv2.cvtColor(self.image_cv, cv2.COLOR_BGR2RGB)
                q_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)
                self.lbl_image.setPixmap(pixmap.scaled(self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except: pass

    def resizeEvent(self, event):
        self.update_image()
        super().resizeEvent(event)