import os
import cv2
import numpy as np
from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QFrame, QGroupBox, QComboBox, QSplitter,
                             QTableWidget, QHeaderView, QAbstractItemView, QMessageBox, QTableWidgetItem,
                             QFileDialog, QProgressDialog, QCheckBox, QMenu, QInputDialog, QApplication, QDialog)
from PySide2.QtCore import Qt, Slot, Signal, QThread, QObject, QRunnable, QThreadPool, QTimer
from PySide2.QtGui import QPixmap, QImage


# 기존 UI 컴포넌트 import
from ui.scanner.components.control_panel import ControlPanel
from ui.scanner.components.data_grid import DataGrid
from logic.scanner_core import ScannerDevice

# 추가 기능 연결을 위해 추가된 모듈
from logic.omr_engine import OMREngine
from database import DBManager
from ui.scanner.popups.error_editor import ErrorCorrectionDialog  # 오류 수정 팝업
from logic.pipeline import ScanPipeline
from logic.form_loader import list_forms, load_form, build_rois_from_form, get_anchor_from_form, get_omr_params, get_sheet_code


# =========================================================
# [스캔 워커 스레드 - 백그라운드에서 스캐너 처리(스캔)]
# =========================================================
class ScanWorker(QThread):
    image_scanned = Signal(str)
    scan_finished = Signal()
    error_occurred = Signal(str)

    # __init__에서 save_folder 인자 추가
    def __init__(self, hwnd, save_folder): 
        super().__init__()
        self.hwnd = hwnd
        self.save_folder = save_folder  # 경로 저장
        self.scanner = ScannerDevice()
        self.is_running = True


    def run(self):
        try:
            # 1. 연결
            success, msg = self.scanner.connect(self.hwnd)
            if not success:
                self.error_occurred.emit(f"SCAN_ERR|CONNECT|1|0|스캐너 연결 실패: {msg}")
                return

            # 2. 장비 열기
            success, msg = self.scanner.open_scanner()
            if not success:
                self.error_occurred.emit(f"SCAN_ERR|OPEN|1|0|장비 열기 실패: {msg}")
                return

            # 3. 급지 확인
            if not self.scanner.check_paper():
                self.error_occurred.emit("SCAN_ERR|NO_PAPER|0|0|급지대에 용지가 없습니다.")
                return

            # 4. scan 후 save_folder 전달
            for image_path in self.scanner.scan(self.save_folder):
                if not self.is_running: break
                
                # 여기서 바로 분석까지 해서 결과(dict)를 보낼 수도 있습니다.
                # 현재는 경로만 보내고, 메인에서 처리하도록 process_image는 다른 스레드에 맡깁니다.
                self.image_scanned.emit(image_path)
            
            self.scan_finished.emit()

        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.scanner.close()

    def stop(self):
        self.is_running = False
class DemoWorker(QThread):
    progress = Signal(int, int, str)   # current, total, filename
    result_row = Signal(list)          # row_data
    finished = Signal(int, int)        # ok, fail
    error = Signal(str)

    def __init__(self, pipeline, files, place, room, start_read_num):
        super().__init__()
        self.pipeline = pipeline
        self.files = files
        self.place = place
        self.room = room
        self.start_read_num = start_read_num
        self._cancel = False

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

                # 진행 신호
                self.progress.emit(idx, total, os.path.basename(path))

                try:
                    read_num += 1
                    row_data = self.pipeline.process_image(
                        image_path=path,
                        read_num=read_num,
                        place=self.place,
                        room=self.room,
                    )
                    self.result_row.emit(row_data)
                    ok += 1
                except Exception as e:
                    fail += 1
                    # 데모 실패여도 계속
                    print(f"[DEMO] 실패: {path} -> {e}")

            self.finished.emit(ok, fail)

        except Exception as e:
            self.error.emit(str(e))


class AnalyzeSignals(QObject):
    result = Signal(list)
    error = Signal(str)


class AnalyzeTask(QRunnable):
    def __init__(self, pipeline, image_path, read_num, place, room):
        super().__init__()
        self.pipeline = pipeline
        self.image_path = image_path
        self.read_num = read_num
        self.place = place
        self.room = room
        self.signals = AnalyzeSignals()

    def run(self):
        try:
            row_data = self.pipeline.process_image(
                image_path=self.image_path,
                read_num=self.read_num,
                place=self.place,
                room=self.room,
            )
            self.signals.result.emit(row_data)
        except Exception as e:
            self.signals.error.emit(str(e))


