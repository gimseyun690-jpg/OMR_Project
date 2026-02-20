# -*- coding: utf-8 -*-
import cv2
import numpy as np
from typing import List, Optional, Sequence, Tuple

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QColor, QFont, QImage, QPixmap
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BaseErrorCorrectionDialog(QDialog):
    request_next = Signal()
    request_prev = Signal()

    def __init__(
        self,
        parent=None,
        image_cv=None,
        scan_results=None,
        image_path: str = "",
        title: str = "판독결과 조회/수정",
        choice_labels: Optional[Sequence[str]] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(str(title))

        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.resize(1600, 900)
        self.setFont(QFont("Malgun Gothic", 10))

        self.image_cv = image_cv
        self.scan_results = list(scan_results or [])
        self.image_path = image_path
        labels = [str(v).strip() for v in (choice_labels or ["찬성", "반대"])]
        labels = [v for v in labels if v]
        if not labels:
            labels = ["1", "2"]
        self.choice_labels = labels[:9]
        self.choice_count = len(self.choice_labels)

        self.exit_code = 0
        self._split_threshold = 20
        self._left_map: List[int] = []
        self._mid_map: List[int] = []
        self._right_map: List[int] = []
        self.batch_buttons: List[QPushButton] = []
        self.zoom_factor = 1.0
        self._orig_pixmap = None
        self._warp_pixmap = None
        self._show_warped = True

        self.init_ui()
        self.connect_signals()
        self.setSizeGripEnabled(True)
        self.load_data()

    def _header_label_for_choice(self, idx: int) -> str:
        label = self.choice_labels[idx]
        if label == str(idx + 1):
            return label
        return f"{label}({idx + 1})"

    @staticmethod
    def _normalize_status(status: str) -> str:
        raw = str(status or "").strip().lower()
        if raw in ("정상", "normal", "ok"):
            return "정상"
        if raw in ("중복", "duplicate", "dup"):
            return "중복"
        if raw in ("공백", "공란", "blank", "empty"):
            return "공백"
        return str(status or "")

    def init_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        top_panel = QFrame()
        top_panel.setObjectName("topPanel")
        top_panel.setFixedHeight(110)
        top_layout = QHBoxLayout(top_panel)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

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

        card_batch = QFrame()
        card_batch.setObjectName("card")
        card_batch.setMinimumWidth(360)
        v_batch = QVBoxLayout(card_batch)
        v_batch.setContentsMargins(12, 10, 12, 10)
        v_batch.setSpacing(8)
        batch_title = "일괄 처리"
        if self.choice_count > 2:
            batch_title = f"일괄 처리 ({self.choice_count}지선다)"
        lbl_batch_title = QLabel(batch_title)
        lbl_batch_title.setObjectName("cardTitle")
        v_batch.addWidget(lbl_batch_title, 0, Qt.AlignLeft)
        batch_row = QHBoxLayout()
        batch_row.setSpacing(6)
        self.batch_buttons = []
        for idx, label in enumerate(self.choice_labels):
            text = f"전체 {label} ({idx + 1})" if self.choice_count <= 2 else f"전체 {label}"
            btn = QPushButton(text)
            btn.setMinimumWidth(80)
            self.batch_buttons.append(btn)
            batch_row.addWidget(btn)
        v_batch.addLayout(batch_row)
        top_layout.addWidget(card_batch)

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

        card_view = QFrame()
        card_view.setObjectName("card")
        card_view.setMinimumWidth(200)
        v_view = QVBoxLayout(card_view)
        v_view.setContentsMargins(12, 10, 12, 10)
        v_view.setSpacing(6)
        lbl_view_title = QLabel("보기 옵션")
        lbl_view_title.setObjectName("cardTitle")
        self.chk_show_warped = QCheckBox("정렬된 이미지 보기")
        self.chk_show_warped.setChecked(True)
        v_view.addWidget(lbl_view_title, 0, Qt.AlignLeft)
        v_view.addWidget(self.chk_show_warped)
        top_layout.addWidget(card_view)

        main_layout.addWidget(top_panel)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #ccc; }")
        self.main_splitter = splitter

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
        splitter.setSizes([520, 900])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

        self.setStyleSheet(
            """
            QDialog { background: #F7F9FC; }
            #topPanel { background: #FFFFFF; }
            #card {
                background: #FFFFFF;
                border: 1px solid #E1E7EE;
                border-radius: 12px;
            }
            #cardPrimary {
                background: #F0F6FF;
                border: 1px solid #8FB0F3;
                border-radius: 12px;
            }
            #cardTitle { color: #5B6775; font-weight: 600; font-size: 12px; }
            #progressValue { color: #2563EB; font-size: 26px; font-weight: 700; }
            #progressHint { color: #8B95A1; font-size: 11px; }
            QPushButton {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #F2F6FF; border-color: #8FB0F3; }
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
                border: 1px solid #E1E7EE;
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
        table.setColumnCount(1 + self.choice_count)
        headers = ["문항"] + [self._header_label_for_choice(i) for i in range(self.choice_count)]
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet(
            """
            QHeaderView::section {
                background-color: #F1F5F9; padding: 6px; border: 1px solid #E2E8F0;
                font-weight: bold; font-size: 13px; color: #0F172A;
            }
            QTableWidget {
                gridline-color: #E5E7EB; font-size: 13px; selection-background-color: #D1E8FF; selection-color: black;
                background: #FFFFFF; border: 1px solid #E1E7EE; border-radius: 12px;
            }
        """
        )
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for col in range(1, 1 + self.choice_count):
            header.setSectionResizeMode(col, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        return table

    def _fill_table(self, table, indices):
        table.setRowCount(len(indices))
        for row, idx in enumerate(indices):
            data = self.scan_results[idx]

            item_no = QTableWidgetItem(str(data.get("q_num", idx + 1)))
            item_no.setTextAlignment(Qt.AlignCenter)
            item_no.setFlags(item_no.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, item_no)

            marked = data.get("marked", [])
            if not isinstance(marked, list):
                marked = []

            for choice_idx in range(self.choice_count):
                chk = QCheckBox()
                chk.setStyleSheet("QCheckBox::indicator { width: 20px; height: 20px; }")
                chk.setChecked(choice_idx in marked)
                chk.clicked.connect(
                    lambda checked, r=idx, c=choice_idx: self.on_checkbox_click(r, c, checked)
                )
                wrapper = QWidget()
                wrapper_layout = QHBoxLayout(wrapper)
                wrapper_layout.addWidget(chk)
                wrapper_layout.setAlignment(Qt.AlignCenter)
                wrapper_layout.setContentsMargins(0, 0, 0, 0)
                table.setCellWidget(row, 1 + choice_idx, wrapper)

            status = self._normalize_status(data.get("status", ""))
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
        self.btn_save.clicked.connect(self.save_and_close)
        self.btn_prev.clicked.connect(self.on_prev)
        self.btn_next.clicked.connect(self.on_next)
        self.chk_show_warped.toggled.connect(self._on_toggle_warped)
        for idx, btn in enumerate(self.batch_buttons):
            btn.clicked.connect(lambda _checked=False, c=idx: self.batch_process(c))

    def load_data(self):
        self.update_image()
        if not self.scan_results:
            return

        error_logs = []
        for data in self.scan_results:
            status = self._normalize_status(data.get("status", ""))
            if status and status != "정상":
                error_logs.append(f"[{data.get('q_num', '?')}번 문항] {status} 오류")

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
            self.lbl_log.setStyleSheet("")
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
        target_list = self.scan_results[row].setdefault("marked", [])
        if checked:
            if col_type not in target_list:
                target_list.append(col_type)
        else:
            if col_type in target_list:
                target_list.remove(col_type)
        target_list.sort()

        if len(target_list) == 0:
            self.scan_results[row]["status"] = "공백"
        elif len(target_list) == 1:
            self.scan_results[row]["status"] = "정상"
        else:
            self.scan_results[row]["status"] = "중복"

    def batch_process(self, target_val):
        if target_val < 0 or target_val >= self.choice_count:
            return
        for data in self.scan_results:
            data["marked"] = [target_val]
            data["status"] = "정상"
        self.load_data()
        QMessageBox.information(self, "알림", "일괄 처리가 완료되었습니다.")

    def keyPressEvent(self, event):
        key = event.key()
        table, mapping = self._get_active_table()
        if not mapping:
            super().keyPressEvent(event)
            return

        current_row = table.currentRow()
        if current_row < 0:
            current_row = 0
            table.selectRow(0)

        global_idx = None
        try:
            global_idx = mapping[current_row]
        except Exception:
            pass

        pressed_choice = None
        if Qt.Key_1 <= key <= Qt.Key_9:
            pressed_choice = int(key - Qt.Key_1)

        if (
            global_idx is not None
            and pressed_choice is not None
            and 0 <= pressed_choice < self.choice_count
        ):
            self.scan_results[global_idx]["marked"] = [pressed_choice]
            self.scan_results[global_idx]["status"] = "정상"
            next_idx = global_idx + 1
            self.load_data()
            self._select_global_index(next_idx)
            return

        if key == Qt.Key_S:
            self.save_and_close()
            return

        super().keyPressEvent(event)

    def save_and_close(self):
        self.exit_code = 1
        self.accept()

    def on_prev(self):
        self.exit_code = 2
        self.request_prev.emit()
        self.accept()

    def on_next(self):
        self.exit_code = 3
        self.request_next.emit()
        self.accept()

    def update_image(self):
        base_img = None
        if self.image_path:
            try:
                img_array = np.fromfile(self.image_path, np.uint8)
                base_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                print(f"[ErrorCorrectionDialog] base image load failed: {e}")
                base_img = None

        if self.image_cv is not None or base_img is not None:
            try:
                if base_img is not None:
                    self._orig_pixmap = self._cv_to_pixmap(base_img)
                self._warp_pixmap = self._cv_to_pixmap(self.image_cv) if self.image_cv is not None else None
                self._render_image()
            except Exception as e:
                print(f"[ErrorCorrectionDialog] update_image failed: {e}")
                self.lbl_log.setText("이미지 표시 중 오류가 발생했습니다.")
        else:
            self.lbl_log.setText("이미지 로드 실패: 경로를 확인해주세요.")

    def _cv_to_pixmap(self, img_cv):
        if img_cv is None:
            return QPixmap()
        if not hasattr(img_cv, "shape") or len(img_cv.shape) < 2:
            return QPixmap()
        h, w = img_cv.shape[:2]
        if h <= 0 or w <= 0:
            return QPixmap()
        # Large source images can spike memory during QPixmap creation; cap display size safely.
        max_side = 3200
        if max(h, w) > max_side:
            scale = float(max_side) / float(max(h, w))
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img_cv = cv2.resize(img_cv, (new_w, new_h), interpolation=cv2.INTER_AREA)
            h, w = img_cv.shape[:2]
        rgb_img = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        rgb_img = np.ascontiguousarray(rgb_img)
        bytes_per_line = rgb_img.shape[1] * rgb_img.shape[2]
        q_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        q_img = q_img.copy()
        return QPixmap.fromImage(q_img)

    def _render_image(self):
        pixmap = self._get_active_pixmap()
        if not pixmap:
            return
        viewport = self.image_scroll.viewport()
        target_h = viewport.height()
        if target_h <= 0:
            return
        scaled_h = max(1, int(target_h * self.zoom_factor))
        try:
            scaled = pixmap.scaledToHeight(scaled_h, Qt.SmoothTransformation)
            self.lbl_image.setPixmap(scaled)
            self._adjust_left_panel_width(scaled)
        except Exception as e:
            print(f"[ErrorCorrectionDialog] render failed: {e}")
            self.lbl_log.setText("이미지 렌더링 중 오류가 발생했습니다.")

    def _adjust_left_panel_width(self, pixmap: QPixmap):
        if not hasattr(self, "main_splitter") or pixmap.isNull():
            return
        total_w = self.main_splitter.width()
        if total_w <= 0:
            return

        viewport = self.image_scroll.viewport()
        h = viewport.height()
        if h <= 0:
            return

        right_min = max(580, int(total_w * 0.52))
        max_left = max(320, total_w - right_min)
        aspect = pixmap.width() / max(pixmap.height(), 1)
        desired = int(h * aspect)
        desired = max(320, min(max_left, desired))

        if desired > 0 and total_w - desired > 0:
            self.main_splitter.setSizes([desired, total_w - desired])

    def resizeEvent(self, event):
        self._render_image()
        super().resizeEvent(event)

    def _get_active_pixmap(self):
        if self._show_warped and self._warp_pixmap is not None:
            return self._warp_pixmap
        return self._orig_pixmap

    def _on_toggle_warped(self, checked):
        self._show_warped = bool(checked)
        self._render_image()


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
