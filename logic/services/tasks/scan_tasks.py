from __future__ import annotations

import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from typing import Any

from PySide2.QtCore import QObject, QRunnable, QThread, Signal


class ScanWorker(QThread):
    image_scanned = Signal(str)
    scan_finished = Signal()
    error_occurred = Signal(str)

    def __init__(self, hwnd, save_folder, dpi=150):
        super().__init__()
        from logic.scanner_core import ScannerDevice

        self.hwnd = hwnd
        self.save_folder = save_folder
        self.scanner = ScannerDevice()
        self.scanner.set_dpi(dpi)
        self.is_running = True

    def run(self):
        try:
            success, msg = self.scanner.connect(self.hwnd)
            if not success:
                self.error_occurred.emit(f"SCAN_ERR|CONNECT|1|0|스캐너 연결 실패: {msg}")
                return

            success, msg = self.scanner.open_scanner()
            if not success:
                self.error_occurred.emit(f"SCAN_ERR|OPEN|1|0|스캐너 열기 실패: {msg}")
                return

            if not self.scanner.check_paper():
                self.error_occurred.emit("SCAN_ERR|NO_PAPER|0|0|급지대에 용지가 없습니다.")
                return

            for image_path in self.scanner.scan(self.save_folder):
                if not self.is_running:
                    break
                self.image_scanned.emit(image_path)

            self.scan_finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.scanner.close()

    def stop(self):
        self.is_running = False


