from PySide2.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QVBoxLayout,
    QLabel,
    QGroupBox,
    QComboBox,
    QCheckBox,
)
from PySide2.QtCore import Qt

from ui.scanner.components.styles import LABEL, BLUE_NUM, RED_NUM, BLUE_LABEL, COMBO
from logic.form_loader import list_forms


class ScannerStatusPanel(QWidget):
    """상단 상태/설정 패널 묶음 위젯."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._forms = []
        self._init_ui()

    def _init_ui(self):
        top_frame = QFrame()
        top_frame.setFixedHeight(140)
        top_frame.setStyleSheet("background-color: #F0F0F0; border-bottom: 1px solid #A0A0A0;")

        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(5, 5, 5, 5)
        top_layout.setSpacing(10)

        # (1) 좌측: 카운트 그룹
        grp_cnt = QGroupBox()
        grp_cnt.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_cnt = QGridLayout(grp_cnt)
        grid_cnt.setContentsMargins(5, 5, 5, 5)
        grid_cnt.setVerticalSpacing(0)

        grid_cnt.addWidget(QLabel("총판독매수", styleSheet=LABEL), 0, 0, alignment=Qt.AlignCenter)
        grid_cnt.addWidget(QLabel("총점검매수", styleSheet=LABEL), 0, 1, alignment=Qt.AlignCenter)

        self.lbl_total = QLabel("0", styleSheet=BLUE_NUM)
        grid_cnt.addWidget(self.lbl_total, 1, 0, alignment=Qt.AlignCenter)

        self.lbl_check = QLabel("0", styleSheet=RED_NUM)
        grid_cnt.addWidget(self.lbl_check, 1, 1, alignment=Qt.AlignCenter)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #ccc;")
        grid_cnt.addWidget(line, 2, 0, 1, 2)

        lbl_cur_title = QLabel("현재 고사장/시험실/판독매수", styleSheet="font-size:10px; font-weight:bold; color:#555; border:none;")
        grid_cnt.addWidget(lbl_cur_title, 3, 0, 1, 2)

        sub_layout = QGridLayout()
        sub_layout.addWidget(QLabel("현재 고사장:", styleSheet="font-size:11px; border:none;"), 0, 0)
        self.lbl_cur_place = QLabel("스캐너1", styleSheet="color:blue; font-weight:bold; border:none;")
        sub_layout.addWidget(self.lbl_cur_place, 0, 1)

        sub_layout.addWidget(QLabel("현재 시험실:", styleSheet="font-size:11px; border:none;"), 1, 0)
        self.lbl_cur_room = QLabel("1", styleSheet="color:blue; font-weight:bold; font-size:14px; border:none;")
        sub_layout.addWidget(self.lbl_cur_room, 1, 1)

        sub_layout.addWidget(QLabel("현재 판독매수", styleSheet="font-size:11px; border:none;"), 0, 2, 2, 1)
        self.lbl_cur_cnt = QLabel("0", styleSheet="color:red; font-weight:bold; font-size:18px; border:none;")
        sub_layout.addWidget(self.lbl_cur_cnt, 0, 3, 2, 1)

        grid_cnt.addLayout(sub_layout, 4, 0, 1, 2)

        self.lbl_review_detail = QLabel("오류:0  중복:0  공백:0  명단미매칭:0  결시:0")
        self.lbl_review_detail.setStyleSheet("font-size:10px; color:#666; border:none;")
        self.lbl_review_detail.setAlignment(Qt.AlignCenter)
        grid_cnt.addWidget(self.lbl_review_detail, 5, 0, 1, 2)

        # (2) 중앙: 설정
        grp_set = QGroupBox()
        grp_set.setStyleSheet("background-color: white; border: 1px solid #999; border-radius: 3px;")
        grid_set = QGridLayout(grp_set)

        self.cb_form = QComboBox()
        self.cb_form.setStyleSheet(COMBO)

        self._forms = list_forms()
        if not self._forms:
            self.cb_form.addItem("없음 (resources/forms)", userData=None)
        else:
            for form_id, display, path in self._forms:
                self.cb_form.addItem(display, userData=path)

        self.cb_place = QComboBox()
        self.cb_place.setStyleSheet(COMBO)
        for i in range(1, 11):
            self.cb_place.addItem(f"스캐너{i}")

        self.cb_room = QComboBox()
        self.cb_room.setStyleSheet(COMBO)
        for i in range(1, 1000):
            self.cb_room.addItem(str(i))

        grid_set.addWidget(QLabel("스캔 OMR 양식 :", styleSheet=BLUE_LABEL), 0, 0)
        grid_set.addWidget(self.cb_form, 0, 1)
        grid_set.addWidget(QLabel("판독 고사장:", styleSheet="font-weight:bold; border:none;"), 1, 0)
        grid_set.addWidget(self.cb_place, 1, 1)
        grid_set.addWidget(QLabel("판독 시험실:", styleSheet="font-weight:bold; border:none;"), 2, 0)
        grid_set.addWidget(self.cb_room, 2, 1)

        # (3) 우측: 오류처리/필터
        grp_err = QGroupBox("오류처리")
        grp_err.setStyleSheet(
            "QGroupBox { background-color: white; border: 1px solid #999; font-size: 11px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; padding: 0 6px; }"
        )
        grp_err.setMinimumWidth(260)
        grid_err = QGridLayout(grp_err)
        self.cb_err_opt = QComboBox()
        self.cb_err_opt.addItem("이미지 오류(미리보기/읽기오류 스캔완료보류)")
        self.cb_stop_opt = QComboBox()
        self.cb_stop_opt.addItem("모든 오류 스캔중단")
        grid_err.addWidget(QLabel("스캔중 오류처리 보기 :", styleSheet="border:none;"), 0, 0)
        grid_err.addWidget(self.cb_err_opt, 0, 1)
        grid_err.addWidget(QLabel("오류발생시 스캔중단 :", styleSheet="border:none;"), 1, 0)
        grid_err.addWidget(self.cb_stop_opt, 1, 1)

        grp_chk = QGroupBox("오류필터")
        grp_chk.setStyleSheet(
            "QGroupBox { background-color: white; border: 1px solid #999; font-size: 11px; padding-top: 10px; }"
            "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; padding: 0 6px; }"
        )
        grp_chk.setMinimumWidth(150)
        v_chk = QVBoxLayout(grp_chk)
        self.chk_all_blank = QCheckBox("전체공백 무효처리")
        self.chk_etc_error = QCheckBox("기타 무효처리")
        self.chk_all_blank.setChecked(True)
        self.chk_etc_error.setChecked(True)
        v_chk.addWidget(self.chk_all_blank)
        v_chk.addWidget(self.chk_etc_error)

        top_layout.addWidget(grp_cnt, 14)
        top_layout.addWidget(grp_set, 34)
        top_layout.addWidget(grp_err, 28)
        top_layout.addWidget(grp_chk, 14)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(top_frame)
