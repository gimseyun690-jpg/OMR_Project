import os
from PySide2.QtCore import Qt, Signal, QPoint, QPointF, QSettings, QPropertyAnimation, QEasingCurve
from PySide2.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTabWidget,
    QMenu,
    QMessageBox,
    QCheckBox,
    QSlider,
    QGroupBox,
    QComboBox,
    QGraphicsDropShadowEffect,
)

from qfluentwidgets import (
    FluentWindow,
    NavigationItemPosition,
    FluentIcon as FIF,
    setTheme,
    Theme,
)

# 기존 화면 및 설정
from ui.settings.file_setting import FileSettingsDialog
from ui.scanner.scan_window import ScannerReadingView

# 결과 화면들
from ui.results.vote_count import VoteCountView
from ui.results.scan_data import ScanDataView
from ui.results.scan_stats import ScanStatsView
from ui.results.roster_input import RosterInputView
from ui.results.answer_input import AnswerInputView
from ui.results.unread_check import UnreadCheckView
from ui.results.scoring_calc import ScoringCalcView
from ui.results.scoring_result import ScoringResultView
from ui.results.site_status import SiteStatusView
from ui.results.type_status import TypeStatusView
from ui.results.item_analysis import ItemAnalysisView

# 설정 창들
from ui.settings.form_setting import FormSettingsDialog
from ui.settings.mark_setting import MarkSettingsDialog
from ui.settings.path_setting import PathSettingsDialog
from ui.settings.site_setting import SiteSettingsDialog
from ui.settings.coord_calibrator import CoordCalibratorDialog
from database import DBManager


def _icon(name, fallback=FIF.APPLICATION):
    return getattr(FIF, name, fallback)


def _icon_pixmap(icon, size=40):
    """FluentIcon -> QIcon -> QPixmap 안전 변환."""
    if hasattr(icon, "icon"):
        icon = icon.icon()
    return icon.pixmap(size, size)


