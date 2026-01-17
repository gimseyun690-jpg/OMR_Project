from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QCheckBox, 
                             QGroupBox, QLineEdit, QLabel, QFrame, QHBoxLayout, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt

class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)

        # ----------------------------------------------------
        # 1. 메인 버튼들 (그라데이션 스타일)
        # ----------------------------------------------------
        # 파란색 그라데이션 버튼 스타일
        style_blue = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E1F5FE, stop:1 #81D4FA);
                border: 1px solid #0277BD; border-radius: 4px; padding: 8px;
                font-size: 13px; font-weight: bold; color: black; text-align: left;
            }
            QPushButton:hover { background: #B3E5FC; }
            QPushButton:pressed { background: #4FC3F7; }
        """
        # 초록색 그라데이션 버튼 스타일
        style_green = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E8F5E9, stop:1 #A5D6A7);
                border: 1px solid #2E7D32; border-radius: 4px; padding: 8px;
                font-size: 13px; font-weight: bold; color: black; text-align: left;
            }
            QPushButton:hover { background: #C8E6C9; }
        """
        # 빨간색(닫기) 그라데이션 버튼 스타일
        style_red = """
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFEBEE, stop:1 #EF9A9A);
                border: 1px solid #C62828; border-radius: 4px; padding: 8px;
                font-size: 13px; font-weight: bold; color: black;
            }
            QPushButton:hover { background: #FFCDD2; }
        """

        self.btn_scan = QPushButton("📄 현재시험실 스캔(R)"); self.btn_scan.setStyleSheet(style_blue)
        self.btn_check = QPushButton("✔️ 오류미확인 점검(A)"); self.btn_check.setStyleSheet(style_green)
        self.btn_next = QPushButton("▶ 다음시험실 스캔(N)"); self.btn_next.setStyleSheet(style_blue)
        self.btn_demo = QPushButton("📂 테스트 이미지 불러오기")

        
        layout.addWidget(self.btn_scan)
        layout.addWidget(self.btn_check)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_demo)


        # ----------------------------------------------------
        # 2. 체크박스
        # ----------------------------------------------------
        self.chk_next = QCheckBox("오류점검후 다음시험실 스캔")
        self.chk_next.setStyleSheet("color: blue; font-weight: bold; font-size: 11px;")
        self.chk_next.setChecked(True)
        layout.addWidget(self.chk_next)

        # ----------------------------------------------------
        # 3. 닫기 버튼
        # ----------------------------------------------------
        layout.addSpacing(5)
        self.btn_close = QPushButton("🚪 닫기(C)"); self.btn_close.setStyleSheet(style_red)
        layout.addWidget(self.btn_close)

        # ----------------------------------------------------
        # 4. 임시판독매수 (흰색 박스)
        # ----------------------------------------------------
        layout.addSpacing(10)
        grp_temp = QGroupBox()
        grp_temp.setStyleSheet("background-color: #f9f9f9; border: 1px solid #ccc; border-radius: 3px;")
        v_temp = QVBoxLayout(grp_temp)
        v_temp.setContentsMargins(5,5,5,5)
        
        lbl_t = QLabel("임시판독매수 :"); lbl_t.setStyleSheet("font-weight:bold; border:none;")
        v_temp.addWidget(lbl_t)
        
        h_input = QHBoxLayout()
        lbl_sub = QLabel("임시판독매수 :"); lbl_sub.setStyleSheet("border:none;")
        self.txt_temp = QLineEdit("0"); self.txt_temp.setAlignment(Qt.AlignRight)
        self.txt_temp.setStyleSheet("border: 1px solid #999; padding: 2px; font-size: 14px;")
        h_input.addWidget(lbl_sub)
        h_input.addWidget(self.txt_temp)
        v_temp.addLayout(h_input)
        
        btn_reset = QPushButton("🗑️ 임시판독매수 초기화(I)")
        btn_reset.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E3F2FD, stop:1 #90CAF9);
            border: 1px solid #64B5F6; border-radius: 3px; font-weight: bold;
        """)
        v_temp.addWidget(btn_reset)
        layout.addWidget(grp_temp)

        # ----------------------------------------------------
        # 5. 이전 임시판독매수 보관
        # ----------------------------------------------------
        grp_prev = QGroupBox("이전 임시판독매수 보관(좌측이 최근)")
        grp_prev.setStyleSheet("font-size: 10px; border: 1px solid #ccc;")
        v_prev = QVBoxLayout(grp_prev)
        txt_prev = QLineEdit()
        txt_prev.setReadOnly(True)
        v_prev.addWidget(txt_prev)
        layout.addWidget(grp_prev)

        # ----------------------------------------------------
        # 6. 이미지 미리보기 (체크무늬 배경)
        # ----------------------------------------------------
        layout.addStretch(1) # 빈 공간 채우기
        
        self.preview_frame = QFrame()
        self.preview_frame.setFrameShape(QFrame.StyledPanel)
        self.preview_frame.setFixedSize(200, 250) # 세로로 긴 미리보기
        # 체크무늬 패턴 스타일 (CSS로 구현)
        self.preview_frame.setStyleSheet("""
            background-color: #eee;
            background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc),
                              linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc);
            background-size: 20px 20px;
            background-position: 0 0, 10px 10px;
            border: 1px solid #888;
        """)
        
        # 중앙 정렬을 위한 레이아웃
        h_preview = QHBoxLayout()
        h_preview.addStretch(1)
        h_preview.addWidget(self.preview_frame)
        h_preview.addStretch(1)
        
        layout.addLayout(h_preview)

        self.setLayout(layout)