# =========================================================
# [메인 스캔 화면]
# =========================================================
class ScannerReadingView(QWidget):
    closed_signal = Signal()

    def set_project_db(self, db_path):
         self.set_current_db(db_path)

    def __init__(self, parent=None):
        super().__init__(parent)


        # 초기 변수 초기화
        self.total_read = 0
        self.worker = None
        self.session_start_read_num = 1
        self.thread_pool = QThreadPool()
        self.scan_in_progress = False
        self.pending_results = {}
        self.next_emit_read_num = 1
        self.pending_analyze = 0
        self.last_scan_params = None
        self.last_error_code = ""

        self.pipeline = ScanPipeline()

        # 엔진 & DB 매니저 생성
        self.engine = OMREngine()
        self.db = DBManager()
        self.current_db_path = None  # 현재 열려있는 DB 경로
        
        # [중요] 기준 좌표 (find.py에서 검출한 타이밍 마크 위치) - 필요 시 조정
        self.ref_anchor = (100, 500) 

        # UI 초기화
        self.init_ui()
        self.connect_signals()


    # -------------------------------------------------------------------------
        # [1] UI 작성
    # -------------------------------------------------------------------------
    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # === 1. 상단 정보/설정 패널 ===
        top_frame = QFrame()
        top_frame.setFixedHeight(140)
        top_frame.setStyleSheet("background-color: #F0F0F0; border-bottom: 1px solid #A0A0A0;")
        
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(10)

        # (1-1) 좌측: 카운트 그룹
        grp_cnt = QGroupBox()
        grp_cnt.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_cnt = QGridLayout(grp_cnt)
        grid_cnt.setContentsMargins(5, 5, 5, 5)
        grid_cnt.setVerticalSpacing(0)

        st_label = "color: black; font-weight: bold; font-size: 11px; border: none;"
        st_blue_num = "color: blue; font-weight: bold; font-size: 20px; border: none;"
        st_red_num = "color: red; font-weight: bold; font-size: 20px; border: none;"

        grid_cnt.addWidget(QLabel("총판독매수", styleSheet=st_label), 0, 0, alignment=Qt.AlignCenter)
        grid_cnt.addWidget(QLabel("총점검매수", styleSheet=st_label), 0, 1, alignment=Qt.AlignCenter)
        
        self.lbl_total = QLabel("0", styleSheet=st_blue_num)
        grid_cnt.addWidget(self.lbl_total, 1, 0, alignment=Qt.AlignCenter)
        
        self.lbl_check = QLabel("0", styleSheet=st_red_num)
        grid_cnt.addWidget(self.lbl_check, 1, 1, alignment=Qt.AlignCenter)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setStyleSheet("color: #ccc;")
        grid_cnt.addWidget(line, 2, 0, 1, 2)

        # [수정] 현재 고사장/시험실/판독매수 라벨 분리
        lbl_cur_title = QLabel("현재 고사장/시험실/판독매수", styleSheet="font-size:10px; font-weight:bold; color:#555; border:none;")
        grid_cnt.addWidget(lbl_cur_title, 3, 0, 1, 2)

        sub_layout = QGridLayout()
        sub_layout.addWidget(QLabel("현재 고사장:", styleSheet="font-size:11px; border:none;"), 0, 0)
        # 실시간 변경 라벨
        self.lbl_cur_place = QLabel("스캐너1", styleSheet="color:blue; font-weight:bold; border:none;")
        sub_layout.addWidget(self.lbl_cur_place, 0, 1)
        
        sub_layout.addWidget(QLabel("현재 시험실:", styleSheet="font-size:11px; border:none;"), 1, 0)
        self.lbl_cur_room = QLabel("1", styleSheet="color:blue; font-weight:bold; font-size:14px; border:none;")
        sub_layout.addWidget(self.lbl_cur_room, 1, 1)

        sub_layout.addWidget(QLabel("현재 판독매수", styleSheet="font-size:11px; border:none;"), 0, 2, 2, 1)
        self.lbl_cur_cnt = QLabel("0", styleSheet="color:red; font-weight:bold; font-size:18px; border:none;")
        sub_layout.addWidget(self.lbl_cur_cnt, 0, 3, 2, 1)

        grid_cnt.addLayout(sub_layout, 4, 0, 1, 2)

        # 상세 오류 카운트(고정 표시)
        self.lbl_review_detail = QLabel("오류:0  중복:0  공백:0  명단미매칭:0  결시:0")
        self.lbl_review_detail.setStyleSheet("font-size:10px; color:#666; border:none;")
        self.lbl_review_detail.setAlignment(Qt.AlignCenter)
        grid_cnt.addWidget(self.lbl_review_detail, 5, 0, 1, 2)

        # (1-2) 중앙: 설정
        grp_set = QGroupBox()
        grp_set.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_set = QGridLayout(grp_set)
        
        st_blue_lbl = "color: blue; font-weight: bold; font-size: 12px; border: none;"
        st_combo = "QComboBox { border: 1px solid #999; padding: 2px; font-size: 12px; font-weight: bold; color: black; }"
        
        self.cb_form = QComboBox()
        self.cb_form.setStyleSheet(st_combo)

        self._forms = list_forms()
        if not self._forms:
            self.cb_form.addItem("없음 (resources/forms)", userData=None)
        else:
            for form_id, display, path in self._forms:
                self.cb_form.addItem(display, userData=path)

        
        # [수정] 스캐너1~10 목록 채우기
        self.cb_place = QComboBox(); self.cb_place.setStyleSheet(st_combo)
        for i in range(1, 11):
            self.cb_place.addItem(f"스캐너{i}")

        # [수정] 시험실 1~1000 목록 채우기
        self.cb_room = QComboBox(); self.cb_room.setStyleSheet(st_combo)
        for i in range(1, 1000):
            self.cb_room.addItem(str(i))

        grid_set.addWidget(QLabel("스캔 OMR 양식 :", styleSheet=st_blue_lbl), 0, 0)
        grid_set.addWidget(self.cb_form, 0, 1)
        grid_set.addWidget(QLabel("판독 고사장:", styleSheet="font-weight:bold; border:none;"), 1, 0)
        grid_set.addWidget(self.cb_place, 1, 1)
        grid_set.addWidget(QLabel("판독 시험실:", styleSheet="font-weight:bold; border:none;"), 2, 0)
        grid_set.addWidget(self.cb_room, 2, 1)

        # (1-3) 우측: 오류처리
        grp_err = QGroupBox("오류처리")
        grp_err.setStyleSheet(
            "QGroupBox { background-color: white; border: 1px solid #999; font-size: 11px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; padding: 0 6px; }"
        )
        grp_err.setMinimumWidth(260)
        grid_err = QGridLayout(grp_err)
        self.cb_err_opt = QComboBox(); self.cb_err_opt.addItem("이미지 오류(미리보기/읽기오류 스캔완료보류)")
        self.cb_stop_opt = QComboBox(); self.cb_stop_opt.addItem("모든 오류 스캔중단")
        grid_err.addWidget(QLabel("스캔중 오류처리 보기 :", styleSheet="border:none;"), 0, 0)
        grid_err.addWidget(self.cb_err_opt, 0, 1)
        grid_err.addWidget(QLabel("오류발생시 스캔중단 :", styleSheet="border:none;"), 1, 0)
        grid_err.addWidget(self.cb_stop_opt, 1, 1)

        # (1-4) 우측 하단 체크박스
        grp_chk = QGroupBox("오류필터")
        grp_chk.setStyleSheet(
            "QGroupBox { background-color: white; border: 1px solid #999; font-size: 11px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; padding: 0 6px; }"
        )
        grp_chk.setMinimumWidth(150)
        v_chk = QVBoxLayout(grp_chk)
        
        # [수정] 멤버 변수로 할당하여 상태 확인
        self.chk_all_blank = QCheckBox("전체공백 무효처리")
        self.chk_etc_error = QCheckBox("기타 무효처리")
        
        # 기본 체크
        self.chk_all_blank.setChecked(True)
        self.chk_etc_error.setChecked(True)

        v_chk.addWidget(self.chk_all_blank)
        v_chk.addWidget(self.chk_etc_error)

        top_layout.addWidget(grp_cnt, 14)
        top_layout.addWidget(grp_set, 34)
        top_layout.addWidget(grp_err, 36)
        top_layout.addWidget(grp_chk, 16) # grp_chk 추가
        main_layout.addWidget(top_frame)

        # === 2. 하단 3분할 ===
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ccc; }")

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(3)
        self.summary_table.setHorizontalHeaderLabels(["판독고사장", "판독시험실", "판독매수"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.summary_table.setStyleSheet("QHeaderView::section { background-color: #D1E8FF; border: 1px solid #999; font-weight: bold; font-size: 11px; } QTableWidget { gridline-color: #ccc; font-size: 11px; }")
        self.summary_table.insertRow(0)
        self.summary_table.setItem(0, 0, self._item("스캐너1"))
        self.summary_table.setItem(0, 1, self._item("1"))
        self.summary_table.setItem(0, 2, self._item("0"))

        self.main_grid = DataGrid()
        self.main_grid.setContextMenuPolicy(Qt.CustomContextMenu)
        self.main_grid.customContextMenuRequested.connect(self._on_grid_context_menu)
        self.control_panel = ControlPanel()

        splitter.addWidget(self.summary_table)
        splitter.addWidget(self.main_grid)
        splitter.addWidget(self.control_panel)
        splitter.setSizes([200, 1200, 260])
        splitter.setCollapsible(2, False)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    # -------------------------------------------------------------------------
    # [2] 유틸/설정 함수
    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # [2] 핵심 로직: 오류 점검 창 (Next/Prev)
    # -------------------------------------------------------------------------
    def open_error_check(self, auto_next: bool = False):
        """오류 점검 버튼 클릭 시 실행"""
        if not self.current_db_path: 
            return

        # 1. DB에서 모든 데이터 가져오기
        all_rows = self.db.get_all_scans(self.current_db_path)
        
        # 2. 필터링 (체크박스 상태 반영)
        self.error_queue = []  # Index가 아닌 Row 데이터 객체 리스트

        check_blank = self.chk_all_blank.isChecked()
        check_etc = self.chk_etc_error.isChecked()

        for row in all_rows:
            is_valid = row[7]      # 0:오류, 1:정상
            mark_result = row[6]   # "10302..."
            
            # 정상이라면 스킵
            if is_valid == 1:
                continue

            # 오류 유형 분석
            is_blank_paper = (mark_result.replace('0', '') == '')  # 전부 0이면 공백지
            
            if is_blank_paper and check_blank:
                self.error_queue.append(row)
            elif not is_blank_paper and check_etc:
                self.error_queue.append(row)

        if not self.error_queue:
            QMessageBox.information(self, "완료", "점검할 오류가 없습니다.\n(설정 조건에 맞는 오류가 없음)")
            return

        # 3. 점검 루프 시작 (첫 번째 오류부터)
        completed_all = self.run_review_loop(0)
        if completed_all:
            if auto_next and self.control_panel.chk_next.isChecked():
                QMessageBox.information(self, "점검 완료", "점검이 끝났습니다. 다음 시험실로 이동합니다.")
                self._advance_room()
                self.start_scan()
            else:
                QMessageBox.information(self, "점검 완료", "점검이 끝났습니다.")

    def run_review_loop(self, start_idx):
        """오류들을 반복 점검하는 다이얼로그 루프"""
        current_idx = start_idx
        
        while 0 <= current_idx < len(self.error_queue):
            row = self.error_queue[current_idx]
            
            # (1) 데이터 준비
            read_num = row[1]
            image_path = row[4]
            result_str = row[6]
            
            # "103" -> [{'q_num':1, 'marked':[0]}, ...] 변환
            scan_results = self.parse_result_string(result_str)

            # (2) 이미지 로드 (경로 직접)
            image_cv = None
            try:
                # numpy로 읽어 cv2 디코드 (한글 경로 오류 방지)
                img_array = np.fromfile(image_path, np.uint8)
                image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"이미지 로드 실패: {e}")

            # (3) 다이얼로그 실행
            dlg = ErrorCorrectionDialog(self, image_cv, scan_results, image_path)
            session_total = max(0, self.total_read - self.session_start_read_num + 1)
            dlg.lbl_idx.setText(f"{current_idx + 1}/{session_total}")  # 오류 순번/이번 고사실 읽은 장수
            
            # exec_()은 창이 닫힐 때까지 대기함
            dlg.exec_() 

            # (4) 종료 코드 확인 (Dialog에서 exit_code 설정 필요)
            exit_code = getattr(dlg, 'exit_code', 0)

            if exit_code == 0:  # 그냥 닫음 (X버튼) -> 루프 종료
                break
            
            elif exit_code == 1:  # 저장(S) -> 다음으로
                self.save_corrected_data(row, dlg.scan_results)
                current_idx += 1  # 다음 이동

            elif exit_code == 2:  # 이전 (<) -> 저장하지 않고 이전으로
                current_idx -= 1
                if current_idx < 0:
                    QMessageBox.information(self, "알림", "첫 번째 항목입니다.")
                    current_idx = 0

            elif exit_code == 3:  # 다음 (>) -> 저장하지 않고 다음으로
                current_idx += 1

        # 루프 종료 후 통계 갱신
        self.update_statistics()
        if current_idx >= len(self.error_queue):
             return True
        return False

    def parse_result_string(self, result_str):
        """문자열 '103'을 다이얼로그용 리스트로 변환"""
        parsed = []
        for i, char in enumerate(result_str):
            marked = []
            status = "정상"
            
            if char == '1': marked = [0]       # 찬성
            elif char == '2': marked = [1]     # 반대
            elif char == '3':                  # 중복
                marked = [0, 1]
                status = "중복"
            elif char == '0':                  # 공백
                marked = []
                status = "공백"
            
            parsed.append({'q_num': i+1, 'marked': marked, 'status': status})
        return parsed

    def save_corrected_data(self, original_row, modified_results):
        """수정된 데이터를 DB에 저장"""
        new_result_str = ""
        for r in modified_results:
            # 리스트 -> 문자열 변환
            val = "0"
            if len(r['marked']) == 0: val = "0"
            elif len(r['marked']) > 1: val = "3"
            elif 0 in r['marked']: val = "1"
            elif 1 in r['marked']: val = "2"
            new_result_str += val
        
        read_num = original_row[1]
        image_path = original_row[4]
        before_str = original_row[6]

        # 1. 수정 이력 저장
        self.db.insert_manual_edit(
            self.current_db_path,
            read_num=read_num,
            image_path=image_path,
            before_result=before_str,
            after_result=new_result_str,
            reason="오류수정(수동수정)"
        )

        # 2. 원본 데이터 업데이트 (강제 유효=1)
        self.db.update_scan_result(self.current_db_path, read_num, new_result_str, 1)

    def _item(self, text):
        """아이템 데이터 생성 헬퍼"""
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _get_selected_rows(self):
        model = self.main_grid.selectionModel()
        if not model:
            return []
        return sorted([idx.row() for idx in model.selectedRows()])

    def _get_selected_read_nums(self):
        rows = self._get_selected_rows()
        read_nums = []
        for r in rows:
            item = self.main_grid.item(r, 0)
            if item:
                try:
                    read_nums.append(int(item.text()))
                except Exception:
                    pass
        return read_nums

    def _get_row_data_by_read_num(self, read_num):
        if not self.current_db_path:
            return None
        return self.db.get_scan_by_read_num(self.current_db_path, read_num)

    def _open_review_for_row(self, row_data):
        if not row_data:
            return
        read_num = row_data[1]
        image_path = row_data[4]
        result_str = row_data[6]
        scan_results = self.parse_result_string(result_str)

        image_cv = None
        try:
            img_array = np.fromfile(image_path, np.uint8)
            image_cv = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"이미지 로드 실패: {e}")

        dlg = ErrorCorrectionDialog(self, image_cv, scan_results, image_path)
        dlg.lbl_idx.setText(str(read_num))
        dlg.exec_()

        exit_code = getattr(dlg, 'exit_code', 0)
        if exit_code == 1:
            self.save_corrected_data(row_data, dlg.scan_results)
            self.update_statistics()

    def _delete_rows(self, delete_images: bool):
        read_nums = self._get_selected_read_nums()
        if not read_nums or not self.current_db_path:
            return
        msg = "선택한 결과와 이미지 파일을 삭제할까요?" if delete_images else "선택한 결과만 삭제할까요?"
        if QMessageBox.question(self, "삭제 확인", msg) != QMessageBox.Yes:
            return
        for rn in read_nums:
            row = self._get_row_data_by_read_num(rn)
            if delete_images and row and row[4] and os.path.exists(row[4]):
                try:
                    os.remove(row[4])
                except Exception as e:
                    print(f"이미지 삭제 실패: {e}")
            self.db.delete_scan_result(self.current_db_path, rn)
        for r in reversed(self._get_selected_rows()):
            self.main_grid.removeRow(r)
        self.update_statistics()

    def _change_place_or_room(self, field_name: str):
        read_nums = self._get_selected_read_nums()
        if not read_nums or not self.current_db_path:
            return
        title = "판독고사장 변경" if field_name == "place" else "판독시험실 변경"
        text, ok = QInputDialog.getText(self, title, "변경할 값:")
        if not ok or not text.strip():
            return
        for rn in read_nums:
            if field_name == "place":
                self.db.update_scan_meta(self.current_db_path, rn, scanner_name=text.strip())
            else:
                self.db.update_scan_meta(self.current_db_path, rn, room_no=text.strip())
        for r in self._get_selected_rows():
            col = 2 if field_name == "place" else 3
            item = self.main_grid.item(r, col)
            if item:
                item.setText(text.strip())
        self.update_statistics()

    def _change_front_path(self):
        read_nums = self._get_selected_read_nums()
        if len(read_nums) != 1 or not self.current_db_path:
            QMessageBox.information(self, "안내", "한 건만 선택해주세요.")
            return
        new_path, _ = QFileDialog.getOpenFileName(self, "앞면 경로 변경", "", "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if not new_path:
            return
        rn = read_nums[0]
        self.db.update_scan_meta(self.current_db_path, rn, image_path=new_path)
        r = self._get_selected_rows()[0]
        item_path = self.main_grid.item(r, 7)
        item_name = self.main_grid.item(r, 8)
        if item_path:
            item_path.setText(new_path)
        if item_name:
            item_name.setText(os.path.basename(new_path))

    def _renumber_by_room(self):
        if not self.current_db_path:
            return
        all_rows = self.db.get_all_scans(self.current_db_path)
        if not all_rows:
            return
        # row: (id, read_num, scanner_name, room_no, image_path, sheet_code, mark_result, is_valid, scan_time)
        ordered = sorted(all_rows, key=lambda r: (str(r[2]), str(r[3]), int(r[1])))
        ordered_read_nums = [r[1] for r in ordered]
        self.db.renumber_read_nums(self.current_db_path, ordered_read_nums)
        self.reload_grid_from_db()

    def _rename_image_files(self):
        if not self.current_db_path:
            return
        all_rows = self.db.get_all_scans(self.current_db_path)
        if not all_rows:
            return
        if QMessageBox.question(self, "확인", "이미지 파일명을 일괄 변경할까요?") != QMessageBox.Yes:
            return
        for idx, row in enumerate(all_rows, start=1):
            path = row[4]
            if not path or not os.path.exists(path):
                continue
            base_dir = os.path.dirname(path)
            ext = os.path.splitext(path)[1]
            new_name = f"scan_{idx:05d}{ext}"
            new_path = os.path.join(base_dir, new_name)
            try:
                os.rename(path, new_path)
                self.db.update_scan_meta(self.current_db_path, row[1], image_path=new_path)
            except Exception as e:
                print(f"파일명 변경 실패: {e}")
        self.reload_grid_from_db()

    def reload_grid_from_db(self):
        if not self.current_db_path:
            return
        self.main_grid.setRowCount(0)
        rows = self.db.get_all_scans(self.current_db_path)
        for row in rows:
            read_num = row[1]
            place = row[2]
            room = row[3]
            image_path = row[4]
            sheet_code = row[5]
            result_str = row[6]
            is_valid = row[7]
            ui_status = "정상" if is_valid == 1 else "오류"
            row_data = [
                str(read_num),
                str(sheet_code),
                str(place),
                str(room),
                ui_status,
                "완료",
                str(result_str),
                str(image_path),
                os.path.basename(image_path) if image_path else "",
            ]
            self.main_grid.add_row_data(row_data)

    def _find_text(self, from_current: bool):
        text, ok = QInputDialog.getText(self, "찾기", "검색어:")
        if not ok or not text:
            return
        start_row = 0
        if from_current:
            sel = self._get_selected_rows()
            if sel:
                start_row = sel[0] + 1
        for r in range(start_row, self.main_grid.rowCount()):
            for c in range(self.main_grid.columnCount()):
                item = self.main_grid.item(r, c)
                if item and text in item.text():
                    self.main_grid.selectRow(r)
                    self.main_grid.scrollToItem(item)
                    return
        QMessageBox.information(self, "찾기", "검색 결과가 없습니다.")

    def _copy_selected_rows(self):
        rows = self._get_selected_rows()
        if not rows:
            return
        lines = []
        for r in rows:
            vals = []
            for c in range(self.main_grid.columnCount()):
                item = self.main_grid.item(r, c)
                vals.append(item.text() if item else "")
            lines.append("\t".join(vals))
        QApplication.clipboard().setText("\n".join(lines))

    def _on_grid_context_menu(self, pos):
        if not self._get_selected_rows():
            return
        menu = QMenu(self)
        act_review = menu.addAction("현재건 판독결과 조회/수정")
        menu.addSeparator()
        act_copy = menu.addAction("복사")
        menu.addSeparator()
        act_del_all = menu.addAction("전체자료+이미지 삭제")
        act_del_row = menu.addAction("자료만 삭제(이미지 제외)")
        menu.addSeparator()
        act_place = menu.addAction("판독고사장 변경")
        act_room = menu.addAction("판독시험실 변경")
        menu.addSeparator()
        act_front = menu.addAction("앞면경로 변경")
        act_back = menu.addAction("뒷면경로 변경")
        act_back.setEnabled(False)
        menu.addSeparator()
        act_renum = menu.addAction("판독번호 고사장/시험실 순으로 전체 재부여")
        act_rename = menu.addAction("이미지파일명 전체 재부여")
        menu.addSeparator()
        act_find_start = menu.addAction("처음부터 찾기")
        act_find_next = menu.addAction("현재이후부터 찾기")

        action = menu.exec_(self.main_grid.viewport().mapToGlobal(pos))
        if action == act_review:
            rn = self._get_selected_read_nums()[0]
            self._open_review_for_row(self._get_row_data_by_read_num(rn))
        elif action == act_copy:
            self._copy_selected_rows()
        elif action == act_del_all:
            self._delete_rows(delete_images=True)
        elif action == act_del_row:
            self._delete_rows(delete_images=False)
        elif action == act_place:
            self._change_place_or_room("place")
        elif action == act_room:
            self._change_place_or_room("room")
        elif action == act_front:
            self._change_front_path()
        elif action == act_renum:
            self._renumber_by_room()
        elif action == act_rename:
            self._rename_image_files()
        elif action == act_find_start:
            self._find_text(from_current=False)
        elif action == act_find_next:
            self._find_text(from_current=True)

    def set_current_db(self, db_path):
        self.current_db_path = db_path
        self.pipeline.set_project(db_path)

        try:
            self.update_statistics()
        except Exception as e:
            QMessageBox.critical(self, "DB 오류", f"통계 갱신 중 오류:\n{e}")


    # 1. 좌표 가져오기 (DB 연동 버전)
    def get_rois(self):
        """DB에서 좌표 설정값을 불러 ROIs 생성"""
        if not self.current_db_path:
            # DB가 없으면 기본값 반환
            return self.get_default_rois()

        try:
            # (1) DB에서 값 불러오기 (값이 없으면 기본값 사용)
            start_y = int(self.db.get_setting(self.current_db_path, "roi_start_y", "515"))
            gap_y = int(self.db.get_setting(self.current_db_path, "roi_gap_y", "90"))
            w = int(self.db.get_setting(self.current_db_path, "roi_w", "35"))
            h = int(self.db.get_setting(self.current_db_path, "roi_h", "35"))
            x_agree = int(self.db.get_setting(self.current_db_path, "roi_agree_x", "1130"))
            x_disagree = int(self.db.get_setting(self.current_db_path, "roi_disagree_x", "1275"))
            
            # (2) 좌표 리스트 생성
            rois = []
            for i in range(5):
                y = start_y + (i * gap_y)
                rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])
            return rois
            
        except Exception as e:
            print(f"좌표 로드 오류: {e}")
            return self.get_default_rois()

    def get_default_rois(self):
        """기본 좌표"""
        w, h = 35, 35
        x_agree = 1130; x_disagree = 1275
        start_y = 515; gap_y = 90
        rois = []
        for i in range(5):
            y = start_y + (i * gap_y)
            rois.append([(x_agree, y, w, h), (x_disagree, y, w, h)])
        return rois

    # -------------------------------------------------------------------------
    # [3] 이벤트 연결 핸들러 (버튼 동작)
    # -------------------------------------------------------------------------
    def connect_signals(self):
        # 기존 버튼 연결
        self.control_panel.btn_close.clicked.connect(self.go_back_home)
        self.control_panel.btn_scan.clicked.connect(self.start_scan)
        self.control_panel.btn_check.clicked.connect(self.open_error_check)
        self.control_panel.btn_demo.clicked.connect(self.run_demo_folder)
        self.control_panel.btn_next.clicked.connect(self.scan_next_room)
        self.control_panel.btn_stop.clicked.connect(self.stop_scan)
        self.control_panel.btn_retry.clicked.connect(self.retry_last_scan)

        
        # [추가] 콤보박스 변경 시 상단 라벨 자동 업데이트
        self.cb_place.currentTextChanged.connect(self.lbl_cur_place.setText)
        self.cb_room.currentTextChanged.connect(self.lbl_cur_room.setText)

        self.cb_form.currentIndexChanged.connect(self.on_form_changed)
        self.on_form_changed()  # 초기 1회 적용

    def on_form_changed(self):
        self.pipeline.set_form_path(self.cb_form.currentData())


    def go_back_home(self):
        self.closed_signal.emit()

    def run_demo_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "데모 이미지 폴더 선택")
        if not folder:
            return

        exts = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]
        files.sort()

        if not files:
            QMessageBox.information(self, "알림", "선택한 폴더에 이미지가 없습니다.")
            return

        # UI 잠금
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_check.setEnabled(False)
        self.control_panel.btn_demo.setEnabled(False)
        self.control_panel.btn_demo.setText("데모 진행중...")

        current_place = self.cb_place.currentText()
        current_room = self.cb_room.currentText()

        # 진행용 다이얼로그
        self.demo_progress = QProgressDialog("데모 판독 준비중...", "취소", 0, len(files), self)
        self.demo_progress.setWindowTitle("데모 진행")
        self.demo_progress.setWindowModality(Qt.WindowModal)
        self.demo_progress.setAutoClose(False)
        self.demo_progress.setAutoReset(False)
        self.demo_progress.show()

        # 워커 생성
        start_read_num = self.total_read
        self.demo_worker = DemoWorker(
            pipeline=self.pipeline,
            files=files,
            place=current_place,
            room=current_room,
            start_read_num=start_read_num
        )

        # 연결
        self.demo_progress.canceled.connect(self.demo_worker.cancel)
        self.demo_worker.progress.connect(self._on_demo_progress)
        self.demo_worker.result_row.connect(self._on_demo_row)
        self.demo_worker.finished.connect(self._on_demo_finished)
        self.demo_worker.error.connect(self._on_demo_error)

        self.demo_worker.start()
    
    def _on_demo_progress(self, current, total, filename):
        if hasattr(self, "demo_progress") and self.demo_progress:
            self.demo_progress.setMaximum(total)
            self.demo_progress.setValue(current)
            self.demo_progress.setLabelText(f"데모 판독중... ({current}/{total})\n{filename}")

    def _on_demo_row(self, row_data):
        # UI에 결과 반영 (메인 스레드)
        self.main_grid.add_row_data(row_data)
        self.total_read = int(row_data[0])  # read_num 반영
        if len(row_data) > 7 and hasattr(self.control_panel, "image_viewer"):
            self.control_panel.image_viewer.set_image_path(row_data[7])
        self.lbl_total.setText(str(self.total_read))
        self.lbl_cur_cnt.setText(str(self.total_read))
        self.control_panel.txt_temp.setText(str(self.total_read))
        self.main_grid.scrollToBottom()

    def _on_demo_finished(self, ok, fail):
        # UI 복원
        if hasattr(self, "demo_progress") and self.demo_progress:
            self.demo_progress.close()

        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_check.setEnabled(True)
        self.control_panel.btn_demo.setEnabled(True)
        self.control_panel.btn_demo.setText("📂 테스트 이미지 불러오기")

        try:
            self.update_statistics()
        except Exception:
            pass

        # 데모 종료 후 다음 시험실로 자동 이동
        self._advance_room()

        QMessageBox.information(self, "데모 완료", f"성공 {ok} / 실패 {fail}")

    def _on_demo_error(self, msg):
        if hasattr(self, "demo_progress") and self.demo_progress:
            self.demo_progress.close()

        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_check.setEnabled(True)
        self.control_panel.btn_demo.setEnabled(True)
        self.control_panel.btn_demo.setText("📂 테스트 이미지 불러오기")

        QMessageBox.critical(self, "데모 오류", msg)




    @Slot()
    def start_scan(self):
        """스캔 버튼 클릭 시"""
        if self.scan_in_progress:
            return
        if self.current_db_path is None:
            QMessageBox.warning(self, "경고", "먼저 '파일 설정' 메뉴에서 사용할 DB 파일을 선택(열기)해 주세요!")
            return
        # [추가] DB에서 저장 경로 불러오기
        default_path = os.path.abspath(os.path.join("data", "scan_images"))
        save_folder = default_path
        # DB 설정값이 없으면 기본값 사용
        if self.current_db_path:
            save_folder = self.db.get_setting(self.current_db_path, "image_save_path", default_path)
            
        # 폴더가 없으면 생성
        if not os.path.exists(save_folder):
            try:
                os.makedirs(save_folder)
            except Exception as e:
                QMessageBox.critical(self, "오류", f"폴더 생성 실패: {e}")
                return

        # [추가] 이번 스캔 세션 카운트 초기화
        self.current_session_count = 0
        self.session_start_read_num = self.total_read + 1
        self.pending_results = {}
        self.next_emit_read_num = self.session_start_read_num
        self.pending_analyze = 0
        self.auto_next_pending = False

        # 재시도 대비 설정 저장
        self.last_scan_params = {
            "form_index": self.cb_form.currentIndex(),
            "place_index": self.cb_place.currentIndex(),
            "room_index": self.cb_room.currentIndex(),
        }

        my_hwnd = int(self.winId())
        # [수정] 워커 생성 시 save_folder 전달
        self.worker = ScanWorker(my_hwnd, save_folder)
        
        self.worker.image_scanned.connect(self.on_image_received)
        self.worker.scan_finished.connect(self.on_finished)
        self.worker.error_occurred.connect(self.on_error)
        
        self.control_panel.btn_scan.setEnabled(False)
        self.control_panel.btn_scan.setText("스캔중...")
        self.control_panel.btn_next.setEnabled(False)
        self.control_panel.btn_stop.setEnabled(True)
        self.control_panel.btn_retry.setEnabled(False)
        self.scan_in_progress = True
        self.worker.start()

    @Slot(str)
    def on_image_received(self, image_path):
        self.total_read += 1
        self.current_session_count += 1  # 현재 시험실 카운트

        if hasattr(self.control_panel, "image_viewer"):
            self.control_panel.image_viewer.set_image_path(image_path)

        task = AnalyzeTask(
            pipeline=self.pipeline,
            image_path=image_path,
            read_num=self.total_read,
            place=self.cb_place.currentText(),
            room=self.cb_room.currentText(),
        )
        self.pending_analyze += 1
        task.signals.result.connect(self._on_analyze_result)
        task.signals.error.connect(self._on_analyze_error)
        self.thread_pool.start(task)

    def _on_analyze_result(self, row_data):
        self.pending_analyze = max(self.pending_analyze - 1, 0)
        try:
            read_num = int(row_data[0])
        except Exception:
            read_num = None

        if read_num is None:
            self._append_row(row_data)
        else:
            self.pending_results[read_num] = row_data
            self._flush_pending_results()

        if self.pending_analyze == 0:
            self._maybe_start_auto_review()

    def _on_analyze_error(self, msg):
        self.pending_analyze = max(self.pending_analyze - 1, 0)
        QMessageBox.warning(self, "오류", msg)
        if self.pending_analyze == 0:
            self._maybe_start_auto_review()

    def _flush_pending_results(self):
        while self.next_emit_read_num in self.pending_results:
            row_data = self.pending_results.pop(self.next_emit_read_num)
            self._append_row(row_data)
            self.next_emit_read_num += 1

    def _append_row(self, row_data):
        if len(row_data) > 5 and row_data[5] == "타이밍 마크 오류입니다.":
            self._show_timing_mark_error(row_data[7], row_data[5])
        self.main_grid.add_row_data(row_data)
        self.lbl_total.setText(str(self.total_read))        # 전체 누적
        self.lbl_cur_cnt.setText(str(self.current_session_count))  # 현재 시험실만
        self.main_grid.scrollToBottom()

    def _show_timing_mark_error(self, image_path, message):
        dlg = QDialog(self)
        dlg.setWindowTitle("타이밍 마크 오류")
        layout = QVBoxLayout(dlg)

        lbl_msg = QLabel(message)
        lbl_msg.setStyleSheet("font-size: 13px; font-weight: bold; color: #c00;")
        layout.addWidget(lbl_msg)

        img = None
        try:
            img_array = np.fromfile(image_path, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except Exception:
            img = None

        if img is not None:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            bytes_per_line = w * 3
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            max_w = 900
            if pixmap.width() > max_w:
                pixmap = pixmap.scaledToWidth(max_w, Qt.SmoothTransformation)
            lbl_img = QLabel()
            lbl_img.setPixmap(pixmap)
            lbl_img.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl_img)

        dlg.resize(920, 600)
        dlg.exec_()
    


    def update_statistics(self):
        """DB 통계(총매수, 오류매수) 갱신"""
        if not self.current_db_path: return
        total, normal, error = self.db.get_statistics(self.current_db_path)
        
        self.lbl_total.setText(str(total))
        self.lbl_check.setText(str(error)) 
        self.control_panel.txt_temp.setText(str(total))

    def update_review_summary(self):
        if not self.current_db_path:
            return
        try:
            rows = self.db.get_scans_in_range(self.current_db_path, self.session_start_read_num, self.total_read)
            roster_rows = self.db.load_roster(self.current_db_path)
        except Exception:
            return

        roster_by_exam = {str(r[0]).strip(): r for r in roster_rows if r and len(r) > 0}

        start = self.session_start_read_num
        end = self.total_read

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
            is_valid = row[2]
            exam_no = str(row[3] or "").strip()

            needs_review = False
            if is_valid == 0:
                needs_review = True
                invalid_cnt += 1
            if "0" in mark_result or "3" in mark_result:
                needs_review = True
                if "3" in mark_result:
                    dup_cnt += 1
                if mark_result.replace("0", "") == "":
                    blank_cnt += 1

            lookup_key = exam_no if exam_no else str(read_num)
            roster = roster_by_exam.get(lookup_key)
            if roster is None:
                needs_review = True
                roster_missing_cnt += 1
            else:
                attendance = str(roster[6]).strip() if len(roster) > 6 else ""
                if attendance and attendance in ("미응시", "결시", "불참", "N", "NO", "0"):
                    needs_review = True
                    absent_cnt += 1

            if needs_review:
                review_count += 1

        if total_in_session > 0:
            self.lbl_check.setText(f"{review_count}/{total_in_session}")
            self.lbl_review_detail.setText(
                f"오류:{invalid_cnt}  중복:{dup_cnt}  공백:{blank_cnt}  "
                f"명단미매칭:{roster_missing_cnt}  결시:{absent_cnt}"
            )

    @Slot()
    def on_finished(self):
        # [기존 기능] 좌측 요약 테이블 추가
        place = self.cb_place.currentText()
        room = self.cb_room.currentText()
        count = str(self.current_session_count)
        
        row = self.summary_table.rowCount()
        self.summary_table.insertRow(row)
        self.summary_table.setItem(row, 0, self._item(place))
        self.summary_table.setItem(row, 1, self._item(room))
        self.summary_table.setItem(row, 2, self._item(count))
        
        if self.control_panel.chk_next.isChecked():
            QMessageBox.information(self, "완료", f"{place} - {room} 시험실 스캔 완료\n(총 {count}매)")
            self.reset_ui_state()
            self.control_panel.btn_retry.setEnabled(False)
            self.update_review_summary()
            self.auto_next_pending = True
            self._maybe_start_auto_review()
        else:
            # [수정] 시험실 번호 자동 증가
            self._advance_room()
            QMessageBox.information(self, "완료", f"{place} - {room} 시험실 스캔 완료\n(총 {count}매)")
            self.reset_ui_state()
            self.control_panel.btn_retry.setEnabled(False)
            self.update_review_summary()
    @Slot(str)
    def on_error(self, msg):
        code, retryable, auto_retry, user_msg = self._parse_scan_error(msg)
        self.last_error_code = code

        if user_msg:
            QMessageBox.warning(self, "오류", user_msg)
        else:
            QMessageBox.warning(self, "오류", msg)

        if retryable:
            self.control_panel.btn_retry.setEnabled(True)

        self.reset_ui_state()
        if auto_retry and self.control_panel.chk_auto_retry.isChecked():
            QTimer.singleShot(500, self.retry_last_scan)

    def reset_ui_state(self):
        self.control_panel.btn_scan.setEnabled(True)
        self.control_panel.btn_scan.setText("📄 현재시험실 스캔(R)")
        self.control_panel.btn_next.setEnabled(True)
        self.control_panel.btn_stop.setEnabled(True)
        self.scan_in_progress = False

    def scan_next_room(self):
        if self.scan_in_progress:
            return
        self._advance_room()
        self.start_scan()

    def stop_scan(self):
        if not self.scan_in_progress:
            return
        if self.worker:
            try:
                self.worker.stop()
            except Exception:
                pass
        self.reset_ui_state()
        QMessageBox.information(self, "중단", "스캔이 중단되었습니다.")

    def retry_last_scan(self):
        if self.scan_in_progress:
            return
        if not self.last_scan_params:
            QMessageBox.information(self, "재시도", "이전 스캔 정보가 없습니다.")
            return
        try:
            self.cb_form.setCurrentIndex(self.last_scan_params.get("form_index", 0))
            self.cb_place.setCurrentIndex(self.last_scan_params.get("place_index", 0))
            self.cb_room.setCurrentIndex(self.last_scan_params.get("room_index", 0))
        except Exception:
            pass
        self.control_panel.btn_retry.setEnabled(False)
        self.start_scan()

    def _parse_scan_error(self, msg):
        if not msg or not isinstance(msg, str):
            return "", False, False, ""
        if not msg.startswith("SCAN_ERR|"):
            return "", False, False, ""
        try:
            _, code, retryable, auto_retry, user_msg = msg.split("|", 4)
            return code, retryable == "1", auto_retry == "1", user_msg
        except Exception:
            return "", False, False, ""

    def _maybe_start_auto_review(self):
        if self.auto_next_pending and self.pending_analyze == 0:
            self.auto_next_pending = False
            self.open_error_check(auto_next=True)

    def _advance_room(self):
        current_idx = self.cb_room.currentIndex()
        if current_idx < self.cb_room.count() - 1:
            self.cb_room.setCurrentIndex(current_idx + 1)
            # currentTextChanged 시그널로 라벨 자동 갱신
            self.lbl_cur_room.setText(self.cb_room.currentText())

