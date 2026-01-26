from PySide2.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, 
                             QLabel, QSpinBox, QPushButton, QMessageBox, QGroupBox)
from database import DBManager

class FormSettingsDialog(QDialog):
    def __init__(self, parent=None, db_path=None):
        super().__init__(parent)
        self.setWindowTitle("OMR 양식(좌표) 설정")
        self.resize(450, 400)
        self.db = DBManager()
        self.db_path = db_path
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 1. 기준점 설정
        grp_anchor = QGroupBox("1. 기준점 (Anchor) 설정")
        form_anchor = QFormLayout()
        self.sb_ref_x = QSpinBox(); self.sb_ref_x.setRange(0, 3000)
        self.sb_ref_y = QSpinBox(); self.sb_ref_y.setRange(0, 3000)
        form_anchor.addRow("기준점 X좌표:", self.sb_ref_x)
        form_anchor.addRow("기준점 Y좌표:", self.sb_ref_y)
        grp_anchor.setLayout(form_anchor)
        layout.addWidget(grp_anchor)
        
        # 2. 문항 좌표 설정
        grp_pos = QGroupBox("2. 문항 위치 설정 (1번 문항 기준)")
        form_pos = QFormLayout()
        self.sb_start_y = QSpinBox(); self.sb_start_y.setRange(0, 3000)
        self.sb_gap_y = QSpinBox(); self.sb_gap_y.setRange(0, 500)
        self.sb_box_w = QSpinBox(); self.sb_box_w.setRange(10, 200)
        self.sb_box_h = QSpinBox(); self.sb_box_h.setRange(10, 200)
        
        form_pos.addRow("1번문항 Y시작점:", self.sb_start_y)
        form_pos.addRow("문항 간격 (Gap Y):", self.sb_gap_y)
        form_pos.addRow("박스 너비 (W):", self.sb_box_w)
        form_pos.addRow("박스 높이 (H):", self.sb_box_h)
        grp_pos.setLayout(form_pos)
        layout.addWidget(grp_pos)
        
        # 3. 찬/반 X좌표
        grp_x = QGroupBox("3. 찬성/반대 X좌표")
        form_x = QFormLayout()
        self.sb_agree_x = QSpinBox(); self.sb_agree_x.setRange(0, 3000)
        self.sb_disagree_x = QSpinBox(); self.sb_disagree_x.setRange(0, 3000)
        form_x.addRow("찬성(1) X좌표:", self.sb_agree_x)
        form_x.addRow("반대(2) X좌표:", self.sb_disagree_x)
        grp_x.setLayout(form_x)
        layout.addWidget(grp_x)

        btn_save = QPushButton("설정 저장")
        btn_save.setFixedHeight(40)
        btn_save.clicked.connect(self.save_data)
        layout.addWidget(btn_save)

        self.setLayout(layout)

    def load_data(self):
        if not self.db_path: return
        # 기본값은 현재 하드코딩된 값들
        self.sb_ref_x.setValue(int(self.db.get_setting(self.db_path, "ref_x", "100")))
        self.sb_ref_y.setValue(int(self.db.get_setting(self.db_path, "ref_y", "500")))
        
        self.sb_start_y.setValue(int(self.db.get_setting(self.db_path, "roi_start_y", "515")))
        self.sb_gap_y.setValue(int(self.db.get_setting(self.db_path, "roi_gap_y", "90")))
        
        self.sb_box_w.setValue(int(self.db.get_setting(self.db_path, "roi_w", "35")))
        self.sb_box_h.setValue(int(self.db.get_setting(self.db_path, "roi_h", "35")))
        
        self.sb_agree_x.setValue(int(self.db.get_setting(self.db_path, "roi_agree_x", "1130")))
        self.sb_disagree_x.setValue(int(self.db.get_setting(self.db_path, "roi_disagree_x", "1275")))

    def save_data(self):
        if not self.db_path: return
        self.db.save_setting(self.db_path, "ref_x", self.sb_ref_x.value())
        self.db.save_setting(self.db_path, "ref_y", self.sb_ref_y.value())
        self.db.save_setting(self.db_path, "roi_start_y", self.sb_start_y.value())
        self.db.save_setting(self.db_path, "roi_gap_y", self.sb_gap_y.value())
        self.db.save_setting(self.db_path, "roi_w", self.sb_box_w.value())
        self.db.save_setting(self.db_path, "roi_h", self.sb_box_h.value())
        self.db.save_setting(self.db_path, "roi_agree_x", self.sb_agree_x.value())
        self.db.save_setting(self.db_path, "roi_disagree_x", self.sb_disagree_x.value())
        
        QMessageBox.information(self, "저장", "양식 좌표가 저장되었습니다.\n스캐너 화면을 다시 열면 적용됩니다.")
        self.accept()
