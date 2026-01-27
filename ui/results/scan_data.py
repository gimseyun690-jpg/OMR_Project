from PySide2.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QHeaderView, 
                             QTableWidgetItem, QPushButton, QHBoxLayout, QLabel)
from PySide2.QtCore import Qt
from database import DBManager

class ScanDataView(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 상단 정보바
        top_layout = QHBoxLayout()
        self.lbl_count = QLabel("총 판독매수: 0 건")
        self.lbl_count.setStyleSheet("font-size: 14px; font-weight: bold; color: #333;")
        top_layout.addWidget(self.lbl_count)
        top_layout.addStretch()
        
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self.load_data)
        top_layout.addWidget(btn_refresh)
        layout.addLayout(top_layout)

        # 메인 데이터 그리드
        self.table = QTableWidget()
        # 컬럼: 판독번호, 구분, 안건1~5
        headers = ["판독번호", "구분", "제1호", "제2호", "제3호", "제4호", "제5호"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("""
            QHeaderView::section { background-color: #F5F5F5; border: 1px solid #ddd; font-weight: bold; }
            QTableWidget { alternate-background-color: #FAFAFA; }
        """)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def set_db_path(self, path):
        self.current_db_path = path
        self.load_data()

    def load_data(self):
        if not self.current_db_path: return
        
        rows = self.db.get_raw_data_for_grid(self.current_db_path)
        self.table.setRowCount(len(rows))
        self.lbl_count.setText(f"총 판독매수: {len(rows)} 건")

        for r_idx, row in enumerate(rows):
            read_num = row[0]
            sheet_code = row[1]
            result_str = row[2] or ""  # 예: "12130"
            
            self.table.setItem(r_idx, 0, self._item(read_num))
            self.table.setItem(r_idx, 1, self._item(sheet_code))
            
            # 결과 문자열 파싱 (1, 2, 3=중복, 0=기권)
            for c_idx, char in enumerate(result_str):
                if c_idx < 5:
                    val = char
                    if char == '3': val = "중복"
                    elif char == '0': val = ""
                    self.table.setItem(r_idx, 2 + c_idx, self._item(val))

    def _item(self, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        return item
