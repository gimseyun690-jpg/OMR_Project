from __future__ import annotations

import os

from PySide2.QtCore import QThread, Signal, QRunnable, QObject


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
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(self, controller, files, place, room, start_read_num):
        super().__init__()
        self.controller = controller
        self.files = files
        self.place = place
        self.room = room
        self.start_read_num = start_read_num
        self._cancel = False
        self.first_error = ""
        self.error_samples = []

    def cancel(self):
        self._cancel = True

    def run(self):
        ok = 0
        fail = 0
        total = len(self.files)
        read_num = self.start_read_num
        try:
            for idx, path in enumerate(self.files, start=1):
                if self._cancel:
                    break
                self.progress.emit(idx, total, os.path.basename(path))
                try:
                    read_num += 1
                    row_data = self.controller.process_image(
                        image_path=path,
                        read_num=read_num,
                        place=self.place,
                        room=self.room,
                    )
                    self.result_row.emit(row_data)
                    ok += 1
                except Exception as e:
                    fail += 1
                    print(f"[DEMO] 실패: {path} -> {e}")
                    if not self.first_error:
                        self.first_error = str(e)
                    if len(self.error_samples) < 5:
                        self.error_samples.append(f"{os.path.basename(path)}: {e}")
            self.finished.emit(ok, fail)
        except Exception as e:
            self.error.emit(str(e))


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
