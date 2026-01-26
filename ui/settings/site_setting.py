from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QListWidget, QLineEdit, QPushButton, QMessageBox, QGroupBox)
from database import DBManager

class SiteSettingsDialog(QDialog):
    def __init__(self, parent=None, db_path=None):
        super().__init__(parent)
        self.setWindowTitle("고사장 및 시험실 설정")
        self.resize(500, 400)
        self.db = DBManager()
        self.db_path = db_path
        
        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QHBoxLayout()

        # === 1. 왼쪽: 고사장(스캐너) 관리 ===
        grp_scanner = QGroupBox("판독 고사장 (스캐너명)")
        v_scanner = QVBoxLayout()
        
        self.list_scanner = QListWidget()
        v_scanner.addWidget(self.list_scanner)
        
        h_scanner = QHBoxLayout()
        self.txt_scanner = QLineEdit()
        self.txt_scanner.setPlaceholderText("예: 스캐너1")
        btn_add_scanner = QPushButton("추가")
        btn_add_scanner.clicked.connect(self.add_scanner)
        btn_del_scanner = QPushButton("삭제")
        btn_del_scanner.clicked.connect(self.del_scanner)
        
        h_scanner.addWidget(self.txt_scanner)
        h_scanner.addWidget(btn_add_scanner)
        h_scanner.addWidget(btn_del_scanner)
        v_scanner.addLayout(h_scanner)
        grp_scanner.setLayout(v_scanner)

        # === 2. 오른쪽: 시험실 관리 ===
        grp_room = QGroupBox("시험실 번호")
        v_room = QVBoxLayout()
        
        self.list_room = QListWidget()
        v_room.addWidget(self.list_room)
        
        h_room = QHBoxLayout()
        self.txt_room = QLineEdit()
        self.txt_room.setPlaceholderText("예: 01")
        btn_add_room = QPushButton("추가")
        btn_add_room.clicked.connect(self.add_room)
        btn_del_room = QPushButton("삭제")
        btn_del_room.clicked.connect(self.del_room)
        
        h_room.addWidget(self.txt_room)
        h_room.addWidget(btn_add_room)
        h_room.addWidget(btn_del_room)
        v_room.addLayout(h_room)
        grp_room.setLayout(v_room)

        layout.addWidget(grp_scanner)
        layout.addWidget(grp_room)
        
        # 하단 저장 버튼
        main_layout = QVBoxLayout()
        main_layout.addLayout(layout)
        btn_save = QPushButton("설정 저장 및 닫기")
        btn_save.setFixedHeight(40)
        btn_save.clicked.connect(self.save_data)
        main_layout.addWidget(btn_save)
        
        self.setLayout(main_layout)

    def load_data(self):
        if not self.db_path: return
        # DB에서 콤마(,)로 구분된 문자열을 가져와 리스트로 변환
        scanners = self.db.get_setting(self.db_path, "site_scanners", "스캐너1,스캐너2")
        rooms = self.db.get_setting(self.db_path, "site_rooms", "1,2,3,4,5")
        
        self.list_scanner.addItems(scanners.split(","))
        self.list_room.addItems(rooms.split(","))

    def add_scanner(self):
        text = self.txt_scanner.text().strip()
        if text:
            self.list_scanner.addItem(text)
            self.txt_scanner.clear()

    def del_scanner(self):
        row = self.list_scanner.currentRow()
        if row >= 0: self.list_scanner.takeItem(row)

    def add_room(self):
        text = self.txt_room.text().strip()
        if text:
            self.list_room.addItem(text)
            self.txt_room.clear()

    def del_room(self):
        row = self.list_room.currentRow()
        if row >= 0: self.list_room.takeItem(row)

    def save_data(self):
        if not self.db_path: return
        
        # 리스트 위젯의 항목들을 콤마 문자열로 합침
        scanners = ",".join([self.list_scanner.item(i).text() for i in range(self.list_scanner.count())])
        rooms = ",".join([self.list_room.item(i).text() for i in range(self.list_room.count())])
        
        self.db.save_setting(self.db_path, "site_scanners", scanners)
        self.db.save_setting(self.db_path, "site_rooms", rooms)
        
        QMessageBox.information(self, "저장", "고사장 및 시험실 설정이 저장되었습니다.")
        self.accept()
