from PySide2.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QAbstractItemView


class SessionSummaryWidget(QWidget):
    """좌측 요약 테이블 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["스캐너", "판독시험실", "판독매수"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setStyleSheet(
            "QHeaderView::section { background-color: #D1E8FF; border: 1px solid #999; font-weight: bold; font-size: 11px; }"
            "QTableWidget { gridline-color: #ccc; font-size: 11px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
