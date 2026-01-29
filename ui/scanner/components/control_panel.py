from PySide2.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QCheckBox, 
                             QGroupBox, QLineEdit, QLabel, QFrame, QHBoxLayout, QSpacerItem, QSizePolicy,
                             QGraphicsDropShadowEffect)
from PySide2.QtCore import Qt, QPointF, QPropertyAnimation, QEasingCurve
from ui.scanner.components.image_viewer import ImageViewer

class HoverShadowButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setAttribute(Qt.WA_Hover, True)
        self._init_shadow()

    def _init_shadow(self):
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 1)
        self._shadow.setColor(Qt.black)
        self.setGraphicsEffect(self._shadow)

        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(140)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._offset_anim = QPropertyAnimation(self._shadow, b"offset", self)
        self._offset_anim.setDuration(140)
        self._offset_anim.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, event):
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(16)
        self._shadow_anim.start()

        self._offset_anim.stop()
        self._offset_anim.setStartValue(self._shadow.offset())
        self._offset_anim.setEndValue(QPointF(0, 3))
        self._offset_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(8)
        self._shadow_anim.start()

        self._offset_anim.stop()
        self._offset_anim.setStartValue(self._shadow.offset())
        self._offset_anim.setEndValue(QPointF(0, 1))
        self._offset_anim.start()
        super().leaveEvent(event)

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

        self.btn_scan = HoverShadowButton("📄 현재시험실 스캔(R)"); self.btn_scan.setStyleSheet(style_blue)
        self.btn_check = HoverShadowButton("✔️ 오류미확인 점검(A)"); self.btn_check.setStyleSheet(style_green)
        self.btn_next = HoverShadowButton("▶ 다음시험실 스캔(N)"); self.btn_next.setStyleSheet(style_blue)
        self.btn_demo = HoverShadowButton("📂 이미지 불러오기")
        self.btn_stop = HoverShadowButton("⏹ 스캔중단/종료(E)"); self.btn_stop.setStyleSheet(style_red)
        self.btn_retry = HoverShadowButton("↻ 재시도(T)"); self.btn_retry.setStyleSheet(style_blue)
        self.btn_retry.setEnabled(False)

        
        layout.addWidget(self.btn_scan)
        layout.addWidget(self.btn_check)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_demo)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_retry)


        # ----------------------------------------------------
        # 2. 체크박스
        # ----------------------------------------------------
        self.chk_next = QCheckBox("오류점검후 다음시험실 스캔")
        self.chk_next.setStyleSheet("color: blue; font-weight: bold; font-size: 11px;")
        self.chk_next.setChecked(True)
        layout.addWidget(self.chk_next)

        self.chk_auto_retry = QCheckBox("오류시 자동 재시도")
        self.chk_auto_retry.setStyleSheet("color: #444; font-weight: bold; font-size: 11px;")
        self.chk_auto_retry.setChecked(False)
        layout.addWidget(self.chk_auto_retry)

        # ----------------------------------------------------
        # 3. 닫기 버튼
        # ----------------------------------------------------
        layout.addSpacing(5)
        self.btn_close = HoverShadowButton("🚪 닫기(C)"); self.btn_close.setStyleSheet(style_red)
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
        
        btn_reset = HoverShadowButton("🗑️ 임시판독매수 초기화(I)")
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
        grp_prev.setMinimumHeight(70)
        v_prev = QVBoxLayout(grp_prev)
        v_prev.setContentsMargins(5, 5, 5, 5)
        txt_prev = QLineEdit()
        txt_prev.setReadOnly(True)
        v_prev.addWidget(txt_prev)
        layout.addWidget(grp_prev)

        # ----------------------------------------------------
        # 6. 이미지 미리보기 (체크무늬 배경)
        # ----------------------------------------------------
        layout.addStretch(1) # 빈 공간 채우기
        
        self.image_viewer = ImageViewer(width=200, height=210)
        
        # 중앙 정렬을 위한 레이아웃
        h_preview = QHBoxLayout()
        h_preview.addStretch(1)
        h_preview.addWidget(self.image_viewer)
        h_preview.addStretch(1)
        
        layout.addLayout(h_preview)

        self.setLayout(layout)

