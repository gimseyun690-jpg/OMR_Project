from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, 
                             QSpinBox, QDoubleSpinBox, QPushButton, QMessageBox, QGroupBox)
from database import DBManager

class MarkSettingsDialog(QDialog):
    def __init__(self, parent=None, db_path=None):
        super().__init__(parent)
        self.setWindowTitle("기표 인식 설정")
        self.resize(400, 300)
        self.db = DBManager()
        self.db_path = db_path
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()
        
        grp = QGroupBox("인식 민감도 설정")
        form = QFormLayout()
        
        # 1. 흑백 기준값
        self.sb_threshold = QSpinBox()
        self.sb_threshold.setRange(0, 255)
        self.sb_threshold.setSingleStep(5)
        self.sb_threshold.setToolTip("값이 낮을수록 진한 마킹만 인정합니다. (기본: 140)")
        form.addRow("흑백 임계값 (Threshold):", self.sb_threshold)
        
        # 2. 마킹 인정 비율
        self.sb_pixel_ratio = QDoubleSpinBox()
        self.sb_pixel_ratio.setRange(0.0, 1.0)
        self.sb_pixel_ratio.setSingleStep(0.05)
        self.sb_pixel_ratio.setToolTip("박스 안에 몇 %가 채워져야 마킹으로 볼지 설정 (기본: 0.25 = 25%)")
        form.addRow("마킹 인정 비율 (Ratio):", self.sb_pixel_ratio)
        
        grp.setLayout(form)
        layout.addWidget(grp)
        
        lbl_info = QLabel("※ 인식이 잘 안될 경우 임계값을 조절해보세요.\n(보통 120~160 사이 권장)")
        lbl_info.setStyleSheet("color: blue;")
        layout.addWidget(lbl_info)
        
        btn_save = QPushButton("저장")
        btn_save.clicked.connect(self.save_data)
        layout.addWidget(btn_save)
        
        self.setLayout(layout)

    def load_data(self):
        if not self.db_path: return
        thresh = self.db.get_setting(self.db_path, "omr_threshold", "140")
        ratio = self.db.get_setting(self.db_path, "omr_pixel_ratio", "0.25")
        
        self.sb_threshold.setValue(int(thresh))
        self.sb_pixel_ratio.setValue(float(ratio))

    def save_data(self):
        if not self.db_path: return
        self.db.save_setting(self.db_path, "omr_threshold", self.sb_threshold.value())
        self.db.save_setting(self.db_path, "omr_pixel_ratio", self.sb_pixel_ratio.value())
        QMessageBox.information(self, "저장", "인식 설정이 저장되었습니다.")
        self.accept()