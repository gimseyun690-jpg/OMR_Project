from __future__ import annotations

import csv

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
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
        self.setObjectName("answerStatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.lbl_title = QLabel(str(title))
        self.lbl_title.setObjectName("answerStatTitle")
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("answerStatValue")
        self.lbl_value.setStyleSheet(f"color: {accent};")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("answerStatSub")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)
        layout.addStretch(1)

    def set_value(self, value: str, sub: str = ""):
        self.lbl_value.setText(str(value))
        self.lbl_sub.setText(str(sub or ""))


class AnswerInputView(QWidget):
    HEADERS = ["문항", "정답", "배점"]

    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("정답 입력")
        self.lbl_title.setObjectName("answerTitle")
        self.lbl_info = QLabel("정답 0문항")
        self.lbl_info.setObjectName("answerCount")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_info)
        header.addLayout(title_col, 1)

        header.addWidget(QLabel("문항수"))
        self.spin_q_count = QSpinBox()
        self.spin_q_count.setRange(1, 500)
        self.spin_q_count.setValue(50)
        header.addWidget(self.spin_q_count)

        btn_generate = QPushButton("행 생성")
        btn_generate.clicked.connect(self.generate_rows)
        header.addWidget(btn_generate)
        self.btn_save = PrimaryPushButton("DB 저장")
        self.btn_save.clicked.connect(self.save_data)
        header.addWidget(self.btn_save)
        root.addLayout(header)

        action = QHBoxLayout()
        action.setSpacing(8)
        btn_load = QPushButton("DB 불러오기")
        btn_load.clicked.connect(self.load_data)
        btn_import = QPushButton("CSV 불러오기")
        btn_import.clicked.connect(self.import_csv)
        btn_export = QPushButton("CSV 내보내기")
        btn_export.clicked.connect(self.export_csv)
        for btn in (btn_load, btn_import, btn_export):
            action.addWidget(btn)
        action.addStretch(1)
        root.addLayout(action)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(8)
        self.card_total = StatCard("문항 수", "#2563EB")
        self.card_answered = StatCard("정답 입력", "#16A34A")
        self.card_score = StatCard("총 배점", "#EA580C")
        stat_row.addWidget(self.card_total)
        stat_row.addWidget(self.card_answered)
        stat_row.addWidget(self.card_score)
        root.addLayout(stat_row)

        self.table = QTableWidget()
        self.table.setObjectName("answerTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(lambda _item: self._refresh_metrics())
        root.addWidget(self.table, 1)

        self.setStyleSheet(
            """
            #answerTitle { font-size: 22px; font-weight: 700; color: #0F172A; }
            #answerCount { font-size: 12px; color: #64748B; }
            QSpinBox {
                min-height: 30px;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 4px 6px;
                background: #FFFFFF;
            }
            #answerStatCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            #answerStatTitle { font-size: 11px; color: #64748B; }
            #answerStatValue { font-size: 24px; font-weight: 700; }
            #answerStatSub { font-size: 11px; color: #94A3B8; }
            #answerTable {
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

    def _set_q_item(self, row: int, q_num: int):
        item = QTableWidgetItem(str(int(q_num)))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, item)

    def _refresh_metrics(self):
        rows = self.table.rowCount()
        answered = 0
        total_score = 0.0

        for r in range(rows):
            ans = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            score_raw = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else "0"
            if ans:
                answered += 1
                try:
                    total_score += float(score_raw)
                except Exception:
                    pass

        self.lbl_info.setText(f"정답 {rows:,}문항")
        self.card_total.set_value(f"{rows:,}", "행 기준")
        self.card_answered.set_value(f"{answered:,}", "정답 입력됨")
        self.card_score.set_value(f"{total_score:.1f}", "입력 정답 합산")

    def _capture_existing(self):
        data = {}
        for r in range(self.table.rowCount()):
            q_item = self.table.item(r, 0)
            if not q_item:
                continue
            try:
                q_num = int(q_item.text().strip())
            except Exception:
                continue
            ans = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            score = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else ""
            data[q_num] = (ans, score)
        return data

    def generate_rows(self):
        count = int(self.spin_q_count.value())
        previous = self._capture_existing()
        self.table.blockSignals(True)
        self.table.setRowCount(count)
        for i in range(count):
            q_num = i + 1
            self._set_q_item(i, q_num)
            prev = previous.get(q_num, ("", "1"))
            ans_item = QTableWidgetItem(str(prev[0]))
            ans_item.setTextAlignment(Qt.AlignCenter)
            score_item = QTableWidgetItem(str(prev[1] if prev[1] else "1"))
            score_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, ans_item)
            self.table.setItem(i, 2, score_item)
        self.table.blockSignals(False)
        self._refresh_metrics()

    def _fill_from_rows(self, rows):
        max_q = 0
        for row in rows:
            try:
                max_q = max(max_q, int(row[0]))
            except Exception:
                continue
        max_q = max(1, max_q)
        self.spin_q_count.setValue(max_q)

        self.table.blockSignals(True)
        self.table.setRowCount(max_q)
        for i in range(max_q):
            self._set_q_item(i, i + 1)
            ans_item = QTableWidgetItem("")
            score_item = QTableWidgetItem("1")
            ans_item.setTextAlignment(Qt.AlignCenter)
            score_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, ans_item)
            self.table.setItem(i, 2, score_item)

        for row in rows:
            try:
                q_num = int(row[0])
            except Exception:
                continue
            if q_num <= 0 or q_num > max_q:
                continue
            idx = q_num - 1
            ans = str(row[1] if len(row) > 1 else "").strip()
            score = str(row[2] if len(row) > 2 else "1").strip()
            self.table.item(idx, 1).setText(ans)
            self.table.item(idx, 2).setText(score if score else "1")
        self.table.blockSignals(False)
        self._refresh_metrics()

    def load_data(self):
        if not self.current_db_path:
            self.table.setRowCount(0)
            self.lbl_info.setText("정답 DB 없음")
            self._refresh_metrics()
            return
        try:
            rows = self.db.load_answers(self.current_db_path) or []
            if rows:
                self._fill_from_rows(rows)
                return
            q_count = 50
            raw = self.db.get_setting(self.current_db_path, "vote_count_q_count", "50")
            try:
                q_count = max(1, int(raw))
            except Exception:
                q_count = 50
            self.spin_q_count.setValue(q_count)
            self.generate_rows()
        except Exception as e:
            QMessageBox.warning(self, "불러오기 실패", str(e))

    def _collect_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            q_item = self.table.item(r, 0)
            if not q_item:
                continue
            try:
                q_num = int(q_item.text().strip())
            except Exception:
                continue
            ans = self.table.item(r, 1).text().strip().upper() if self.table.item(r, 1) else ""
            score_raw = self.table.item(r, 2).text().strip() if self.table.item(r, 2) else "1"
            if not ans:
                continue
            try:
                score_val = float(score_raw)
            except Exception:
                score_val = 1.0
            rows.append((q_num, ans, score_val))
        return rows

    def save_data(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "안내", "먼저 DB를 선택해 주세요.")
            return
        rows = self._collect_rows()
        try:
            self.db.save_answers(self.current_db_path, rows)
            QMessageBox.information(self, "완료", f"정답 {len(rows)}문항 저장 완료")
        except Exception as e:
            QMessageBox.warning(self, "저장 실패", str(e))

    @staticmethod
    def _read_csv_rows(path):
        last_error = None
        for enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8"):
            try:
                with open(path, "r", encoding=enc, newline="") as f:
                    return list(csv.reader(f))
            except Exception as e:
                last_error = e
        if last_error:
            raise last_error
        return []

    def import_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "정답 CSV 불러오기", "", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            raw_rows = self._read_csv_rows(file_path)
            if not raw_rows:
                return
            rows = raw_rows
            first = [c.strip().lower() for c in rows[0]]
            if ("문항" in first) or ("q_num" in first):
                rows = rows[1:]

            parsed = []
            for raw in rows:
                if not raw:
                    continue
                try:
                    q_num = int(str(raw[0]).strip())
                except Exception:
                    continue
                ans = str(raw[1]).strip().upper() if len(raw) > 1 else ""
                score = str(raw[2]).strip() if len(raw) > 2 else "1"
                parsed.append((q_num, ans, score))
            self._fill_from_rows(parsed)
        except Exception as e:
            QMessageBox.warning(self, "CSV 불러오기 실패", str(e))

    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "정답 CSV 내보내기", "answers.csv", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            rows = self._collect_rows()
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)
                for row in rows:
                    writer.writerow(row)
            QMessageBox.information(self, "완료", f"CSV 저장 완료 ({len(rows)}문항)")
        except Exception as e:
            QMessageBox.warning(self, "CSV 저장 실패", str(e))
