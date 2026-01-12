from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, 
                             QGridLayout, QTableWidget, QHeaderView, QPushButton, 
                             QTableWidgetItem)
from PyQt5.QtCore import Qt
from database import DBManager

class VoteCountView(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. 상단 집계 옵션 (디자인 요소)
        grp_check = QGroupBox("집계 대상 선택")
        grp_check.setStyleSheet("font-weight: bold; background-color: white;")
        grid_check = QGridLayout(grp_check)
        grid_check.addWidget(QLabel("☑ 1. 서면결의서(청색)"), 0, 0)
        grid_check.addWidget(QLabel("☑ 2. 현장투표용지(녹색)"), 1, 0)
        layout.addWidget(grp_check)

        # 2. 결과 테이블 (문항별 득표수)
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["안건명", "찬성(1)", "반대(2)", "기권/무효"])
        
        # 헤더 스타일
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("""
            QHeaderView::section { background-color: #E1F5FE; border: 1px solid #90CAF9; font-weight: bold; }
            QTableWidget { gridline-color: #ccc; font-size: 13px; }
        """)
        layout.addWidget(self.table)

        # 3. 하단 버튼
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 결과 산출/새로고침")
        self.btn_refresh.setMinimumHeight(40)
        self.btn_refresh.setStyleSheet("background-color: #E8F5E9; font-weight: bold;")
        self.btn_refresh.clicked.connect(self.load_data)
        
        self.btn_export = QPushButton("💾 엑셀 저장(F)")
        self.btn_export.setMinimumHeight(40)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_export)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def set_db_path(self, path):
        """메인에서 DB 경로를 받으면 저장하고 데이터 로드"""
        self.current_db_path = path
        self.load_data()

    def load_data(self):
        if not self.current_db_path: return
        
        # DB에서 투표 결과 집계 가져오기
        stats = self.db.get_vote_counts(self.current_db_path, q_count=5)
        
        self.table.setRowCount(len(stats))
        for row, (q_num, counts) in enumerate(stats.items()):
            self.table.setItem(row, 0, self._item(f"제{q_num}호 안건"))
            self.table.setItem(row, 1, self._item(str(counts['1']))) # 찬성
            self.table.setItem(row, 2, self._item(str(counts['2']))) # 반대
            # 기권(0) + 중복(3) 등을 합쳐서 기타로 표시
            others = counts['0'] + counts['3']
            self.table.setItem(row, 3, self._item(str(others))) 

    def _item(self, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        return item