class HomeCard(QWidget):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon):
        super().__init__()
        self.setObjectName("homeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(_icon_pixmap(icon, 40))
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("homeCardTitle")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("homeCardSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.icon_label, 0, Qt.AlignLeft)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addStretch(1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
            event.accept()
        super().mouseReleaseEvent(event)


class HoverGroupBox(QGroupBox):
    def __init__(self, title: str):
        super().__init__(title)
        self.setAttribute(Qt.WA_Hover, True)
        self._init_shadow()

    def _init_shadow(self):
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(8)
        self._shadow.setOffset(0, 1)
        self._shadow.setColor(Qt.black)
        self.setGraphicsEffect(self._shadow)

        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(160)
        self._shadow_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._offset_anim = QPropertyAnimation(self._shadow, b"offset", self)
        self._offset_anim.setDuration(160)
        self._offset_anim.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, event):
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(18)
        self._shadow_anim.start()

        self._offset_anim.stop()
        self._offset_anim.setStartValue(self._shadow.offset())
        self._offset_anim.setEndValue(QPointF(0, 4))
        self._offset_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow_anim.stop()
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(8)
        self._shadow_anim.start()

        self._offset_anim.stop()
        self._offset_anim.setStartValue(self._shadow.offset())
        self._offset_anim.setEndValue(QPointF(0, 1))
        self._offset_anim.start()
        super().leaveEvent(event)



class HomeInterface(QWidget):
    open_file_settings = Signal()
    open_coord_settings = Signal()
    open_env_settings = Signal(QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homeInterface")
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        title = QLabel("OMR 홈")
        title.setObjectName("homeTitle")

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)

        self.card_file = HomeCard(
            "파일 설정",
            "DB 생성/선택 및 프로젝트 파일 관리",
            _icon("FOLDER"),
        )
        self.card_coord = HomeCard(
            "좌표 설정",
            "OMR 좌표 캘리브레이션",
            _icon("EDIT"),
        )
        self.card_env = HomeCard(
            "환경 설정",
            "양식/기표/경로/고사장 설정",
            _icon("SETTING"),
        )

        self.card_file.clicked.connect(self.open_file_settings.emit)
        self.card_coord.clicked.connect(self.open_coord_settings.emit)
        self.card_env.clicked.connect(self._emit_env_menu)

        grid.addWidget(self.card_file, 0, 0)
        grid.addWidget(self.card_coord, 0, 1)
        grid.addWidget(self.card_env, 0, 2)

        root.addWidget(title)
        root.addLayout(grid)
        root.addStretch(1)

        self.setStyleSheet(
            "#homeTitle { font-size: 26px; font-weight: 600; }"
            "#homeCard { background: rgba(255, 255, 255, 0.9); "
            "border: 1px solid rgba(0, 0, 0, 0.08); border-radius: 16px; }"
            "#homeCard:hover { border-color: rgba(0, 120, 215, 0.7); "
            "background: rgba(235, 245, 255, 0.95); }"
            "#homeCardTitle { font-size: 18px; font-weight: 600; }"
            "#homeCardSubtitle { color: #666; }"
        )

    def _emit_env_menu(self):
        pos = self.card_env.mapToGlobal(self.card_env.rect().bottomLeft())
        self.open_env_settings.emit(pos)


class ScanInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scanInterface")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scanner_view = ScannerReadingView()
        layout.addWidget(self.scanner_view)


class ResultsInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsInterface")
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("데이터 조회 및 수정")
        title.setObjectName("resultsTitle")

        self.tabs = QTabWidget()

        self.vote_view = VoteCountView()
        self.data_view = ScanDataView()
        self.stats_view = ScanStatsView()
        self.roster_view = RosterInputView()
        self.answer_view = AnswerInputView()
        self.unread_view = UnreadCheckView()
        self.scoring_view = ScoringCalcView()
        self.scoring_result_view = ScoringResultView()
        self.site_status_view = SiteStatusView()
        self.type_status_view = TypeStatusView()
        self.item_analysis_view = ItemAnalysisView()

        self.tabs.addTab(self.vote_view, "투표 집계")
        self.tabs.addTab(self.data_view, "스캔 데이터")
        self.tabs.addTab(self.stats_view, "통계 분석")
        self.tabs.addTab(self.roster_view, "명단 입력")
        self.tabs.addTab(self.answer_view, "정답 입력")
        self.tabs.addTab(self.unread_view, "미판독 확인")
        self.tabs.addTab(self.scoring_view, "채점 계산")
        self.tabs.addTab(self.scoring_result_view, "채점 결과")
        self.tabs.addTab(self.site_status_view, "고사장 현황")
        self.tabs.addTab(self.type_status_view, "전형별 현황")
        self.tabs.addTab(self.item_analysis_view, "문항 분석")

        root.addWidget(title)
        root.addWidget(self.tabs, 1)

        self.setStyleSheet("#resultsTitle { font-size: 22px; font-weight: 600; }")

    def set_db_path(self, db_path):
        self.vote_view.set_db_path(db_path)
        self.data_view.set_db_path(db_path)
        self.stats_view.set_db_path(db_path)
        self.roster_view.set_db_path(db_path)
        self.answer_view.set_db_path(db_path)
        self.unread_view.set_db_path(db_path)
        self.scoring_view.set_db_path(db_path)
        self.scoring_result_view.set_db_path(db_path)
        self.site_status_view.set_db_path(db_path)
        self.type_status_view.set_db_path(db_path)
        self.item_analysis_view.set_db_path(db_path)


class SettingsInterface(QWidget):
    auto_open_changed = Signal(bool)
    auto_retry_changed = Signal(bool)
    error_popup_changed = Signal(bool)
    debug_save_changed = Signal(bool)
    log_level_changed = Signal(str)
    locale_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        self._settings = QSettings("OMR", "OMRProject")
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("설정")
        title.setObjectName("settingsTitle")

        # 시작 설정
        startup_group = HoverGroupBox("시작")
        startup_layout = QVBoxLayout(startup_group)
        self.chk_auto_open = QCheckBox("마지막 DB 자동 열기")
        self.chk_auto_open.toggled.connect(self._on_auto_open_changed)
        startup_layout.addWidget(self.chk_auto_open)

        # 테마 설정
        theme_group = HoverGroupBox("테마")
        theme_layout = QVBoxLayout(theme_group)
        self.chk_dark = QCheckBox("다크 모드")
        self.chk_dark.toggled.connect(self._on_toggle_dark)
        theme_layout.addWidget(self.chk_dark)

        # 글자 크기
        font_group = HoverGroupBox("글자 크기")
        font_layout = QVBoxLayout(font_group)
        self.lbl_font = QLabel("기본: 10")
        self.slider_font = QSlider(Qt.Horizontal)
        self.slider_font.setMinimum(8)
        self.slider_font.setMaximum(16)
        self.slider_font.setValue(10)
        self.slider_font.valueChanged.connect(self._on_font_size_changed)
        font_layout.addWidget(self.lbl_font)
        font_layout.addWidget(self.slider_font)

        # 스캔 동작
        scan_group = HoverGroupBox("스캔")
        scan_layout = QVBoxLayout(scan_group)
        self.chk_auto_retry = QCheckBox("오류 시 자동 재시도")
        self.chk_auto_retry.toggled.connect(self._on_auto_retry_changed)
        self.chk_error_popup = QCheckBox("오류 팝업 표시")
        self.chk_error_popup.toggled.connect(self._on_error_popup_changed)
        scan_layout.addWidget(self.chk_auto_retry)
        scan_layout.addWidget(self.chk_error_popup)

        # 디버그/로그
        debug_group = HoverGroupBox("디버그/로그")
        debug_layout = QVBoxLayout(debug_group)
        self.chk_debug_save = QCheckBox("오류 이미지 저장")
        self.chk_debug_save.toggled.connect(self._on_debug_save_changed)

        self.cbo_log_level = QComboBox()
        self.cbo_log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.cbo_log_level.currentTextChanged.connect(self._on_log_level_changed)

        debug_layout.addWidget(self.chk_debug_save)
        debug_layout.addWidget(QLabel("로그 레벨"))
        debug_layout.addWidget(self.cbo_log_level)

        # 언어/지역
        locale_group = HoverGroupBox("언어/지역")
        locale_layout = QVBoxLayout(locale_group)
        self.cbo_locale = QComboBox()
        self.cbo_locale.addItems(["한국어 (ko-KR)", "English (en-US)"])
        self.cbo_locale.currentTextChanged.connect(self._on_locale_changed)
        locale_layout.addWidget(self.cbo_locale)
        locale_layout.addWidget(QLabel("변경 사항은 재시작 후 적용됩니다."))

        root.addWidget(title)
        root.addWidget(startup_group)
        root.addWidget(theme_group)
        root.addWidget(font_group)
        root.addWidget(scan_group)
        root.addWidget(debug_group)
        root.addWidget(locale_group)
        root.addStretch(1)

        self.setStyleSheet(
            "#settingsTitle { font-size: 22px; font-weight: 600; }"
            "QGroupBox { background: rgba(255, 255, 255, 0.92); border: 1px solid rgba(0,0,0,0.08);"
            " border-radius: 12px; padding: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; top: -2px; padding: 0 6px; }"
        )

    def _load_settings(self):
        self.chk_auto_open.setChecked(self._settings.value("startup/auto_open", False, type=bool))
        self.chk_dark.setChecked(self._settings.value("theme/dark", False, type=bool))

        font_size = self._settings.value("font/size", 10, type=int)
        self.slider_font.setValue(font_size)
        self.lbl_font.setText(f"기본: {font_size}")

        self.chk_auto_retry.setChecked(self._settings.value("scan/auto_retry", False, type=bool))
        self.chk_error_popup.setChecked(self._settings.value("scan/error_popups", True, type=bool))
        self.chk_debug_save.setChecked(self._settings.value("debug/save_on_error", False, type=bool))

        log_level = self._settings.value("log/level", "INFO", type=str)
        idx = self.cbo_log_level.findText(log_level)
        if idx >= 0:
            self.cbo_log_level.setCurrentIndex(idx)

        locale = self._settings.value("locale", "한국어 (ko-KR)", type=str)
        idx = self.cbo_locale.findText(locale)
        if idx >= 0:
            self.cbo_locale.setCurrentIndex(idx)

    def _on_auto_open_changed(self, checked: bool):
        self._settings.setValue("startup/auto_open", checked)
        self.auto_open_changed.emit(checked)

    def _on_toggle_dark(self, checked: bool):
        try:
            setTheme(Theme.DARK if checked else Theme.LIGHT)
        except Exception:
            pass
        self._settings.setValue("theme/dark", checked)

    def _on_font_size_changed(self, size: int):
        self.lbl_font.setText(f"기본: {size}")
        app = QApplication.instance()
        if app is None:
            return
        font = app.font()
        font.setPointSize(size)
        app.setFont(font)
        self._settings.setValue("font/size", size)

    def _on_auto_retry_changed(self, checked: bool):
        self._settings.setValue("scan/auto_retry", checked)
        self.auto_retry_changed.emit(checked)

    def _on_error_popup_changed(self, checked: bool):
        self._settings.setValue("scan/error_popups", checked)
        self.error_popup_changed.emit(checked)

    def _on_debug_save_changed(self, checked: bool):
        self._settings.setValue("debug/save_on_error", checked)
        self.debug_save_changed.emit(checked)

    def _on_log_level_changed(self, level: str):
        self._settings.setValue("log/level", level)
        self.log_level_changed.emit(level)

    def _on_locale_changed(self, label: str):
        self._settings.setValue("locale", label)
        self.locale_changed.emit(label)


class OMRScannerApp(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OMR_PRO")
        self.resize(1280, 800)

        self._settings = QSettings("OMR", "OMRProject")
        self.current_db_path = None

        self.home_interface = HomeInterface(self)
        self.scan_interface = ScanInterface(self)
        self.results_interface = ResultsInterface(self)
        self.settings_interface = SettingsInterface(self)

        self._init_navigation()
        self._connect_signals()
        self._apply_saved_settings()
        self._auto_open_last_db()

    def _init_navigation(self):
        self.addSubInterface(
            self.home_interface,
            _icon("HOME"),
            "홈",
            selected=True,
        )
        self.addSubInterface(
            self.scan_interface,
            _icon("SCAN", _icon("CAMERA")),
            "스캔 판독",
        )
        self.addSubInterface(
            self.results_interface,
            _icon("DOCUMENT"),
            "데이터 조회 및 수정",
        )
        self.addSubInterface(
            self.settings_interface,
            _icon("SETTING"),
            "설정",
            position=NavigationItemPosition.BOTTOM,
        )

    def addSubInterface(self, interface, icon, text, position=NavigationItemPosition.TOP, selected=False):
        interface.setObjectName(text)
        self.stackedWidget.addWidget(interface)
        self.navigationInterface.addItem(
            routeKey=interface.objectName(),
            icon=icon,
            text=text,
            onClick=lambda: self.switchTo(interface),
            position=position,
        )
        if selected:
            self.stackedWidget.setCurrentWidget(interface)

    def _connect_signals(self):
        self.home_interface.open_file_settings.connect(self.open_file_setting)
        self.home_interface.open_coord_settings.connect(self.open_coord_calibrator)
        self.home_interface.open_env_settings.connect(self.open_env_menu)
        self.settings_interface.auto_retry_changed.connect(self._apply_auto_retry)
        self.settings_interface.error_popup_changed.connect(self._apply_error_popups)
        self.settings_interface.debug_save_changed.connect(self._apply_debug_save)
        self.settings_interface.log_level_changed.connect(self._apply_log_level)

    def open_file_setting(self):
        dlg = FileSettingsDialog(self)
        dlg.db_selected_signal.connect(self.on_db_changed)
        dlg.exec_()

    def on_db_changed(self, path, title):
        self.current_db_path = path
        self.setWindowTitle(f"김세윤omr_project - [{title}]")
        self.scan_interface.scanner_view.set_current_db(path)
        self.results_interface.set_db_path(path)
        self._settings.setValue("startup/last_db_path", path)

    def get_current_db(self):
        if not self.current_db_path:
            QMessageBox.warning(self, "경고", "먼저 DB파일을 선택(파일 설정)해주세요.")
            return None
        return self.current_db_path

    def open_coord_calibrator(self):
        db_path = self.get_current_db()
        if db_path:
            CoordCalibratorDialog(self, db_path).exec_()

    def open_form_setting(self):
        db_path = self.get_current_db()
        if db_path:
            FormSettingsDialog(self, db_path).exec_()

    def open_mark_setting(self):
        db_path = self.get_current_db()
        if db_path:
            MarkSettingsDialog(self, db_path).exec_()

    def open_path_setting(self):
        db_path = self.get_current_db()
        if db_path:
            PathSettingsDialog(self, db_path).exec_()

    def open_site_setting(self):
        db_path = self.get_current_db()
        if db_path:
            SiteSettingsDialog(self, db_path).exec_()

    def open_env_menu(self, global_pos: QPoint):
        menu = QMenu(self)
        menu.addAction("양식/좌표 설정", self.open_form_setting)
        menu.addAction("기표 인식 설정", self.open_mark_setting)
        menu.addAction("저장 경로 설정", self.open_path_setting)
        menu.addAction("고사장/시험실 설정", self.open_site_setting)
        menu.exec_(global_pos)

    def _apply_saved_settings(self):
        self._apply_auto_retry(self._settings.value("scan/auto_retry", False, type=bool))
        self._apply_error_popups(self._settings.value("scan/error_popups", True, type=bool))
        self._apply_debug_save(self._settings.value("debug/save_on_error", False, type=bool))
        self._apply_log_level(self._settings.value("log/level", "INFO", type=str))

    def _apply_auto_retry(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "control_panel") and hasattr(view.control_panel, "chk_auto_retry"):
            view.control_panel.chk_auto_retry.setChecked(enabled)

    def _apply_error_popups(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "set_error_popups_enabled"):
            view.set_error_popups_enabled(enabled)

    def _apply_debug_save(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.set_debug_options(save_on_error=enabled)

    def _apply_log_level(self, level: str):
        import logging

        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        target = level_map.get(level, logging.INFO)
        if not logging.getLogger().handlers:
            logging.basicConfig(level=target)
        logging.getLogger().setLevel(target)

    def _resolve_db_title(self, db_path: str) -> str:
        try:
            db = DBManager()
            for filename, title, full_path, _ in db.get_all_files():
                if full_path == db_path:
                    return title
        except Exception:
            pass
        return os.path.basename(db_path)

    def _auto_open_last_db(self):
        if not self._settings.value("startup/auto_open", False, type=bool):
            return
        last_path = self._settings.value("startup/last_db_path", "", type=str)
        if last_path and os.path.exists(last_path):
            self.on_db_changed(last_path, self._resolve_db_title(last_path))