class DemoWorker(QThread):
    progress = Signal(int, int, str)
    result_row = Signal(list)
    result_rows = Signal(list)
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(
        self,
        controller,
        files,
        place,
        room,
        start_read_num,
        ui_update_interval_sec: float = 0.05,
        result_emit_interval_sec: float = 0.05,
        result_ui_batch_size: int = 20,
        db_batch_size: int = 100,
        submit_window_factor: int = 4,
        max_workers: int | None = None,
    ):
        super().__init__()
        self.controller = controller
        self.files = list(files)
        self.place = place
        self.room = room
        self.start_read_num = int(start_read_num)

        self.ui_update_interval_sec = max(0.01, float(ui_update_interval_sec))
        self.result_emit_interval_sec = max(0.01, float(result_emit_interval_sec))
        self.result_ui_batch_size = max(1, int(result_ui_batch_size))
        self.db_batch_size = max(1, int(db_batch_size))
        self.submit_window_factor = max(1, int(submit_window_factor))
        cpu_total = max(1, (os.cpu_count() or 1))
        self.max_workers = max(1, int(max_workers)) if max_workers is not None else max(1, cpu_total // 2)

        self._cancel = False
        self._last_progress_value = -1
        self._last_progress_emit_ts = 0.0
        self._last_result_emit_ts = 0.0
        self._pending_result_rows = []
        self._thread_local = threading.local()
        self._pipeline_snapshot = self._capture_pipeline_snapshot(getattr(self.controller, "pipeline", None))

        self.first_error = ""
        self.error_samples = []

    def cancel(self):
        self._cancel = True

    @staticmethod
    def _capture_pipeline_snapshot(pipeline) -> dict[str, Any]:
        if pipeline is None:
            return {}

        engine = getattr(pipeline, "engine", None)
        engine_config = {}
        if engine is not None:
            engine_config = {
                "block_size": int(getattr(engine, "block_size", 15)),
                "pixel_ratio": float(getattr(engine, "pixel_threshold", 0.05)),
                "marker_thresh": int(getattr(engine, "marker_thresh", 120)),
                "C": int(getattr(engine, "C", 7)),
                "global_offset_x": int(getattr(engine, "global_offset_x", 0)),
                "global_offset_y": int(getattr(engine, "global_offset_y", 0)),
                "exam_no_offset_x": int(getattr(engine, "exam_no_offset_x", 0)),
                "exam_no_offset_y": int(getattr(engine, "exam_no_offset_y", 0)),
                "birth_offset_x": int(getattr(engine, "birth_offset_x", 0)),
                "birth_offset_y": int(getattr(engine, "birth_offset_y", 0)),
                "name_offset_x": int(getattr(engine, "name_offset_x", 0)),
                "name_offset_y": int(getattr(engine, "name_offset_y", 0)),
                "subject_offset_x": int(getattr(engine, "subject_offset_x", 0)),
                "subject_offset_y": int(getattr(engine, "subject_offset_y", 0)),
                "question_offset_x": int(getattr(engine, "question_offset_x", 0)),
                "question_offset_y": int(getattr(engine, "question_offset_y", 0)),
                "exam_no_offset": float(getattr(engine, "exam_no_offset", 0.0)),
                "birth_offset": float(getattr(engine, "birth_offset", 0.0)),
                "name_offset": float(getattr(engine, "name_offset", 0.0)),
                "subject_offset": float(getattr(engine, "subject_offset", 0.0)),
                "questions_offset": float(getattr(engine, "questions_offset", 0.0)),
                "marker_detection": dict(getattr(engine, "marker_detection", {}) or {}),
            }

        dpi = getattr(pipeline, "dpi", getattr(pipeline, "system_dpi", 150))
        try:
            dpi = int(dpi)
        except Exception:
            dpi = 150

        return {
            "db_path": getattr(pipeline, "current_db_path", None),
            "form_path": getattr(pipeline, "form_path", None),
            "debug_save_on_error": bool(getattr(pipeline, "debug_save_on_error", False)),
            "debug_dir": getattr(pipeline, "debug_dir", None),
            "candidate_enabled": bool(getattr(pipeline, "candidate_enabled", False)),
            "auto_scale_dpi": bool(getattr(pipeline, "auto_scale_dpi", True)),
            "warp_enabled": bool(getattr(pipeline, "warp_enabled", True)),
            "dpi": dpi,
            "engine_config": engine_config,
        }

    def _build_worker_pipeline(self):
        from logic.pipeline import ScanPipeline

        pipe = ScanPipeline()
        snap = self._pipeline_snapshot

        db_path = snap.get("db_path")
        if db_path:
            pipe.set_project(db_path)

        pipe.set_debug_options(
            save_on_error=bool(snap.get("debug_save_on_error", False)),
            debug_dir=snap.get("debug_dir"),
        )
        pipe.set_candidate_enabled(bool(snap.get("candidate_enabled", False)))
        pipe.set_dpi(int(snap.get("dpi", 150)))
        pipe.set_auto_scale_dpi(bool(snap.get("auto_scale_dpi", True)))
        pipe.warp_enabled = bool(snap.get("warp_enabled", True))

        form_path = snap.get("form_path")
        if form_path:
            pipe.set_form_path(form_path)

        engine_config = snap.get("engine_config", {})
        if engine_config:
            pipe.engine.configure(**engine_config)

        return pipe

    def _get_worker_pipeline(self):
        pipe = getattr(self._thread_local, "pipeline", None)
        if pipe is None:
            pipe = self._build_worker_pipeline()
            self._thread_local.pipeline = pipe
        return pipe

    def _analyze_one(self, idx: int, image_path: str, read_num: int) -> dict[str, Any]:
        try:
            pipe = self._get_worker_pipeline()
            row_data, save_data = pipe.analyze_image(
                image_path=image_path,
                read_num=read_num,
                place=self.place,
                room=self.room,
            )
            return {
                "ok": True,
                "idx": idx,
                "path": image_path,
                "read_num": read_num,
                "row_data": row_data,
                "save_data": save_data,
            }
        except Exception as e:
            return {
                "ok": False,
                "idx": idx,
                "path": image_path,
                "read_num": read_num,
                "error": str(e),
            }

    @staticmethod
    def _ensure_scan_columns(conn):
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(tblScanData)")
        rows = cur.fetchall()
        cols = {row[1] for row in rows}
        if not cols:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS tblScanData (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    read_num INTEGER,
                    scanner_name TEXT,
                    room_no TEXT,
                    image_path TEXT,
                    sheet_code TEXT,
                    mark_result TEXT,
                    is_valid INTEGER DEFAULT 1,
                    scan_time TEXT,
                    error_message TEXT,
                    exam_no TEXT,
                    birth TEXT,
                    subject TEXT,
                    review_done INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_scan_readnum
                    ON tblScanData(read_num);
                CREATE INDEX IF NOT EXISTS idx_scan_place_room
                    ON tblScanData(scanner_name, room_no);
                CREATE INDEX IF NOT EXISTS idx_scan_is_valid
                    ON tblScanData(is_valid);
                """
            )
            conn.commit()
            cur.execute("PRAGMA table_info(tblScanData)")
            rows = cur.fetchall()
            cols = {row[1] for row in rows}

        for name, col_type in (
            ("error_message", "TEXT"),
            ("exam_no", "TEXT"),
            ("birth", "TEXT"),
            ("subject", "TEXT"),
            ("review_done", "INTEGER"),
        ):
            if name not in cols:
                cur.execute(f"ALTER TABLE tblScanData ADD COLUMN {name} {col_type}")
        conn.commit()

    @staticmethod
    def _to_insert_row(save_data: dict[str, Any]):
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            save_data.get("read_num"),
            save_data.get("place"),
            save_data.get("room"),
            save_data.get("path"),
            save_data.get("sheet_code"),
            save_data.get("mark_result"),
            save_data.get("is_valid", 1),
            scan_time,
            save_data.get("error_message"),
            save_data.get("exam_no"),
            save_data.get("birth"),
            save_data.get("subject"),
            save_data.get("review_done", 0),
        )

    @staticmethod
    def _flush_batch(conn, batch_rows):
        if not batch_rows:
            return
        cur = conn.cursor()
        cur.executemany(
            """
            INSERT INTO tblScanData
            (read_num, scanner_name, room_no, image_path, sheet_code, mark_result, is_valid, scan_time, error_message, exam_no, birth, subject, review_done)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            batch_rows,
        )
        conn.commit()
        batch_rows.clear()

    def _emit_progress(self, current: int, total: int, filename: str, force: bool = False):
        now = time.monotonic()
        if not force and (now - self._last_progress_emit_ts) < self.ui_update_interval_sec:
            return
        if current == self._last_progress_value and not force:
            return
        self._last_progress_value = current
        self._last_progress_emit_ts = now
        self.progress.emit(current, total, filename)

    def _emit_result_rows(self, force: bool = False):
        if not self._pending_result_rows:
            return
        now = time.monotonic()
        if not force:
            is_time_due = (now - self._last_result_emit_ts) >= self.result_emit_interval_sec
            is_batch_due = len(self._pending_result_rows) >= self.result_ui_batch_size
            if not (is_time_due or is_batch_due):
                return
        rows = self._pending_result_rows[:]
        self._pending_result_rows.clear()
        self._last_result_emit_ts = now
        self.result_rows.emit(rows)

    def run(self):
        ok = 0
        fail = 0
        total = len(self.files)
        processed = 0
        next_submit_idx = 1
        submit_window = max(self.max_workers, self.max_workers * self.submit_window_factor)
        db_batch_rows = []
        db_conn = None
        last_filename = ""

        try:
            db_path = self._pipeline_snapshot.get("db_path")
            if db_path:
                db_conn = self.controller.db.connect(db_path)
                self._ensure_scan_columns(db_conn)

            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                pending = {}

                while next_submit_idx <= total and len(pending) < submit_window and not self._cancel:
                    path = self.files[next_submit_idx - 1]
                    read_num = self.start_read_num + next_submit_idx
                    future = executor.submit(self._analyze_one, next_submit_idx, path, read_num)
                    pending[future] = (next_submit_idx, path)
                    next_submit_idx += 1

                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)

                    for future in done:
                        idx, path = pending.pop(future)
                        last_filename = os.path.basename(path)

                        if future.cancelled():
                            continue

                        try:
                            result = future.result()
                        except Exception as e:
                            result = {
                                "ok": False,
                                "idx": idx,
                                "path": path,
                                "error": str(e),
                            }

                        processed += 1

                        if result.get("ok"):
                            row_data = result.get("row_data")
                            if row_data:
                                self._pending_result_rows.append(row_data)
                                self._emit_result_rows(force=False)

                            save_data = result.get("save_data")
                            if db_conn is not None and save_data:
                                db_batch_rows.append(self._to_insert_row(save_data))
                                if len(db_batch_rows) >= self.db_batch_size:
                                    self._flush_batch(db_conn, db_batch_rows)

                            ok += 1
                        else:
                            fail += 1
                            err = str(result.get("error", "Unknown error"))
                            print(f"[DEMO] 실패: {path} -> {err}")
                            if not self.first_error:
                                self.first_error = err
                            if len(self.error_samples) < 5:
                                self.error_samples.append(f"{os.path.basename(path)}: {err}")

                        progress_name = os.path.basename(result.get("path", path))
                        self._emit_progress(processed, total, progress_name)

                    if self._cancel:
                        for future in list(pending):
                            future.cancel()

                    while next_submit_idx <= total and len(pending) < submit_window and not self._cancel:
                        path = self.files[next_submit_idx - 1]
                        read_num = self.start_read_num + next_submit_idx
                        future = executor.submit(self._analyze_one, next_submit_idx, path, read_num)
                        pending[future] = (next_submit_idx, path)
                        next_submit_idx += 1

            if db_conn is not None and db_batch_rows:
                self._flush_batch(db_conn, db_batch_rows)

            self._emit_result_rows(force=True)
            self._emit_progress(processed, total, last_filename, force=True)
            self.finished.emit(ok, fail)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if db_conn is not None:
                try:
                    db_conn.close()
                except Exception:
                    pass


class AnalyzeSignals(QObject):
    result = Signal(list)
    error = Signal(str)


class AnalyzeTask(QRunnable):
    def __init__(self, controller, image_path, read_num, place, room):
        super().__init__()
        self.controller = controller
        self.image_path = image_path
        self.read_num = read_num
        self.place = place
        self.room = room
        self.signals = AnalyzeSignals()

    def run(self):
        try:
            row_data = self.controller.process_image(
                image_path=self.image_path,
                read_num=self.read_num,
                place=self.place,
                room=self.room,
            )
            self.signals.result.emit(row_data)
        except Exception as e:
            self.signals.error.emit(str(e))
