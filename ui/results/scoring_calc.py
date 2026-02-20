from __future__ import annotations

from typing import Dict, Tuple

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
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


class ScoringCalcView(QWidget):
    HEADERS = ["수험번호", "이름", "정답수", "점수", "등급", "비고"]

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
        self.lbl_info = QLabel("채점 계산: 대기")
        top.addWidget(self.lbl_info)
        top.addSpacing(10)
        top.addWidget(QLabel("점수 방식"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("원점수", "raw")
        self.cmb_mode.addItem("100점 환산", "percent")
        top.addWidget(self.cmb_mode)
        top.addStretch(1)

        btn_run = QPushButton("채점 계산")
        btn_run.clicked.connect(self.run_scoring)
        btn_save = QPushButton("채점 결과 저장")
        btn_save.clicked.connect(self.save_current)
        top.addWidget(btn_run)
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
        self.table.setRowCount(0)
        if self.current_db_path:
            self.lbl_info.setText("채점 계산: 준비")
        else:
            self.lbl_info.setText("채점 계산: DB 없음")

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
    def _is_absent(attendance: str) -> bool:
        raw = str(attendance or "").strip().upper()
        return raw in ("결시", "미응시", "불참", "N", "NO", "0")

    @staticmethod
    def _grade_from_ratio(ratio: float) -> str:
        if ratio >= 0.90:
            return "A"
        if ratio >= 0.80:
            return "B"
        if ratio >= 0.70:
            return "C"
        if ratio >= 0.60:
            return "D"
        return "F"

    @staticmethod
    def _item(text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _load_answer_map(self):
        rows = self.db.load_answers(self.current_db_path) or []
        answer_map: Dict[int, str] = {}
        score_map: Dict[int, float] = {}
        for row in rows:
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

    def _load_latest_scan_by_exam(self):
        scans = self.db.get_all_scans(self.current_db_path) or []
        out = {}
        for row in scans:
            if len(row) <= 10:
                continue
            if int(row[7]) != 1:
                continue
            exam_no = str(row[10] or "").strip()
            if not exam_no:
                continue
            try:
                read_num = int(row[1])
            except Exception:
                read_num = 0
            prev = out.get(exam_no)
            if prev is None:
                out[exam_no] = row
                continue
            try:
                prev_read_num = int(prev[1])
            except Exception:
                prev_read_num = 0
            if read_num >= prev_read_num:
                out[exam_no] = row
        return out

    def run_scoring(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "안내", "먼저 DB를 선택해 주세요.")
            return

        answer_map, score_map = self._load_answer_map()
        if not answer_map:
            QMessageBox.warning(self, "안내", "정답 입력 데이터가 없습니다.")
            return
        total_possible = sum(float(score_map.get(q, 1.0)) for q in answer_map.keys())
        if total_possible <= 0:
            total_possible = float(len(answer_map))

        roster_rows = self.db.load_roster(self.current_db_path) or []
        if not roster_rows:
            QMessageBox.warning(self, "안내", "명단 데이터가 없습니다.")
            return
        scan_by_exam = self._load_latest_scan_by_exam()

        mode = self.cmb_mode.currentData() or "raw"
        rows_out = []
        for roster in roster_rows:
            exam_no = str(roster[0] if len(roster) > 0 else "").strip()
            name = str(roster[1] if len(roster) > 1 else "").strip()
            attendance = str(roster[6] if len(roster) > 6 else "").strip()

            correct_cnt = 0
            raw_score = 0.0
            note = ""

            if self._is_absent(attendance):
                note = "결시"
            else:
                scan = scan_by_exam.get(exam_no)
                if scan is None:
                    note = "판독데이터 없음"
                else:
                    mark_result = str(scan[6] if len(scan) > 6 else "")
                    for q_num, answer in answer_map.items():
                        idx = q_num - 1
                        char = mark_result[idx] if idx < len(mark_result) else "0"
                        kind, selected = self._decode_mark_char(char)
                        if kind == "single" and selected == answer:
                            correct_cnt += 1
                            raw_score += float(score_map.get(q_num, 1.0))

            ratio = float(raw_score) / float(total_possible) if total_possible > 0 else 0.0
            grade = self._grade_from_ratio(ratio) if note != "결시" else "결시"
            if mode == "percent":
                score_value = ratio * 100.0
            else:
                score_value = raw_score

            rows_out.append(
                (
                    exam_no,
                    name,
                    correct_cnt,
                    f"{score_value:.2f}",
                    grade,
                    note,
                )
            )

        self.table.setRowCount(len(rows_out))
        for r, row in enumerate(rows_out):
            for c, value in enumerate(row):
                self.table.setItem(r, c, self._item(value))
        self.lbl_info.setText(f"채점 계산: {len(rows_out)}명")

    def _collect_rows_for_save(self):
        rows = []
        for r in range(self.table.rowCount()):
            exam_no = self.table.item(r, 0).text().strip() if self.table.item(r, 0) else ""
            name = self.table.item(r, 1).text().strip() if self.table.item(r, 1) else ""
            try:
                correct_cnt = int(float(self.table.item(r, 2).text().strip())) if self.table.item(r, 2) else 0
            except Exception:
                correct_cnt = 0
            try:
                score = float(self.table.item(r, 3).text().strip()) if self.table.item(r, 3) else 0.0
            except Exception:
                score = 0.0
            grade = self.table.item(r, 4).text().strip() if self.table.item(r, 4) else ""
            note = self.table.item(r, 5).text().strip() if self.table.item(r, 5) else ""
            rows.append((exam_no, name, correct_cnt, score, grade, note))
        return rows

    def save_current(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "안내", "먼저 DB를 선택해 주세요.")
            return
        rows = self._collect_rows_for_save()
        if not rows:
            QMessageBox.warning(self, "안내", "먼저 채점 계산을 실행해 주세요.")
            return
        mode = self.cmb_mode.currentData() or "raw"
        try:
            self.db.save_score_results(self.current_db_path, rows, mode)
            QMessageBox.information(self, "완료", f"채점 결과 {len(rows)}건 저장 완료")
        except Exception as e:
            QMessageBox.warning(self, "저장 실패", str(e))
