from PySide2.QtWidgets import QTableWidget, QHeaderView, QAbstractItemView, QTableWidgetItem
from PySide2.QtCore import Qt

class DataGrid(QTableWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        # 컬럼명 그대로
        headers = ["판독번호", "용지코드", "판독고사장", "판독시험실", "표기오류", "점검구분", "표기내용", "앞면경로", "앞면파일명"]
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        
        # 스타일링
        self.verticalHeader().setVisible(False) # 행번호 숨김
        self.setAlternatingRowColors(True)      # 줄무늬
        self.setSelectionBehavior(QAbstractItemView.SelectRows) # 행 단위 선택
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setStyleSheet("""
            QTableWidget { background-color: white; gridline-color: #d0d0d0; }
            QHeaderView::section { 
                background-color: #E6E6E6; 
                color: black; 
                padding: 4px; 
                border: 1px solid #b0b0b0; 
                font-weight: bold; font-size: 11px;
            }
            QTableWidget::item { padding: 2px; }
        """)
        
        # 컬럼 너비 조정 (내용에 맞게)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(0, 60)  # 판독번호
        header.resizeSection(1, 60)  # 용지코드
        header.resizeSection(6, 200) # 표기내용 (넓게)

    def add_row_data(self, data_list):
        """데이터 리스트를 받아서 한 행 추가"""
        row = self.rowCount()
        self.insertRow(row)
        for i, text in enumerate(data_list):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignCenter)
            self.setItem(row, i, item)

