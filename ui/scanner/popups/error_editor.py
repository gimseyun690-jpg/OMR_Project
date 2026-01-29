# -*- coding: utf-8 -*-
import cv2
from PySide2.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QHeaderView,
    QSplitter,
    QCheckBox,
    QWidget,
    QAbstractItemView,
    QFrame,
    QMessageBox,
    QScrollArea,
)
from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QPixmap, QImage, QColor, QFont


class ErrorCorrectionDialog(QDialog):
    # 메인 윈도우에 "다음/이전 결과 보기" 요청하는 시그널
    request_next = Signal()
    request_prev = Signal()

    def __init__(self, parent=None, image_cv=None, scan_results=None, image_path=""):
        super().__init__(parent)
        self.setWindowTitle("판독결과 조회/수정")

        # 윈도우 설정
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.resize(1600, 900)
        self.setFont(QFont("Malgun Gothic", 10))

        self.image_cv = image_cv
        self.scan_results = scan_results  # 리스트 형태 [{'q_num':1, 'marked':[0], 'status':'정상'}...]
        self.image_path = image_path
        self.exit_code = 0
        self._split_threshold = 20
        self._left_map = []
        self._mid_map = []
        self._right_map = []
        self.zoom_factor = 1.0
        self._orig_pixmap = None

        self.init_ui()
        self.connect_signals()  # 버튼 기능 연결
        self.setSizeGripEnabled(True)

        self.load_data()

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # [1] 상단 카드
        top_panel = QFrame()
        top_panel.setObjectName("topPanel")
        top_panel.setFixedHeight(110)
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        # (1-1) 오류 진행 카드
        card_idx = QFrame()
        card_idx.setObjectName("card")
        card_idx.setMinimumWidth(160)
        v_idx = QVBoxLayout(card_idx)
        v_idx.setContentsMargins(12, 10, 12, 10)
        v_idx.setSpacing(6)
        lbl_idx_title = QLabel("오류 진행")
        lbl_idx_title.setObjectName("cardTitle")
        self.lbl_idx = QLabel("1/1")
        self.lbl_idx.setObjectName("progressValue")
        self.lbl_idx.setAlignment(Qt.AlignCenter)
        lbl_idx_hint = QLabel("현재/전체")
        lbl_idx_hint.setObjectName("progressHint")
        lbl_idx_hint.setAlignment(Qt.AlignCenter)
        v_idx.addWidget(lbl_idx_title, 0, Qt.AlignLeft)
        v_idx.addWidget(self.lbl_idx)
        v_idx.addWidget(lbl_idx_hint)
        top_layout.addWidget(card_idx)

        # (1-2) 이동/검색 카드
        card_nav = QFrame()
        card_nav.setObjectName("card")
        card_nav.setMinimumWidth(260)
        v_nav = QVBoxLayout(card_nav)
        v_nav.setContentsMargins(12, 10, 12, 10)
        v_nav.setSpacing(8)
        lbl_nav_title = QLabel("이동/검색")
        lbl_nav_title.setObjectName("cardTitle")
        v_nav.addWidget(lbl_nav_title, 0, Qt.AlignLeft)
        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        self.btn_prev = QPushButton("이전 항목")
        self.btn_next = QPushButton("다음 항목")
        nav_row.addWidget(self.btn_prev)
        nav_row.addWidget(self.btn_next)
        v_nav.addLayout(nav_row)
        top_layout.addWidget(card_nav)

        # (1-3) 일괄 처리 카드
        card_batch = QFrame()
        card_batch.setObjectName("card")
        card_batch.setMinimumWidth(320)
        v_batch = QVBoxLayout(card_batch)
        v_batch.setContentsMargins(12, 10, 12, 10)
        v_batch.setSpacing(8)
        lbl_batch_title = QLabel("일괄 처리")
        lbl_batch_title.setObjectName("cardTitle")
        v_batch.addWidget(lbl_batch_title, 0, Qt.AlignLeft)
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)
        self.btn_all_agree = QPushButton("전체 찬성 처리 (1)")
        self.btn_all_disagree = QPushButton("전체 반대 처리 (2)")
        batch_row.addWidget(self.btn_all_agree)
        batch_row.addWidget(self.btn_all_disagree)
        v_batch.addLayout(batch_row)
        top_layout.addWidget(card_batch)

        # (1-4) 저장 카드
        card_save = QFrame()
        card_save.setObjectName("cardPrimary")
        card_save.setMinimumWidth(240)
        v_save = QVBoxLayout(card_save)
        v_save.setContentsMargins(12, 10, 12, 10)
        v_save.setSpacing(6)
        lbl_save_title = QLabel("저장")
        lbl_save_title.setObjectName("cardTitle")
        self.btn_save = QPushButton("확인/저장 후 다음 (S)")
        self.btn_save.setObjectName("primaryButton")
        self.btn_save.setFixedHeight(40)
        v_save.addWidget(lbl_save_title, 0, Qt.AlignLeft)
        v_save.addWidget(self.btn_save)
        top_layout.addWidget(card_save)

        main_layout.addWidget(top_panel)

        # [2] 중앙 작업 영역
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ccc; }")
        self.main_splitter = splitter

        # 좌측: 이미지
        frame_left = QFrame()
        frame_left.setObjectName("imagePanel")
        layout_left = QVBoxLayout(frame_left)
        layout_left.setContentsMargins(0, 0, 0, 0)

        self.lbl_info = QLabel(f"  현재 파일명: {self.image_path}")
        self.lbl_info.setFixedHeight(30)
        self.lbl_info.setObjectName("imageInfo")
        layout_left.addWidget(self.lbl_info)

        self.lbl_image = _ImageLabel(self)
        self.lbl_image.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidget(self.lbl_image)
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setFrameShape(QFrame.NoFrame)
        self.image_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.image_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout_left.addWidget(self.image_scroll)
        splitter.addWidget(frame_left)

        # 우측: 판독결과(문항 분할)
        frame_right = QWidget()
        layout_right = QVBoxLayout(frame_right)
        layout_right.setContentsMargins(0, 0, 0, 0)
        layout_right.setSpacing(6)
        right_splitter = QSplitter(Qt.Vertical)

        self._tables_splitter = QSplitter(Qt.Horizontal)
        self.table_left = self._create_table()
        self.table_mid = self._create_table()
        self.table_right = self._create_table()
        self.table_mid.setVisible(False)
        self.table_right.setVisible(False)
        self._tables_splitter.addWidget(self.table_left)
        self._tables_splitter.addWidget(self.table_mid)
        self._tables_splitter.addWidget(self.table_right)
        self._tables_splitter.setSizes([1, 1, 1])
        right_splitter.addWidget(self._tables_splitter)

        self.lbl_log = QLabel()
        self.lbl_log.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_log.setObjectName("logPanel")
        self.lbl_log.setText("오류 내용 확인 중...")
        right_splitter.addWidget(self.lbl_log)
        right_splitter.setSizes([600, 200])
        layout_right.addWidget(right_splitter)

        splitter.addWidget(frame_right)
        splitter.setSizes([700, 500])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        self.setStyleSheet(
            """
            QDialog { background: #F7F9FC; }
            #topPanel { background: transparent; }
            #card {
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
            }
            #cardPrimary {
                background: #F0F6FF;
                border: 1px solid rgba(37, 99, 235, 0.35);
                border-radius: 12px;
            }
            #cardTitle { color: #5B6775; font-weight: 600; font-size: 12px; }
            #progressValue { color: #2563EB; font-size: 26px; font-weight: 700; }
            #progressHint { color: #8B95A1; font-size: 11px; }
            QPushButton {
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #F2F6FF; border-color: rgba(37, 99, 235, 0.4); }
            QPushButton#primaryButton {
                background: #2563EB;
                color: #FFFFFF;
                border: 1px solid #1D4ED8;
            }
            QPushButton#primaryButton:hover { background: #1D4ED8; }
            #imagePanel { background: #1F2937; border-radius: 12px; }
            #imageInfo { background: #111827; color: #E5E7EB; font-weight: 600; padding: 6px 10px; }
            #logPanel {
                background: #FFFFFF;
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                padding: 10px;
                color: #B91C1C;
                font-weight: 600;
                font-size: 13px;
            }
        """
        )

    def _create_table(self):
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["문항", "찬성(1)", "반대(2)"])
        table.verticalHeader().setVisible(False)
        table.setStyleSheet(
            """
            QHeaderView::section {
                background-color: #F1F5F9; padding: 6px; border: 1px solid #E2E8F0;
                font-weight: bold; font-size: 13px; color: #0F172A;
            }
            QTableWidget {
                gridline-color: #E5E7EB; font-size: 13px; selection-background-color: #D1E8FF; selection-color: black;
                background: #FFFFFF; border: 1px solid rgba(0,0,0,0.08); border-radius: 12px;
            }
        """
        )
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        return table

    def _fill_table(self, table, indices):
        table.setRowCount(len(indices))
        for row, idx in enumerate(indices):
            data = self.scan_results[idx]

            item_no = QTableWidgetItem(str(data["q_num"]))
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setFlags(item_no.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, item_no)

            chk_agree = QCheckBox()
            chk_disagree = QCheckBox()
            chk_agree.setStyleSheet("QCheckBox::indicator { width: 20px; height: 20px; }")
            chk_disagree.setStyleSheet("QCheckBox::indicator { width: 20px; height: 20px; }")

            if 0 in data["marked"]:
                chk_agree.setChecked(True)
            if 1 in data["marked"]:
                chk_disagree.setChecked(True)

            chk_agree.clicked.connect(lambda checked, r=idx: self.on_checkbox_click(r, 0, checked))
            chk_disagree.clicked.connect(
                lambda checked, r=idx: self.on_checkbox_click(r, 1, checked)
            )

            w1 = QWidget()
            l1 = QHBoxLayout(w1)
            l1.addWidget(chk_agree)
            l1.setAlignment(Qt.AlignCenter)
            l1.setContentsMargins(0, 0, 0, 0)
            w2 = QWidget()
            l2 = QHBoxLayout(w2)
            l2.addWidget(chk_disagree)
            l2.setAlignment(Qt.AlignCenter)
            l2.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 1, w1)
            table.setCellWidget(row, 2, w2)

            status = data["status"]
            if status != "정상":
                bg_color = QColor(255, 255, 255)
                txt_color = QColor(0, 0, 0)
                if status == "중복":
                    bg_color = QColor(0, 0, 255)
                    txt_color = QColor(255, 255, 255)
                elif status == "공백":
                    bg_color = QColor(255, 200, 200)
                    txt_color = QColor(255, 0, 0)
                item_no.setBackground(bg_color)
                item_no.setForeground(txt_color)

    def _get_active_table(self):
        if self.table_right.isVisible() and self.table_right.hasFocus():
            return self.table_right, self._right_map
        if self.table_mid.isVisible() and self.table_mid.hasFocus():
            return self.table_mid, self._mid_map
        return self.table_left, self._left_map

    def _select_global_index(self, idx):
        if idx is None:
            return
        if idx in self._left_map:
            row = self._left_map.index(idx)
            self.table_left.selectRow(row)
            self.table_left.setFocus()
        elif idx in self._mid_map:
            row = self._mid_map.index(idx)
            self.table_mid.selectRow(row)
            self.table_mid.setFocus()
        elif idx in self._right_map:
            row = self._right_map.index(idx)
            self.table_right.selectRow(row)
            self.table_right.setFocus()

    def connect_signals(self):
        """버튼 기능 연결"""
        self.btn_save.clicked.connect(self.save_and_close)
        self.btn_prev.clicked.connect(self.on_prev)
        self.btn_next.clicked.connect(self.on_next)

        # 일괄 처리 버튼 연결
        self.btn_all_agree.clicked.connect(lambda: self.batch_process(0))  # 0: 찬성
        self.btn_all_disagree.clicked.connect(lambda: self.batch_process(1))  # 1: 반대

    def load_data(self):
        """데이터를 화면에 표시"""
        self.update_image()

        if not self.scan_results:
            return

        error_logs = []
        for data in self.scan_results:
            status = data.get("status")
            if status and status != "정상":
                error_logs.append(f"[{data['q_num']}번 문항] {status} 오류")

        total = len(self.scan_results)
        if total > 40:
            first = (total + 2) // 3
            second = (total - first + 1) // 2
            split_a = first
            split_b = first + second
        elif total > self._split_threshold:
            split_a = (total + 1) // 2
            split_b = total
        else:
            split_a = total
            split_b = total

        self._left_map = list(range(0, split_a))
        self._mid_map = list(range(split_a, split_b))
        self._right_map = list(range(split_b, total))

        self.table_left.setRowCount(0)
        self.table_mid.setRowCount(0)
        self.table_right.setRowCount(0)
        self._fill_table(self.table_left, self._left_map)

        if self._right_map:
            self.table_mid.setVisible(True)
            self.table_right.setVisible(True)
            self._fill_table(self.table_mid, self._mid_map)
            self._fill_table(self.table_right, self._right_map)
            self._tables_splitter.setSizes([1, 1, 1])
        elif self._mid_map:
            self.table_mid.setVisible(True)
            self.table_right.setVisible(False)
            self._fill_table(self.table_mid, self._mid_map)
            self._tables_splitter.setSizes([1, 1, 0])
        else:
            self.table_mid.setVisible(False)
            self.table_right.setVisible(False)
            self._tables_splitter.setSizes([1, 0, 0])

        if self._left_map:
            self.table_left.selectRow(0)

        if error_logs:
            self.lbl_log.setText("오류 내용:\n" + "\n".join(error_logs))
        else:
            self.lbl_log.setText("모든 문항이 정상입니다.")
            self.lbl_log.setStyleSheet(
                "background-color: #E8F5E9; border-top: 2px solid #4CAF50; "
                "padding: 10px; color: #2E7D32; font-weight: bold; font-size: 13px;"
            )

    def wheelEvent(self, event):
        if self.image_scroll.underMouse():
            delta = event.angleDelta().y()
            step = 10 if delta > 0 else -10
            self._apply_wheel_zoom(step)
            event.accept()
            return
        super().wheelEvent(event)

    def _apply_wheel_zoom(self, step):
        factor = 1.1 if step > 0 else 0.9
        self.zoom_factor = max(0.5, min(3.0, self.zoom_factor * factor))
        self._render_image()

    def _start_pan(self, event):
        self._panning = True
        self._pan_start = event.pos()
        self._pan_h_start = self.image_scroll.horizontalScrollBar().value()
        self._pan_v_start = self.image_scroll.verticalScrollBar().value()
        self.lbl_image.setCursor(Qt.ClosedHandCursor)

    def _move_pan(self, event):
        if not getattr(self, "_panning", False):
            return
        delta = event.pos() - self._pan_start
        self.image_scroll.horizontalScrollBar().setValue(self._pan_h_start - delta.x())
        self.image_scroll.verticalScrollBar().setValue(self._pan_v_start - delta.y())

    def _end_pan(self):
        self._panning = False
        self.lbl_image.setCursor(Qt.OpenHandCursor)

    def on_checkbox_click(self, row, col_type, checked):
        """체크박스를 클릭하면 실제 데이터(self.scan_results)를 업데이트"""
        target_list = self.scan_results[row]["marked"]

        # 체크
        if checked:
            if col_type not in target_list:
                target_list.append(col_type)
        # 체크 해제
        else:
            if col_type in target_list:
                target_list.remove(col_type)

        target_list.sort()  # 정렬

        # 상태 판정(정상/중복/공백)
        if len(target_list) == 0:
            self.scan_results[row]["status"] = "공백"
        elif len(target_list) == 1:
            self.scan_results[row]["status"] = "정상"
        else:
            self.scan_results[row]["status"] = "중복"

        # (선택사항) 상태가 변경되면 테이블 표시를 갱신
        # self.load_data()

    def batch_process(self, target_val):
        """일괄 처리 로직"""
        # 모든 데이터 수정
        for data in self.scan_results:
            data["marked"] = [target_val]  # [0] 또는 [1]로 넣기
            data["status"] = "정상"  # 강제 정상 처리

        # 화면 로그 갱신
        self.load_data()
        QMessageBox.information(self, "알림", "일괄 처리가 완료되었습니다.")

    def keyPressEvent(self, event):
        """키보드 단축키 처리"""
        key = event.key()

        table, mapping = self._get_active_table()
        if not mapping:
            return

        current_row = table.currentRow()
        if current_row < 0:
            current_row = 0
            table.selectRow(0)

        try:
            global_idx = mapping[current_row]
        except Exception:
            global_idx = None

        next_idx = None

        if key == Qt.Key_1 and global_idx is not None:
            self.scan_results[global_idx]["marked"] = [0]
            self.scan_results[global_idx]["status"] = "정상"
            next_idx = global_idx + 1
            self.load_data()
            self._select_global_index(next_idx)

        elif key == Qt.Key_2 and global_idx is not None:
            self.scan_results[global_idx]["marked"] = [1]
            self.scan_results[global_idx]["status"] = "정상"
            next_idx = global_idx + 1
            self.load_data()
            self._select_global_index(next_idx)

        elif key == Qt.Key_S:
            self.save_and_close()

        else:
            super().keyPressEvent(event)

    # =========================================================
    # 저장/이동 버튼 처리: exit_code 설정 후 메인에 전달
    # =========================================================
    def save_and_close(self):
        """저장(S) 버튼"""
        self.exit_code = 1  # 1 = 저장하고 다음으로
        self.accept()  # 창 닫기

    def on_prev(self):
        """이전 버튼"""
        self.exit_code = 2  # 2 = 저장하지 않고 이전으로
        self.request_prev.emit()  # (선택) 시그널 전달
        self.accept()  # 창 닫기

    def on_next(self):
        """다음 버튼"""
        self.exit_code = 3  # 3 = 저장하지 않고 다음으로
        self.request_next.emit()  # (선택) 시그널 전달
        self.accept()  # 창 닫기

    def update_image(self):
        if self.image_cv is not None:
            try:
                h, w, ch = self.image_cv.shape
                bytes_per_line = ch * w
                rgb_img = cv2.cvtColor(self.image_cv, cv2.COLOR_BGR2RGB)
                q_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self._orig_pixmap = QPixmap.fromImage(q_img)
                self._render_image()
            except Exception:
                pass

    def _render_image(self):
        if not self._orig_pixmap:
            return
        viewport = self.image_scroll.viewport()
        target_h = viewport.height()
        if target_h <= 0:
            return
        scaled_h = max(1, int(target_h * self.zoom_factor))
        scaled = self._orig_pixmap.scaledToHeight(scaled_h, Qt.SmoothTransformation)
        self.lbl_image.setPixmap(scaled)
        self._adjust_left_panel_width(scaled)

    def _adjust_left_panel_width(self, pixmap: QPixmap):
        if not hasattr(self, "main_splitter") or pixmap.isNull():
            return
        total_w = self.main_splitter.width()
        if total_w <= 0:
            return
        right_min = 420
        viewport = self.image_scroll.viewport()
        h = viewport.height()
        if h <= 0:
            return
        aspect = pixmap.width() / max(pixmap.height(), 1)
        desired = int(h * aspect)
        desired = max(360, min(total_w - right_min, desired))
        if desired > 0 and total_w - desired > 0:
            self.main_splitter.setSizes([desired, total_w - desired])

    def resizeEvent(self, event):
        self._render_image()
        super().resizeEvent(event)


class _ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner = parent
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._owner is not None:
            self._owner._start_pan(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._owner is not None:
            self._owner._move_pan(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._owner is not None:
            self._owner._end_pan()
            event.accept()
            return
        super().mouseReleaseEvent(event)
