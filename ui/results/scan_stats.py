from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QHeaderView, 
                             QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView)
from PyQt5.QtCore import Qt
from database import DBManager

class ScanStatsView(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 버튼바
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_refresh = QPushButton("조회/새로고침")
        btn_refresh.setMinimumHeight(35)
        btn_refresh.clicked.connect(self.load_data)
        btn_layout.addWidget(btn_refresh)
        layout.addLayout(btn_layout)

        # 통계 테이블
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["고사장(스캐너)", "시험실", "정상판독", "오류/미점검"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        self.table.setStyleSheet("""
            QHeaderView::section { background-color: #FFF3E0; border: 1px solid #FFCC80; font-weight: bold; }
            QTableWidget { font-size: 13px; }
        """)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def set_db_path(self, path):
        self.current_db_path = path
        self.load_data()

    def load_data(self):
        if not self.current_db_path: return
        
        # 고사장별 통계 가져오기
        rows = self.db.get_summary_by_scanner(self.current_db_path)
        
        self.table.setRowCount(len(rows) + 1) # 합계 줄 포함
        
        total_read = 0
        total_error = 0

        # 데이터 채우기
        for i, row in enumerate(rows):
            scanner, room, read_cnt, err_cnt = row
            # read_cnt는 전체 개수이므로, 정상 = 전체 - 오류
            normal_cnt = read_cnt - err_cnt
            
            total_read += normal_cnt
            total_error += err_cnt
            
            self.table.setItem(i, 0, self._item(scanner))
            self.table.setItem(i, 1, self._item(room))
            self.table.setItem(i, 2, self._item(str(normal_cnt)))
            self.table.setItem(i, 3, self._item(str(err_cnt)))
            
        # 맨 아래 '합계' 줄 추가
        last = len(rows)
        self.table.setItem(last, 0, self._item("전체 합계"))
        self.table.setItem(last, 1, self._item("-"))
        self.table.setItem(last, 2, self._item(str(total_read)))
        self.table.setItem(last, 3, self._item(str(total_error)))
        
        # 합계 줄 강조
        for c in range(4):
            item = self.table.item(last, c)
            item.setBackground(Qt.yellow)
            item.setFont(self.font()) # 볼드 처리 등 가능

    def _item(self, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        return item