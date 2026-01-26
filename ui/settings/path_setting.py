from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QMessageBox, QGroupBox)
from database import DBManager
import os

class PathSettingsDialog(QDialog):
    def __init__(self, parent=None, db_path=None):
        super().__init__(parent)
        self.setWindowTitle("경로 설정")
        self.resize(500, 200)
        self.db = DBManager()
        self.db_path = db_path
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()
        
        grp = QGroupBox("이미지 저장 경로")
        v_layout = QVBoxLayout()
        
        lbl_desc = QLabel("스캔한 이미지가 저장될 폴더를 지정하세요.")
        lbl_desc.setStyleSheet("color: #666;")
        v_layout.addWidget(lbl_desc)
        
        h_layout = QHBoxLayout()
        self.txt_path = QLineEdit()
        self.txt_path.setReadOnly(True)
        
        btn_browse = QPushButton("폴더 찾기...")
        btn_browse.clicked.connect(self.browse_folder)
        
        h_layout.addWidget(self.txt_path)
        h_layout.addWidget(btn_browse)
        v_layout.addLayout(h_layout)
        
        grp.setLayout(v_layout)
        layout.addWidget(grp)
        
        btn_save = QPushButton("저장")
        btn_save.clicked.connect(self.save_data)
        layout.addWidget(btn_save)
        
        self.setLayout(layout)

    def load_data(self):
        if not self.db_path: return
        # 기본값: 현재 프로젝트 폴더 안의 data/scan_images
        default_path = os.path.abspath(os.path.join("data", "scan_images"))
        saved_path = self.db.get_setting(self.db_path, "image_save_path", default_path)
        self.txt_path.setText(saved_path)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "이미지 저장 폴더 선택")
        if folder:
            self.txt_path.setText(folder)

    def save_data(self):
        if not self.db_path: return
        path = self.txt_path.text()
        self.db.save_setting(self.db_path, "image_save_path", path)
        QMessageBox.information(self, "저장", "경로 설정이 저장되었습니다.")
        self.accept()
