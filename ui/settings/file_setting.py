import os
from PySide2.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, 
                             QMessageBox, QLineEdit, QLabel, QGroupBox, QFileDialog)
from PySide2.QtCore import Signal, Qt
from database import DBManager # 방금 만든 DB매니저 불러오기

class FileSettingsDialog(QDialog):
    # 메인 화면으로 "나 이 파일 선택했어!"라고 알려주는 신호
    db_selected_signal = Signal(str, str) # (경로, 제목)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("파일 설정 (DB 관리)")
        self.resize(800, 500)
        self.db = DBManager() # DB 매니저 연결
        self.init_ui()
        self.apply_white_mode()
        self.load_list()

    def init_ui(self):
        layout = QVBoxLayout()

        # 1. 파일 목록 테이블
        self.table = QTableWidget()
        self.table.setObjectName("dbFileTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["파일명", "제목", "경로", "생성일"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows) # 줄 단위 선택
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # 2. 버튼 영역
        btn_layout = QHBoxLayout()
        
        btn_new = QPushButton("📄 새 DB 생성")
        btn_new.clicked.connect(self.create_new_db)
        
        btn_select = QPushButton("📂 선택 열기")
        btn_select.clicked.connect(self.select_db)
        
        btn_del = QPushButton("🗑️ 목록 삭제")
        btn_del.clicked.connect(self.delete_db)

        # 스타일 꾸미기 (선택사항)
        btn_new.setStyleSheet("background-color: #E3F2FD; font-weight: bold; padding: 10px;")
        btn_select.setStyleSheet("background-color: #E8F5E9; font-weight: bold; padding: 10px;")
        
        btn_layout.addWidget(btn_new)
        btn_layout.addWidget(btn_select)
        btn_layout.addWidget(btn_del)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def apply_white_mode(self):
        self.setObjectName("fileSettingsDialog")
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            """
            #fileSettingsDialog {
                background-color: #FFFFFF;
                color: #000000;
            }
            #fileSettingsDialog QWidget {
                background-color: #FFFFFF;
                color: #000000;
            }
            #dbFileTable {
                background-color: #FFFFFF;
                alternate-background-color: #F8FAFC;
                color: #111111;
                gridline-color: #DDE3EA;
                border: 1px solid #DDE3EA;
            }
            #dbFileTable::item {
                background-color: #FFFFFF;
                color: #111111;
            }
            #dbFileTable::item:selected {
                background-color: #DCEBFF;
                color: #000000;
            }
            #fileSettingsDialog QHeaderView::section {
                background-color: #F1F5F9;
                color: #111111;
                border: 1px solid #DDE3EA;
                padding: 4px;
                font-weight: bold;
            }
            #fileSettingsDialog QTableCornerButton::section {
                background-color: #F1F5F9;
                border: 1px solid #DDE3EA;
            }
            """
        )

    def load_list(self):
        """DB에서 목록 가져와서 테이블에 뿌리기"""
        self.table.setRowCount(0)
        files = self.db.get_all_files() # DBManager 사용!
        
        for i, (filename, title, full_path, created_at) in enumerate(files):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(filename))
            self.table.setItem(i, 1, QTableWidgetItem(title))
            self.table.setItem(i, 2, QTableWidgetItem(full_path))
            self.table.setItem(i, 3, QTableWidgetItem(created_at))

    def create_new_db(self):
        """새 파일 만들기 (간단한 입력창)"""
        # 저장할 경로 선택
        path, _ = QFileDialog.getSaveFileName(self, "새 DB 파일 생성", "", "OMR Data (*.SSDB)")
        if not path: return

        # 제목 입력 받기 (간단하게 inputDialog 대신 커스텀 로직)
        filename = os.path.basename(path)
        title = "새 프로젝트" # 편의상 고정 (나중에 입력창 추가 가능)
        
        # DB에 등록 (이때 실제 파일과 테이블도 생성됨)
        self.db.add_file_to_master(path, filename, title)
        self.load_list() # 목록 새로고침
        QMessageBox.information(self, "완료", f"새 파일이 생성되었습니다.\n{filename}")

    def delete_db(self):
        row = self.table.currentRow()
        if row < 0: return
        
        path = self.table.item(row, 2).text()
        self.db.delete_file_from_master(path)
        self.load_list()

    def select_db(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "주의", "열고 싶은 파일을 선택해주세요.")
            return
            
        path = self.table.item(row, 2).text()
        title = self.table.item(row, 1).text()
        
        # 메인 화면으로 신호 발사! 🚀
        self.db_selected_signal.emit(path, title)
        self.close()
