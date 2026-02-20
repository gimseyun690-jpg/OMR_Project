from __future__ import annotations

from PySide2.QtCore import Qt, QTimer
from PySide2.QtGui import QColor
from PySide2.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
        self.setObjectName("scanDataStatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        self.lbl_title = QLabel(str(title))
        self.lbl_title.setObjectName("scanDataStatTitle")
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("scanDataStatValue")
        self.lbl_value.setStyleSheet(f"color: {accent};")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("scanDataStatSub")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)
        layout.addStretch(1)

    def set_value(self, value: str, sub: str = ""):
        self.lbl_value.setText(str(value))
        self.lbl_sub.setText(str(sub or ""))


class ScanDataView(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self._current_q_count = 0
        self._last_scan_count = -1
        self._all_rows = []
        self._pending_rows = []
        self._render_cursor = 0
        self._chunk_size = 150

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_next_chunk)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._apply_filters_and_render)

        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("판독 자료")
        self.lbl_title.setObjectName("scanDataTitle")
        self.lbl_count = QLabel("전체 0건")
        self.lbl_count.setObjectName("scanDataCount")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_count)
        header.addLayout(title_col, 1)

        self.btn_refresh = PrimaryPushButton("새로고침")
        self.btn_refresh.clicked.connect(lambda: self.load_data(force=True))
        header.addWidget(self.btn_refresh, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addLayout(header)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.edt_search = QLineEdit()
        self.edt_search.setPlaceholderText("판독번호 / 용지코드 검색")
        self.edt_search.textChanged.connect(self._schedule_filter_apply)

        self.cmb_status = QComboBox()
        self.cmb_status.addItem("전체", "all")
        self.cmb_status.addItem("정상", "normal")
        self.cmb_status.addItem("중복", "dup")
        self.cmb_status.addItem("공백", "blank")
        self.cmb_status.currentIndexChanged.connect(self._schedule_filter_apply)

        filter_row.addWidget(self.edt_search, 1)
        filter_row.addWidget(self.cmb_status, 0)
        root.addLayout(filter_row)

        stat_row = QHBoxLayout()
        stat_row.setSpacing(8)
        self.card_total = StatCard("전체", "#2563EB")
        self.card_normal = StatCard("정상", "#16A34A")
        self.card_dup = StatCard("중복", "#DC2626")
        self.card_blank = StatCard("공백", "#475569")
        stat_row.addWidget(self.card_total)
        stat_row.addWidget(self.card_normal)
        stat_row.addWidget(self.card_dup)
        stat_row.addWidget(self.card_blank)
        root.addLayout(stat_row)

        self.table = QTableWidget()
        self.table.setObjectName("scanDataTable")
        self._set_headers(5)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table, 1)

        self.setStyleSheet(
            """
            #scanDataTitle { font-size: 22px; font-weight: 700; color: #0F172A; }
            #scanDataCount { font-size: 12px; color: #64748B; }
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
            #scanDataStatCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            #scanDataStatTitle { font-size: 11px; color: #64748B; }
            #scanDataStatValue { font-size: 24px; font-weight: 700; }
            #scanDataStatSub { font-size: 11px; color: #94A3B8; }
            #scanDataTable {
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
        path = path or None
        changed = path != self.current_db_path
        self.current_db_path = path

        if changed:
            self._last_scan_count = -1

        if not self.current_db_path:
            self._clear_view()
            return

        if not changed and self._is_scan_count_unchanged():
            return
        self.load_data(force=True)

    def _set_headers(self, q_count: int):
        count = max(1, int(q_count))
        headers = ["판독번호", "용지코드", "상태"] + [f"제{i}호" for i in range(1, count + 1)]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self._current_q_count = count

    @staticmethod
    def _decode_mark_char(char: str) -> str:
        text = str(char or "").strip()
        if not text:
            return ""
        if text.upper() == "X":
            return "중복"
        if text == "0":
            return ""
        return text

    @staticmethod
    def _classify_result(result_str: str) -> str:
        text = str(result_str or "").strip().upper()
        if not text or text.replace("0", "") == "":
            return "공백"
        if "X" in text:
            return "중복"
        return "정상"

    def _resolve_question_count(self, rows) -> int:
        max_len = 0
        for row in rows or []:
            try:
                result_str = str(row[2] or "")
            except Exception:
                result_str = ""
            if len(result_str) > max_len:
                max_len = len(result_str)

        setting_count = 0
        if self.current_db_path:
            raw = self.db.get_setting(self.current_db_path, "vote_count_q_count", "0")
            try:
                setting_count = max(0, int(raw))
            except Exception:
                setting_count = 0

        return max(1, max(max_len, setting_count))

    def _clear_view(self):
        self._cancel_render()
        self._all_rows = []
        self.table.setRowCount(0)
        self.lbl_count.setText("전체 0건")
        self.card_total.set_value("0")
        self.card_normal.set_value("0")
        self.card_dup.set_value("0")
        self.card_blank.set_value("0")

    def load_data(self, force=False):
        if not self.current_db_path:
            self._clear_view()
            return

        if not force and self._is_scan_count_unchanged():
            return

        rows = self.db.get_raw_data_for_grid(self.current_db_path) or []
        self._all_rows = rows
        q_count = self._resolve_question_count(rows)
        if q_count != self._current_q_count:
            self._set_headers(q_count)
        self._apply_filters_and_render()
        self._last_scan_count = len(rows)

    def _schedule_filter_apply(self):
        self._filter_timer.start(120)

    def _apply_filters_and_render(self):
        search_text = self.edt_search.text().strip().lower()
        status_key = str(self.cmb_status.currentData() or "all")

        total = len(self._all_rows)
        normal = 0
        dup = 0
        blank = 0
        filtered = []

        for row in self._all_rows:
            read_num = str(row[0] if len(row) > 0 else "")
            sheet_code = str(row[1] if len(row) > 1 else "")
            result_str = str(row[2] if len(row) > 2 else "")

            status = self._classify_result(result_str)
            if status == "정상":
                normal += 1
            elif status == "중복":
                dup += 1
            else:
                blank += 1

            if search_text and (search_text not in read_num.lower()) and (search_text not in sheet_code.lower()):
                continue
            if status_key == "normal" and status != "정상":
                continue
            if status_key == "dup" and status != "중복":
                continue
            if status_key == "blank" and status != "공백":
                continue

            filtered.append(row)

        self.card_total.set_value(f"{total:,}", "전체")
        self.card_normal.set_value(f"{normal:,}", "정상")
        self.card_dup.set_value(f"{dup:,}", "중복")
        self.card_blank.set_value(f"{blank:,}", "공백")
        self.lbl_count.setText(f"필터 결과 {len(filtered):,}건 / 전체 {total:,}건")
        self._start_incremental_render(filtered)

    def _is_scan_count_unchanged(self) -> bool:
        try:
            return self.db.get_scan_count(self.current_db_path) == self._last_scan_count
        except Exception:
            return False

    def _start_incremental_render(self, rows):
        self._cancel_render()
        self._pending_rows = list(rows)
        self._render_cursor = 0
        self.table.clearContents()
        self.table.setRowCount(len(self._pending_rows))
        if self._pending_rows:
            self._render_timer.start(0)

    def _cancel_render(self):
        if self._render_timer.isActive():
            self._render_timer.stop()
        self._pending_rows = []
        self._render_cursor = 0

    def _render_next_chunk(self):
        rows = self._pending_rows
        total = len(rows)
        if total == 0:
            return

        start = self._render_cursor
        end = min(start + self._chunk_size, total)
        self.table.setUpdatesEnabled(False)
        try:
            for r_idx in range(start, end):
                row = rows[r_idx]
                read_num = row[0]
                sheet_code = row[1]
                result_str = row[2] or ""
                status = self._classify_result(result_str)

                self.table.setItem(r_idx, 0, self._item(read_num))
                self.table.setItem(r_idx, 1, self._item(sheet_code))
                self.table.setItem(r_idx, 2, self._status_item(status))

                for c_idx, char in enumerate(result_str):
                    if c_idx >= self._current_q_count:
                        break
                    self.table.setItem(r_idx, 3 + c_idx, self._item(self._decode_mark_char(char)))

                for c_idx in range(len(result_str), self._current_q_count):
                    self.table.setItem(r_idx, 3 + c_idx, self._item(""))
        finally:
            self.table.setUpdatesEnabled(True)

        self._render_cursor = end
        if end < total:
            self._render_timer.start(0)

    def _item(self, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    @staticmethod
    def _status_item(status: str):
        item = QTableWidgetItem(str(status))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        if status == "정상":
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#DCFCE7"))
        elif status == "중복":
            item.setForeground(QColor("#991B1B"))
            item.setBackground(QColor("#FEE2E2"))
        else:
            item.setForeground(QColor("#334155"))
            item.setBackground(QColor("#E2E8F0"))
        return item
