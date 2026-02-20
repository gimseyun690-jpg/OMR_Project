from __future__ import annotations

from PySide2.QtCore import QRunnable, QObject, Signal


class SummarySignals(QObject):
    result = Signal(list, int, int, int)
    error = Signal(str)


class SummaryTask(QRunnable):
    def __init__(self, db, db_path):
        super().__init__()
        self.db = db
        self.db_path = db_path
        self.signals = SummarySignals()

    def run(self):
        try:
            summary_rows = self.db.get_summary_by_scanner(self.db_path)
            total, normal, error = self.db.get_statistics(self.db_path)
            self.signals.result.emit(summary_rows, total, normal, error)
        except Exception as e:
            self.signals.error.emit(str(e))


class ReviewSummarySignals(QObject):
    result = Signal(int, int, int, int, int, int, int)
    error = Signal(str)


class ReviewSummaryTask(QRunnable):
    def __init__(self, db, db_path, start, end, profile=""):
        super().__init__()
        self.db = db
        self.db_path = db_path
        self.start = start
        self.end = end
        self.profile = str(profile or "").strip().lower()
        self.signals = ReviewSummarySignals()

    def run(self):
        try:
            rows = self.db.get_scans_in_range(self.db_path, self.start, self.end)
            roster_rows = self.db.load_roster(self.db_path)
        except Exception as e:
            self.signals.error.emit(str(e))
            return

        roster_by_exam = {str(r[0]).strip(): r for r in roster_rows if r and len(r) > 0}

        total_in_session = 0
        review_count = 0
        blank_cnt = 0
        dup_cnt = 0
        invalid_cnt = 0
        roster_missing_cnt = 0
        absent_cnt = 0

        for row in rows:
            read_num = row[0]
            total_in_session += 1

            mark_result = str(row[1] or "")
            normalized_result = mark_result.upper()
            is_valid = row[2]
            exam_no = str(row[3] or "").strip()

            needs_review = False
            if is_valid == 0:
                needs_review = True
                invalid_cnt += 1
            is_legacy_binary = set(normalized_result).issubset({"0", "1", "2", "3"})
            has_blank = "0" in normalized_result
            # Legacy "3=duplicate" is valid only for church/rebuild historical data.
            legacy_three_dup = (
                self.profile in ("church", "rebuild")
                and ("3" in normalized_result)
                and is_legacy_binary
            )
            has_dup = ("X" in normalized_result) or legacy_three_dup
            if has_blank or has_dup:
                needs_review = True
                if has_dup:
                    dup_cnt += 1
                if normalized_result.replace("0", "") == "":
                    blank_cnt += 1

            lookup_key = exam_no if exam_no else str(read_num)
            roster = roster_by_exam.get(lookup_key)
            if roster is None:
                needs_review = True
                roster_missing_cnt += 1
            else:
                attendance = str(roster[6]).strip() if len(roster) > 6 else ""
                if attendance and attendance in ("\ubbf8\uc751\uc2dc", "\uacb0\uc2dc", "\ubd88\ucc38", "N", "NO", "0"):
                    needs_review = True
                    absent_cnt += 1

            if needs_review:
                review_count += 1

        self.signals.result.emit(
            total_in_session,
            review_count,
            blank_cnt,
            dup_cnt,
            invalid_cnt,
            roster_missing_cnt,
            absent_cnt,
        )
