from __future__ import annotations

from typing import Dict, List, Tuple

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
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


class ItemAnalysisView(QWidget):
    HEADERS = ["문항", "정답", "정답률", "난이도", "변별도", "비고"]

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
        self.lbl_summary = QLabel("문항 분석: 대기")
        top.addWidget(self.lbl_summary)
        top.addStretch(1)

        btn_analyze = QPushButton("분석 실행")
        btn_analyze.clicked.connect(self.run_analysis)
        btn_load = QPushButton("저장결과 불러오기")
        btn_load.clicked.connect(self.load_saved)
        btn_save = QPushButton("현재결과 저장")
        btn_save.clicked.connect(self.save_current)

        top.addWidget(btn_analyze)
        top.addWidget(btn_load)
        top.addWidget(btn_save)
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
        self.load_saved()

    @staticmethod
    def _decode_mark_char(char: str) -> Tuple[str, str]:
        text = str(char or "").strip().upper()
        if not text or text == "0":
            return "blank", ""
        if text == "X":
            return "dup", ""
        if text.isdigit() and int(text) > 0:
            return "single", text
        return "blank", ""

    @staticmethod
    def _difficulty_label(rate: float) -> str:
        if rate >= 0.85:
            return "매우 쉬움"
        if rate >= 0.70:
            return "쉬움"
        if rate >= 0.40:
            return "보통"
        if rate >= 0.20:
            return "어려움"
        return "매우 어려움"

    @staticmethod
    def _discrimination_text(value: float | None) -> str:
        if value is None:
            return "-"
        return f"{value:.3f}"

    def _set_rows(self, rows: List[Tuple]):
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row[: len(self.HEADERS)]):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _build_answer_map(self) -> Tuple[Dict[int, str], Dict[int, float]]:
        answer_rows = self.db.load_answers(self.current_db_path) or []
        answer_map: Dict[int, str] = {}
        score_map: Dict[int, float] = {}
        for row in answer_rows:
            try:
                q_num = int(row[0])
            except Exception:
                continue
            answer = str(row[1] if len(row) > 1 else "").strip().upper()
            if not answer:
                continue
            try:
                score = float(row[2]) if len(row) > 2 else 1.0
            except Exception:
                score = 1.0
            answer_map[q_num] = answer
            score_map[q_num] = score
        return answer_map, score_map

    def run_analysis(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "안내", "먼저 DB를 선택해 주세요.")
            return

        answer_map, score_map = self._build_answer_map()
        if not answer_map:
            QMessageBox.warning(self, "안내", "정답 입력 데이터가 없습니다.")
            return

        scans = self.db.get_all_scans(self.current_db_path) or []
        valid_scans = [row for row in scans if len(row) > 7 and int(row[7]) == 1]
        if not valid_scans:
            QMessageBox.warning(self, "안내", "정상 판독 데이터가 없습니다.")
            return

        q_numbers = sorted(answer_map.keys())
        total_per_q = {q: len(valid_scans) for q in q_numbers}
        correct_per_q = {q: 0 for q in q_numbers}
        blank_per_q = {q: 0 for q in q_numbers}
        dup_per_q = {q: 0 for q in q_numbers}
        person_records = []

        for row in valid_scans:
            mark_result = str(row[6] if len(row) > 6 else "")
            total_score = 0.0
            correct_map = {}
            for q in q_numbers:
                idx = q - 1
                char = mark_result[idx] if idx < len(mark_result) else "0"
                kind, selected = self._decode_mark_char(char)
                is_correct = (kind == "single" and selected == answer_map[q])
                correct_map[q] = is_correct
                if is_correct:
                    total_score += float(score_map.get(q, 1.0))
                    correct_per_q[q] += 1
                elif kind == "blank":
                    blank_per_q[q] += 1
                elif kind == "dup":
                    dup_per_q[q] += 1
            person_records.append({"score": total_score, "correct": correct_map})

        n_person = len(person_records)
        group_size = max(1, int(round(float(n_person) * 0.27))) if n_person >= 10 else 0
        sorted_records = sorted(person_records, key=lambda x: float(x["score"]), reverse=True)

        rows_out = []
        for q in q_numbers:
            total = max(1, int(total_per_q[q]))
            correct = int(correct_per_q[q])
            rate = float(correct) / float(total)
            difficulty = self._difficulty_label(rate)

            discrimination = None
            if group_size > 0 and len(sorted_records) >= group_size * 2:
                top = sorted_records[:group_size]
                bottom = sorted_records[-group_size:]
                top_rate = sum(1 for rec in top if rec["correct"].get(q)) / float(group_size)
                bottom_rate = sum(1 for rec in bottom if rec["correct"].get(q)) / float(group_size)
                discrimination = float(top_rate - bottom_rate)

            note = (
                f"응시:{total} 공백:{blank_per_q[q]} "
                f"중복:{dup_per_q[q]}"
            )
            rows_out.append(
                (
                    q,
                    answer_map[q],
                    f"{rate * 100.0:.1f}%",
                    difficulty,
                    self._discrimination_text(discrimination),
                    note,
                )
            )

        self._set_rows(rows_out)
        self.lbl_summary.setText(f"문항 분석: {len(rows_out)}문항, 응시 {len(valid_scans)}건")

    def save_current(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "안내", "먼저 DB를 선택해 주세요.")
            return
        rows = []
        for r in range(self.table.rowCount()):
            values = []
            for c in range(len(self.HEADERS)):
                item = self.table.item(r, c)
                values.append(item.text().strip() if item else "")
            if not values or not values[0]:
                continue
            try:
                q_num = int(values[0])
            except Exception:
                continue
            rows.append((q_num, values[1], values[2], values[3], values[4], values[5]))

        try:
            self.db.save_item_analysis(self.current_db_path, rows)
            QMessageBox.information(self, "완료", f"문항 분석 {len(rows)}건 저장 완료")
        except Exception as e:
            QMessageBox.warning(self, "저장 실패", str(e))

    def load_saved(self):
        if not self.current_db_path:
            self.table.setRowCount(0)
            self.lbl_summary.setText("문항 분석: DB 없음")
            return
        try:
            rows = self.db.load_item_analysis(self.current_db_path) or []
        except Exception as e:
            QMessageBox.warning(self, "불러오기 실패", str(e))
            return
        self._set_rows(rows)
        self.lbl_summary.setText(f"문항 분석: 저장결과 {len(rows)}건")
