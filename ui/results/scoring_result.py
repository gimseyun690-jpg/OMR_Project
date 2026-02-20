from __future__ import annotations

import csv

from PySide2.QtCore import Qt, QTimer
from PySide2.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from database import DBManager

try:
    from qfluentwidgets import PrimaryPushButton
except Exception:
    PrimaryPushButton = QPushButton


class StatCard(QFrame):
    def __init__(self, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.setObjectName("scoreStatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.lbl_title = QLabel(str(title))
        self.lbl_title.setObjectName("scoreStatTitle")
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("scoreStatValue")
        self.lbl_value.setStyleSheet(f"color: {accent};")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("scoreStatSub")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)
        layout.addStretch(1)

    def set_value(self, value: str, sub: str = ""):
        self.lbl_value.setText(str(value))
        self.lbl_sub.setText(str(sub or ""))


class ScoringResultView(QWidget):
    HEADERS = ["수험번호", "이름", "정답수", "점수", "등급", "비고", "채점모드", "생성시각"]

    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self._all_rows = []
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_filters)
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("채점 결과")
        self.lbl_title.setObjectName("scoreTitle")
        self.lbl_info = QLabel("채점 결과 0건")
        self.lbl_info.setObjectName("scoreCount")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_info)
        header.addLayout(title_col, 1)

        btn_refresh = QPushButton("새로고침")
        btn_refresh.clicked.connect(self.load_data)
        self.btn_export = PrimaryPushButton("CSV 내보내기")
        self.btn_export.clicked.connect(self.export_csv)
        header.addWidget(btn_refresh)
        header.addWidget(self.btn_export)
        root.addLayout(header)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("수험번호 / 이름 검색")
        self.edt_search.textChanged.connect(self._schedule_filter)

        self.cmb_grade = QComboBox()
        self.cmb_grade.addItem("전체 등급", "all")
        for grade in ("A", "B", "C", "D", "F", "결시"):
            self.cmb_grade.addItem(grade, grade)
        self.cmb_grade.currentIndexChanged.connect(self._schedule_filter)

        filter_row.addWidget(self.edt_search, 1)
        filter_row.addWidget(self.cmb_grade, 0)
        root.addLayout(filter_row)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(8)
        self.card_total = StatCard("대상 수", "#2563EB")
        self.card_avg = StatCard("평균 점수", "#16A34A")
        self.card_a = StatCard("A 등급", "#7C3AED")
        self.card_absent = StatCard("결시", "#EA580C")
        stat_row.addWidget(self.card_total)
        stat_row.addWidget(self.card_avg)
        stat_row.addWidget(self.card_a)
        stat_row.addWidget(self.card_absent)
        root.addLayout(stat_row)

        self.table = QTableWidget()
        self.table.setObjectName("scoreTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        self.setStyleSheet(
            """
            #scoreTitle { font-size: 22px; font-weight: 700; color: #0F172A; }
            #scoreCount { font-size: 12px; color: #64748B; }
            QLineEdit, QComboBox {
                min-height: 30px;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 4px 8px;
                background: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #3B82F6;
            }
            #scoreStatCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            #scoreStatTitle { font-size: 11px; color: #64748B; }
            #scoreStatValue { font-size: 24px; font-weight: 700; }
            #scoreStatSub { font-size: 11px; color: #94A3B8; }
            #scoreTable {
                gridline-color: #E2E8F0;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                border: none;
                border-bottom: 1px solid #E2E8F0;
                padding: 7px;
                font-weight: 600;
                color: #334155;
            }
            """
        )

    def set_db_path(self, path):
        self.current_db_path = path or None
        self.load_data()

    @staticmethod
    def _item(text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _schedule_filter(self):
        self._filter_timer.start(120)

    def _update_stats(self, rows):
        total = len(rows)
        a_count = 0
        absent_count = 0
        sum_score = 0.0
        scored_count = 0

        for row in rows:
            grade = str(row[4] if len(row) > 4 else "").strip().upper()
            note = str(row[5] if len(row) > 5 else "").strip()
            if grade == "A":
                a_count += 1
            if grade == "결시" or note == "결시":
                absent_count += 1
            try:
                score = float(row[3] if len(row) > 3 else 0.0)
            except Exception:
                score = 0.0
            if grade != "결시":
                sum_score += score
                scored_count += 1

        avg = (sum_score / float(scored_count)) if scored_count > 0 else 0.0
        self.card_total.set_value(f"{total:,}", "필터 결과")
        self.card_avg.set_value(f"{avg:.2f}", f"채점 대상 {scored_count:,}명")
        self.card_a.set_value(f"{a_count:,}", "A 등급")
        self.card_absent.set_value(f"{absent_count:,}", "결시")
        self.lbl_info.setText(f"채점 결과 {total:,}건")

    def _apply_filters(self):
        search_text = self.edt_search.text().strip().lower()
        grade_filter = str(self.cmb_grade.currentData() or "all")

        filtered = []
        for row in self._all_rows:
            exam_no = str(row[0] if len(row) > 0 else "")
            name = str(row[1] if len(row) > 1 else "")
            grade = str(row[4] if len(row) > 4 else "")

            if search_text and (search_text not in exam_no.lower()) and (search_text not in name.lower()):
                continue
            if grade_filter != "all" and grade != grade_filter:
                continue
            filtered.append(row)

        self.table.setRowCount(len(filtered))
        for r, row in enumerate(filtered):
            for c, value in enumerate(row[: len(self.HEADERS)]):
                self.table.setItem(r, c, self._item(value))
        self._update_stats(filtered)

    def load_data(self):
        if not self.current_db_path:
            self._all_rows = []
            self.table.setRowCount(0)
            self.lbl_info.setText("채점 결과 DB 없음")
            self._update_stats([])
            return
        try:
            self._all_rows = self.db.load_score_results(self.current_db_path) or []
        except Exception as e:
            QMessageBox.warning(self, "불러오기 실패", str(e))
            return
        self._apply_filters()

    def export_csv(self):
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "안내", "내보낼 결과가 없습니다.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "채점 결과 CSV 저장", "scoring_result.csv", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)
                for r in range(self.table.rowCount()):
                    row = []
                    for c in range(self.table.columnCount()):
                        item = self.table.item(r, c)
                        row.append(item.text() if item else "")
                    writer.writerow(row)
            QMessageBox.information(self, "완료", "CSV 저장 완료")
        except Exception as e:
            QMessageBox.warning(self, "CSV 저장 실패", str(e))
