from __future__ import annotations

import csv

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
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
        self.setObjectName("rosterStatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.lbl_title = QLabel(str(title))
        self.lbl_title.setObjectName("rosterStatTitle")
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("rosterStatValue")
        self.lbl_value.setStyleSheet(f"color: {accent};")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("rosterStatSub")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)
        layout.addStretch(1)

    def set_value(self, value: str, sub: str = ""):
        self.lbl_value.setText(str(value))
        self.lbl_sub.setText(str(sub or ""))


class RosterInputView(QWidget):
    HEADERS = ["수험번호", "이름", "생년월일", "과목", "학교", "고사장", "결시여부"]

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
        self.lbl_title = QLabel("명단 입력")
        self.lbl_title.setObjectName("rosterTitle")
        self.lbl_info = QLabel("명단 0건")
        self.lbl_info.setObjectName("rosterCount")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_info)
        header.addLayout(title_col, 1)

        btn_load = QPushButton("DB 불러오기")
        btn_load.clicked.connect(self.load_data)
        self.btn_save = PrimaryPushButton("DB 저장")
        self.btn_save.clicked.connect(self.save_data)
        header.addWidget(btn_load)
        header.addWidget(self.btn_save)
        root.addLayout(header)

        action = QHBoxLayout()
        action.setSpacing(8)
        btn_import = QPushButton("CSV 불러오기")
        btn_import.clicked.connect(self.import_csv)
        btn_export = QPushButton("CSV 내보내기")
        btn_export.clicked.connect(self.export_csv)
        btn_add = QPushButton("행 추가")
        btn_add.clicked.connect(self.add_row)
        btn_remove = QPushButton("행 삭제")
        btn_remove.clicked.connect(self.remove_selected_rows)
        self.chk_block_on_mismatch = QCheckBox("불일치 시 저장 차단 (ON/OFF)")
        self.chk_block_on_mismatch.setChecked(True)
        self.chk_block_on_mismatch.setToolTip(
            "ON: 수험번호/이름 누락, 중복 수험번호, 판독 수험번호 미매칭이 있으면 저장을 막습니다."
        )
        for btn in (btn_import, btn_export, btn_add, btn_remove):
            action.addWidget(btn)
        action.addWidget(self.chk_block_on_mismatch)
        action.addStretch(1)
        root.addLayout(action)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(8)
        self.card_rows = StatCard("총 행 수", "#2563EB")
        self.card_exam_no = StatCard("수험번호 입력", "#16A34A")
        self.card_absent = StatCard("결시 표시", "#EA580C")
        stat_row.addWidget(self.card_rows)
        stat_row.addWidget(self.card_exam_no)
        stat_row.addWidget(self.card_absent)
        root.addLayout(stat_row)

        self.table = QTableWidget()
        self.table.setObjectName("rosterTable")
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(lambda _item: self._refresh_metrics())
        root.addWidget(self.table, 1)

        self.setStyleSheet(
            """
            #rosterTitle { font-size: 22px; font-weight: 700; color: #0F172A; }
            #rosterCount { font-size: 12px; color: #64748B; }
            #rosterStatCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            #rosterStatTitle { font-size: 11px; color: #64748B; }
            #rosterStatValue { font-size: 24px; font-weight: 700; }
            #rosterStatSub { font-size: 11px; color: #94A3B8; }
            #rosterTable {
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

    def _refresh_metrics(self):
        rows = self.table.rowCount()
        exam_no_filled = 0
        absent_filled = 0

        for r in range(rows):
            exam_item = self.table.item(r, 0)
            absent_item = self.table.item(r, 6)
            exam_no = exam_item.text().strip() if exam_item else ""
            absent = absent_item.text().strip() if absent_item else ""
            if exam_no:
                exam_no_filled += 1
            if absent:
                normalized = absent.upper()
                if normalized in ("결시", "미응시", "불참", "N", "NO", "0"):
                    absent_filled += 1

        self.lbl_info.setText(f"명단 {rows:,}행")
        self.card_rows.set_value(f"{rows:,}", "현재 편집 행")
        self.card_exam_no.set_value(f"{exam_no_filled:,}", "수험번호 입력됨")
        self.card_absent.set_value(f"{absent_filled:,}", "결시 표시")

    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for c in range(len(self.HEADERS)):
            item = QTableWidgetItem("")
            item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, c, item)
        self._refresh_metrics()

    def remove_selected_rows(self):
        selected = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in selected:
            self.table.removeRow(row)
        self._refresh_metrics()

    def _set_table_rows(self, rows):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row_data in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col in range(len(self.HEADERS)):
                value = row_data[col] if col < len(row_data) else ""
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self._refresh_metrics()

    def _collect_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            values = []
            has_any = False
            for c in range(len(self.HEADERS)):
                item = self.table.item(r, c)
                text = item.text().strip() if item else ""
                if text:
                    has_any = True
                values.append(text)
            if has_any:
                rows.append(tuple(values))
        return rows

    @staticmethod
    def _sort_key_exam_no(text: str):
        raw = str(text or "").strip()
        if raw.isdigit():
            return (0, int(raw))
        return (1, raw)

    def _validate_rows_before_save(self, rows):
        issues = []
        exam_no_row = {}
        roster_exam_no = set()

        for idx, row in enumerate(rows, start=1):
            exam_no = str(row[0] if len(row) > 0 else "").strip()
            name = str(row[1] if len(row) > 1 else "").strip()

            if not exam_no:
                issues.append(f"{idx}행: 수험번호 누락")
            else:
                if exam_no in exam_no_row:
                    issues.append(f"{idx}행: 수험번호 중복 ({exam_no})")
                else:
                    exam_no_row[exam_no] = idx
                roster_exam_no.add(exam_no)

            if not name:
                issues.append(f"{idx}행: 이름 누락")

        # 판독데이터가 있으면, 판독 수험번호가 명단에 모두 존재해야 한다.
        if self.current_db_path:
            try:
                scan_rows = self.db.get_all_scans(self.current_db_path) or []
            except Exception:
                scan_rows = []

            scan_exam_no = set()
            for row in scan_rows:
                exam_no = ""
                if len(row) > 10:
                    exam_no = str(row[10] or "").strip()
                if exam_no:
                    scan_exam_no.add(exam_no)

            missing = sorted(scan_exam_no - roster_exam_no, key=self._sort_key_exam_no)
            if missing:
                preview = ", ".join(missing[:20])
                if len(missing) > 20:
                    preview += ", ..."
                issues.append(
                    f"판독 수험번호 {len(missing)}건이 명단에 없음: {preview}"
                )

        return issues

    def load_data(self):
        if not self.current_db_path:
            self.table.setRowCount(0)
            self.lbl_info.setText("명단 DB 없음")
            self._refresh_metrics()
            return
        try:
            rows = self.db.load_roster(self.current_db_path) or []
        except Exception as e:
            QMessageBox.warning(self, "불러오기 실패", str(e))
            return
        self._set_table_rows(rows)

    def save_data(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "안내", "먼저 DB를 선택해 주세요.")
            return
        rows = self._collect_rows()
        if self.chk_block_on_mismatch.isChecked():
            issues = self._validate_rows_before_save(rows)
            if issues:
                preview = "\n".join(issues[:20])
                if len(issues) > 20:
                    preview += "\n... (이하 생략)"
                QMessageBox.warning(
                    self,
                    "저장 차단",
                    "명단 불일치가 있어 저장할 수 없습니다.\n\n" + preview,
                )
                return
        try:
            self.db.save_roster(self.current_db_path, rows)
            QMessageBox.information(self, "완료", f"명단 {len(rows)}건 저장 완료")
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
        file_path, _ = QFileDialog.getOpenFileName(self, "명단 CSV 불러오기", "", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            rows = self._read_csv_rows(file_path)
            if not rows:
                self._set_table_rows([])
                return

            data_rows = rows
            header_tokens = {h.strip().lower() for h in rows[0]}
            if {"수험번호", "이름"} & header_tokens:
                data_rows = rows[1:]

            normalized = []
            for raw in data_rows:
                values = list(raw[: len(self.HEADERS)])
                while len(values) < len(self.HEADERS):
                    values.append("")
                normalized.append(tuple(values))

            self._set_table_rows(normalized)
        except Exception as e:
            QMessageBox.warning(self, "CSV 불러오기 실패", str(e))

    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "명단 CSV 내보내기", "roster.csv", "CSV Files (*.csv)")
        if not file_path:
            return
        try:
            rows = self._collect_rows()
            with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)
                for row in rows:
                    writer.writerow(row)
            QMessageBox.information(self, "완료", f"CSV 저장 완료 ({len(rows)}건)")
        except Exception as e:
            QMessageBox.warning(self, "CSV 저장 실패", str(e))
