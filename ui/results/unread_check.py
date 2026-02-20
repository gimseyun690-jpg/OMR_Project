from __future__ import annotations

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox,
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


class UnreadCheckView(QWidget):
    HEADERS = ["판독번호", "용지코드", "고사장", "시험실", "구분", "세부", "원본결과"]

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
        self.lbl_info = QLabel("미판독 확인: 0건")
        top.addWidget(self.lbl_info)
        top.addSpacing(10)

        self.chk_invalid = QCheckBox("오류")
        self.chk_invalid.setChecked(True)
        self.chk_dup = QCheckBox("중복")
        self.chk_dup.setChecked(True)
        self.chk_blank = QCheckBox("전부 공백")
        self.chk_blank.setChecked(True)
        self.chk_roster_missing = QCheckBox("명단 미등록")
        self.chk_roster_missing.setChecked(True)

        for chk in (self.chk_invalid, self.chk_dup, self.chk_blank, self.chk_roster_missing):
            chk.toggled.connect(self.load_data)
            top.addWidget(chk)

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

    def _set_rows(self, rows):
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, self._item(val))
        self.lbl_info.setText(f"미판독 확인: {len(rows)}건")

    def _build_issue(self, row, roster_set):
        read_num = row[1]
        scanner = row[2]
        room = row[3]
        sheet_code = row[5]
        mark_result = str(row[6] or "")
        mark_upper = mark_result.upper()
        is_valid = int(row[7]) if len(row) > 7 else 0
        exam_no = str(row[10] or "").strip() if len(row) > 10 else ""

        tags = []
        if self.chk_invalid.isChecked() and is_valid == 0:
            tags.append("오류")
        if self.chk_dup.isChecked() and ("X" in mark_upper):
            tags.append("중복")
        if self.chk_blank.isChecked() and mark_upper and mark_upper.replace("0", "") == "":
            tags.append("전부공백")
        if self.chk_roster_missing.isChecked():
            if exam_no and exam_no not in roster_set:
                tags.append("명단미등록")

        if not tags:
            return None
        return (
            read_num,
            sheet_code,
            scanner,
            room,
            ",".join(tags),
            f"수험번호:{exam_no}" if exam_no else "-",
            mark_result,
        )

    def load_data(self):
        if not self.current_db_path:
            self.table.setRowCount(0)
            self.lbl_info.setText("미판독 확인: DB 없음")
            return

        scans = self.db.get_all_scans(self.current_db_path) or []
        roster = self.db.load_roster(self.current_db_path) or []
        roster_set = {str(r[0]).strip() for r in roster if r and len(r) > 0 and str(r[0]).strip()}

        rows = []
        for row in scans:
            issue_row = self._build_issue(row, roster_set)
            if issue_row is not None:
                rows.append(issue_row)

        self._set_rows(rows)
