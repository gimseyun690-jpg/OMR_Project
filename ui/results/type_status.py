from collections import defaultdict

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from database import DBManager


class TypeStatusView(QWidget):
    HEADERS = ["용지코드", "총매수", "정상", "오류", "오류율"]

    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.lbl_info = QLabel("유형별 현황: 0건")
        top.addWidget(self.lbl_info)
        top.addStretch(1)
        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self.load_data)
        top.addWidget(btn_refresh)
        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

    def set_db_path(self, path):
        self.current_db_path = path or None
        self.load_data()

    @staticmethod
    def _item(text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def load_data(self):
        if not self.current_db_path:
            self.table.setRowCount(0)
            self.lbl_info.setText("유형별 현황: DB 없음")
            return

        scans = self.db.get_all_scans(self.current_db_path) or []
        agg = defaultdict(lambda: {"total": 0, "error": 0})
        for row in scans:
            sheet_code = str(row[5] if len(row) > 5 else "").strip() or "Unknown"
            is_valid = int(row[7]) if len(row) > 7 else 0
            agg[sheet_code]["total"] += 1
            if is_valid == 0:
                agg[sheet_code]["error"] += 1

        rows = []
        for sheet_code, stat in sorted(agg.items(), key=lambda x: x[0]):
            total = int(stat["total"])
            error = int(stat["error"])
            normal = total - error
            err_rate = (float(error) / float(total) * 100.0) if total > 0 else 0.0
            rows.append((sheet_code, total, normal, error, f"{err_rate:.1f}%"))

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.table.setItem(r, c, self._item(value))
        self.lbl_info.setText(f"유형별 현황: {len(rows)}유형")
