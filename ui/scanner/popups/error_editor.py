import cv2
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTableWidget, QTableWidgetItem, QPushButton, 
                             QHeaderView, QSplitter, QCheckBox, QWidget, QAbstractItemView)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage, QColor, QFont

class ErrorCorrectionDialog(QDialog):
    def __init__(self, parent=None, image_cv=None, scan_results=None, image_path=""):
        super().__init__(parent)
        self.setWindowTitle("조회/수정 점검 상태")
        self.resize(1280, 720) # 스크린샷처럼 넓게
        
        self.image_cv = image_cv
        self.scan_results = scan_results
        self.image_path = image_path

        self.init_ui()
        self.load_data()

    def init_ui(self):
        # 전체 레이아웃
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # =================================================
        # [왼쪽] 이미지 뷰어
        # =================================================
        left_layout = QVBoxLayout()
        
        # 상단 정보 라벨
        self.lbl_info = QLabel(f"파일명: {self.image_path}")
        self.lbl_info.setStyleSheet("font-weight: bold; color: #333; margin-bottom: 5px;")
        left_layout.addWidget(self.lbl_info)

        # 이미지 들어갈 곳
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("background-color: #555; border: 1px solid #333;")
        self.lbl_image.setMinimumSize(600, 600)
        left_layout.addWidget(self.lbl_image)
        
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # =================================================
        # [오른쪽] 데이터 그리드 & 컨트롤
        # =================================================
        right_layout = QVBoxLayout()

        # 1. 상단 버튼바 (스크린샷 참조)
        btn_layout = QHBoxLayout()
        btn_next = QPushButton("확인/저장/다음점검(S)")
        btn_next.setFixedHeight(40)
        btn_next.setStyleSheet("""
            QPushButton { 
                background-color: #E3F2FD; border: 1px solid #2196F3; 
                font-weight: bold; font-size: 12px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #BBDEFB; }
        """)
        btn_next.clicked.connect(self.accept)
        btn_layout.addWidget(btn_next)
        right_layout.addLayout(btn_layout)

        # 2. 메인 테이블 (스크린샷 스타일 적용)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["안건", "찬성(1)", "반대(2)"])
        
        # 헤더 스타일
        self.table.setStyleSheet("""
            QHeaderView::section {
                background-color: #E0E0E0; padding: 4px; border: 1px solid #BDBDBD;
                font-weight: bold; font-size: 11px; color: black;
            }
            QTableWidget {
                gridline-color: #BDBDBD;
                font-size: 12px;
            }
        """)
        # 컬럼 너비 비율
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents) # 안건 번호는 좁게
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        # 행 선택시 한 줄 전체 선택
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        right_layout.addWidget(self.table)

        # 3. 하단 로그창 (오류 내용 표시)
        self.lbl_log = QLabel()
        self.lbl_log.setFixedHeight(80)
        self.lbl_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_log.setStyleSheet("""
            background-color: white; border: 2px solid #D32F2F; 
            padding: 5px; color: #D32F2F; font-weight: bold; font-size: 12px;
        """)
        self.lbl_log.setText("오류 내용이 없습니다.")
        right_layout.addWidget(self.lbl_log)

        right_widget = QWidget()
        right_widget.setLayout(right_layout)

        # 스플리터로 좌우 배치
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([750, 450]) # 초기 비율 설정

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def load_data(self):
        """데이터를 테이블에 채우고 색상 강조"""
        # 1. 이미지 표시
        if self.image_cv is not None:
            try:
                h, w, ch = self.image_cv.shape
                bytes_per_line = ch * w
                rgb_img = cv2.cvtColor(self.image_cv, cv2.COLOR_BGR2RGB)
                q_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(q_img)
                # 라벨 크기에 맞춰 축소 (비율 유지)
                self.lbl_image.setPixmap(pixmap.scaled(self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except:
                self.lbl_image.setText("이미지 로드 실패")

        # 2. 테이블 채우기
        if not self.scan_results:
            return

        self.table.setRowCount(len(self.scan_results))
        error_logs = []

        for row, data in enumerate(self.scan_results):
            # (1) 안건 번호
            item_no = QTableWidgetItem(str(data['q_num']))
            item_no.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_no)

            # (2) 체크박스 위젯 생성 (중앙 정렬)
            chk_agree = QCheckBox(); chk_agree.setStyleSheet("margin-left:50%; margin-right:50%;")
            chk_disagree = QCheckBox(); chk_disagree.setStyleSheet("margin-left:50%; margin-right:50%;")
            
            # 값 세팅
            if 0 in data['marked']: chk_agree.setChecked(True)
            if 1 in data['marked']: chk_disagree.setChecked(True)

            # 셀에 위젯 넣기 (레이아웃 이용)
            w1 = QWidget(); l1 = QHBoxLayout(w1); l1.addWidget(chk_agree); l1.setAlignment(Qt.AlignCenter); l1.setContentsMargins(0,0,0,0)
            w2 = QWidget(); l2 = QHBoxLayout(w2); l2.addWidget(chk_disagree); l2.setAlignment(Qt.AlignCenter); l2.setContentsMargins(0,0,0,0)
            
            self.table.setCellWidget(row, 1, w1)
            self.table.setCellWidget(row, 2, w2)

            # (3) ★★★ 오류 강조 로직 (스크린샷 스타일) ★★★
            status = data['status']
            if status != "정상":
                # 오류 로그 추가
                error_logs.append(f"[{data['q_num']}번 안건] {status} 오류가 있습니다.")

                # 행 색상 변경
                bg_color = QColor(255, 255, 255) # 기본 흰색
                txt_color = QColor(0, 0, 0)      # 기본 검정

                if status == "중복":
                    # 파란색 배경 (스크린샷의 6,7,8번 같은 스타일)
                    bg_color = QColor(0, 0, 255) 
                    txt_color = QColor(255, 255, 255) # 흰 글씨
                elif status == "공란":
                    # 빨간색 글씨/배경 (필요시)
                    bg_color = QColor(255, 200, 200) # 연한 빨강
                    txt_color = QColor(255, 0, 0)
                
                # 색상 적용 (안건 번호 셀)
                item_no.setBackground(bg_color)
                item_no.setForeground(txt_color)

                # 체크박스 배경도 맞춰주고 싶다면 위젯 스타일 수정 필요 (일단 패스)

        # 로그 업데이트
        if error_logs:
            self.lbl_log.setText("\n".join(error_logs))
        else:
            self.lbl_log.setText("✅ 모든 항목이 정상입니다.")
            self.lbl_log.setStyleSheet("background-color: #E8F5E9; border: 2px solid #4CAF50; color: #2E7D32; padding: 5px; font-weight: bold;")

    def resizeEvent(self, event):
        # 창 크기 변경 시 이미지 리로드
        if self.image_cv is not None:
             self.load_data()
        super().resizeEvent(event)