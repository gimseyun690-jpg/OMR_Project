import os
from importlib import import_module
from PySide2.QtCore import Qt, Signal, QPoint, QPointF, QSettings, QPropertyAnimation, QEasingCurve
from PySide2.QtGui import QColor
from PySide2.QtWidgets import (
    QApplication,
    QWidget,
    QMainWindow,
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
    QSpinBox,
    QDoubleSpinBox,
    QGraphicsDropShadowEffect,
    QStackedWidget,
)

from qfluentwidgets import (
    NavigationInterface,
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


def _to_qicon(icon):
    if hasattr(icon, "icon"):
        return icon.icon()
    return icon

def _load_view_class(module_path: str, class_name: str):
    try:
        module = import_module(module_path)
    except ModuleNotFoundError:
        return None
    return getattr(module, class_name, None)

class HomeCard(QWidget):
    clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon):
        super().__init__()
        self.setObjectName("homeCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        self.icon_wrap = QWidget()
        self.icon_wrap.setObjectName("homeCardIconWrap")
        icon_wrap_layout = QVBoxLayout(self.icon_wrap)
        icon_wrap_layout.setContentsMargins(0, 0, 0, 0)
        icon_wrap_layout.setSpacing(0)

        self.icon_label = QLabel(self.icon_wrap)
        self.icon_label.setPixmap(_icon_pixmap(icon, 40))
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        icon_wrap_layout.addWidget(self.icon_label, 0, Qt.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("homeCardTitle")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("homeCardSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMinimumHeight(38)
        self.subtitle_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(self.icon_wrap, 0, Qt.AlignLeft)
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        layout.addStretch(1)
        self._init_shadow()

    def _init_shadow(self):
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(16)
        self._shadow.setOffset(0, 2)
        self._shadow.setColor(QColor(15, 23, 42, 40))
        self.setGraphicsEffect(self._shadow)

        self._shadow_blur_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_blur_anim.setDuration(170)
        self._shadow_blur_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._shadow_offset_anim = QPropertyAnimation(self._shadow, b"offset", self)
        self._shadow_offset_anim.setDuration(170)
        self._shadow_offset_anim.setEasingCurve(QEasingCurve.OutCubic)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.accept()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
            event.accept()
        super().mouseReleaseEvent(event)

    def setSelected(self, selected: bool):
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def enterEvent(self, event):
        self._shadow_blur_anim.stop()
        self._shadow_blur_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_blur_anim.setEndValue(28)
        self._shadow_blur_anim.start()

        self._shadow_offset_anim.stop()
        self._shadow_offset_anim.setStartValue(self._shadow.offset())
        self._shadow_offset_anim.setEndValue(QPointF(0, 7))
        self._shadow_offset_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._shadow_blur_anim.stop()
        self._shadow_blur_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_blur_anim.setEndValue(16)
        self._shadow_blur_anim.start()

        self._shadow_offset_anim.stop()
        self._shadow_offset_anim.setStartValue(self._shadow.offset())
        self._shadow_offset_anim.setEndValue(QPointF(0, 2))
        self._shadow_offset_anim.start()
        super().leaveEvent(event)


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
    open_exam_results = Signal()
    open_church_results = Signal()
    open_rebuild_results = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homeInterface")
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        title = QLabel("OMR 홈")
        title.setObjectName("homeTitle")
        title.setContentsMargins(2, 0, 0, 0)

        hero = QWidget()
        hero.setObjectName("homeHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(10)

        hero_title = QLabel("스마트 OMR 작업공간")
        hero_title.setObjectName("homeHeroTitle")
        hero_sub = QLabel("판독, 오류검토, 통계를 하나의 흐름으로 빠르게 처리합니다.")
        hero_sub.setObjectName("homeHeroSubtitle")
        hero_sub.setWordWrap(True)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        for chip_text in ("실시간 판독", "배치 처리", "통계 대시보드"):
            chip = QLabel(chip_text)
            chip.setObjectName("homeHeroChip")
            chip_row.addWidget(chip, 0, Qt.AlignLeft)
        chip_row.addStretch(1)

        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_sub)
        hero_layout.addLayout(chip_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

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

        self.card_rebuild = HomeCard(
            "재개발·재건축 선거업무",
            "조합/비상대책위/총회 투표 및 집계",
            _icon("CITY"),
        )
        self.card_church = HomeCard(
            "교회 항존직 선거업무",
            "장로·안수집사·권사 선거 관리",
            _icon("PEOPLE"),
        )
        self.card_exam = HomeCard(
            "성적처리/채용시험/자격증시험선거업무/설문지_채점대행",
            "시험 채점, 통계, 결과 처리",
            _icon("DOCUMENT"),
        )

        for card in (
            self.card_file,
            self.card_coord,
            self.card_env,
            self.card_exam,
            self.card_church,
            self.card_rebuild,
        ):
            card.setMinimumHeight(170)

        self.card_file.clicked.connect(self._on_file_settings_clicked)
        self.card_coord.clicked.connect(self._on_coord_settings_clicked)
        self.card_env.clicked.connect(self._on_env_settings_clicked)
        self.card_exam.clicked.connect(self._on_exam_clicked)
        self.card_church.clicked.connect(self._on_church_clicked)
        self.card_rebuild.clicked.connect(self._on_rebuild_clicked)

        grid.addWidget(self.card_file, 0, 0)
        grid.addWidget(self.card_coord, 0, 1)
        grid.addWidget(self.card_env, 0, 2)
        grid.addWidget(self.card_exam, 1, 0)
        grid.addWidget(self.card_church, 1, 1)
        grid.addWidget(self.card_rebuild, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        root.addWidget(title)
        root.addWidget(hero)
        root.addLayout(grid)
        root.addStretch(1)

        self.setStyleSheet(
            "#homeInterface {"
            "  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F4F8FF, stop:0.6 #F7FAFF, stop:1 #FFFFFF);"
            "}"
            "#homeTitle { font-size: 28px; font-weight: 700; color: #0F172A; }"
            "#homeHero {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #EAF2FF);"
            "  border: 1px solid #D7E3F5;"
            "  border-radius: 20px;"
            "}"
            "#homeHeroTitle { font-size: 24px; font-weight: 700; color: #0F172A; }"
            "#homeHeroSubtitle { font-size: 13px; color: #334155; }"
            "#homeHeroChip {"
            "  background: #FFFFFF;"
            "  border: 1px solid #CFE0FF;"
            "  border-radius: 11px;"
            "  padding: 4px 10px;"
            "  color: #1D4ED8;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "}"
            "#homeCard {"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #F8FBFF);"
            "  border: 1px solid #D8E3F2;"
            "  border-radius: 18px;"
            "}"
            "#homeCard:hover {"
            "  border-color: #2E6BD9;"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #EAF2FF);"
            "}"
            "#homeCard[selected='true'] {"
            "  border: 2px solid #2E6BD9;"
            "  background: #E3EEFF;"
            "}"
            "#homeCardIconWrap {"
            "  background: #F2F7FF;"
            "  border: 1px solid #DCE8FC;"
            "  border-radius: 12px;"
            "  min-width: 48px;"
            "  max-width: 48px;"
            "  min-height: 48px;"
            "  max-height: 48px;"
            "}"
            "#homeCardTitle { font-size: 18px; font-weight: 700; color: #111827; }"
            "#homeCardSubtitle { color: #4B5563; font-size: 13px; }"
        )

    def _emit_env_menu(self):
        pos = self.card_env.mapToGlobal(self.card_env.rect().bottomLeft())
        self.open_env_settings.emit(pos)

    def _set_selected_card(self, selected_card: HomeCard):
        for card in (self.card_exam, self.card_church, self.card_rebuild):
            card.setSelected(card is selected_card)

    def select_exam(self):
        self._set_selected_card(self.card_exam)

    def select_church(self):
        self._set_selected_card(self.card_church)

    def select_rebuild(self):
        self._set_selected_card(self.card_rebuild)

    def clear_mode_selection(self):
        self._set_selected_card(None)

    def _on_file_settings_clicked(self):
        self.open_file_settings.emit()

    def _on_coord_settings_clicked(self):
        self.open_coord_settings.emit()

    def _on_env_settings_clicked(self):
        self._emit_env_menu()

    def _on_exam_clicked(self):
        self.select_exam()
        self.open_exam_results.emit()

    def _on_church_clicked(self):
        self.select_church()
        self.open_church_results.emit()

    def _on_rebuild_clicked(self):
        self.select_rebuild()
        self.open_rebuild_results.emit()

class ScanInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("scanInterface")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scanner_view = ScannerReadingView()
        layout.addWidget(self.scanner_view)


class PlaceholderFeatureView(QWidget):
    def __init__(self, title: str, detail: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        lbl_title = QLabel(str(title or "준비중"))
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 600; color: #0F172A;")
        lbl_msg = QLabel(str(detail or "해당 기능은 현재 준비 중입니다."))
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("font-size: 13px; color: #475569;")

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_msg)
        layout.addStretch(1)


class ResultsExamInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsExamInterface")
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        title = QLabel("시험 관리")
        title.setObjectName("resultsTitle")
        subtitle = QLabel("판독 데이터, 통계 대시보드, 명단/정답/채점/분석을 한 화면에서 관리합니다.")
        subtitle.setObjectName("resultsSubtitle")

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setMovable(False)

        self.data_view = ScanDataView()
        self.stats_view = ScanStatsView()
        self.tabs.addTab(self.data_view, _to_qicon(_icon("DOCUMENT")), "판독 자료")
        self.tabs.addTab(self.stats_view, _to_qicon(_icon("BAR_CHART", _icon("APPLICATION"))), "판독 통계")

        optional_tabs = [
            ("ui.results.roster_input", "RosterInputView", "명단 입력", "roster_view"),
            ("ui.results.answer_input", "AnswerInputView", "정답 입력", "answer_view"),
            ("ui.results.unread_check", "UnreadCheckView", "미판독 확인", "unread_view"),
            ("ui.results.scoring_calc", "ScoringCalcView", "채점 계산", "scoring_view"),
            ("ui.results.scoring_result", "ScoringResultView", "채점 결과", "scoring_result_view"),
            ("ui.results.site_status", "SiteStatusView", "고사장 현황", "site_status_view"),
            ("ui.results.type_status", "TypeStatusView", "전형별 현황", "type_status_view"),
            ("ui.results.item_analysis", "ItemAnalysisView", "문항 분석", "item_analysis_view"),
        ]
        for module_path, class_name, tab_name, attr_name in optional_tabs:
            view_cls = _load_view_class(module_path, class_name)
            if view_cls is None:
                placeholder = PlaceholderFeatureView(
                    tab_name,
                    f"`{module_path}.{class_name}` 모듈이 없어 탭을 축소 모드로 표시합니다.",
                )
                setattr(self, attr_name, placeholder)
                self.tabs.addTab(
                    placeholder,
                    _to_qicon(_icon("APPLICATION")),
                    f"{tab_name} (준비중)",
                )
                continue
            try:
                view = view_cls()
            except Exception:
                placeholder = PlaceholderFeatureView(
                    tab_name,
                    f"`{module_path}.{class_name}` 로드 중 오류가 발생해 축소 모드로 표시합니다.",
                )
                setattr(self, attr_name, placeholder)
                self.tabs.addTab(
                    placeholder,
                    _to_qicon(_icon("APPLICATION")),
                    f"{tab_name} (오류)",
                )
                continue
            setattr(self, attr_name, view)
            self.tabs.addTab(view, _to_qicon(_icon("APPLICATION")), tab_name)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(self.tabs, 1)

        self.setStyleSheet(
            """
            #resultsTitle { font-size: 24px; font-weight: 700; color: #0F172A; }
            #resultsSubtitle { font-size: 12px; color: #64748B; padding-bottom: 2px; }
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                border-radius: 12px;
                background: #FFFFFF;
                top: -2px;
            }
            QTabBar::tab {
                background: transparent;
                color: #475569;
                min-height: 30px;
                padding: 6px 12px;
                margin: 6px 4px 4px 4px;
                border-radius: 8px;
            }
            QTabBar::tab:hover {
                background: #F1F5F9;
            }
            QTabBar::tab:selected {
                background: #E8F1FF;
                color: #1D4ED8;
                font-weight: 600;
            }
            """
        )

    def set_db_path(self, db_path):
        for attr in (
            "data_view",
            "stats_view",
            "roster_view",
            "answer_view",
            "unread_view",
            "scoring_view",
            "scoring_result_view",
            "site_status_view",
            "type_status_view",
            "item_analysis_view",
        ):
            view = getattr(self, attr, None)
            if view is not None and hasattr(view, "set_db_path"):
                try:
                    view.set_db_path(db_path)
                except Exception:
                    pass

class ResultsChurchInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsChurchInterface")
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("교회 선거")
        title.setObjectName("resultsTitle")

        self.tabs = QTabWidget()
        self.vote_view = VoteCountView()
        self.data_view = ScanDataView()
        self.stats_view = ScanStatsView()

        self.tabs.addTab(self.vote_view, "개표 결과")
        self.tabs.addTab(self.data_view, "판독 자료")
        self.tabs.addTab(self.stats_view, "판독 매수")

        root.addWidget(title)
        root.addWidget(self.tabs, 1)

        self.setStyleSheet("#resultsTitle { font-size: 22px; font-weight: 600; }")

    def set_db_path(self, db_path):
        for view in (self.vote_view, self.data_view, self.stats_view):
            try:
                view.set_db_path(db_path)
            except Exception:
                pass


class ResultsRebuildInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultsRebuildInterface")
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("재개발 총회")
        title.setObjectName("resultsTitle")

        self.tabs = QTabWidget()
        self.vote_view = VoteCountView()
        self.data_view = ScanDataView()
        self.stats_view = ScanStatsView()

        self.tabs.addTab(self.vote_view, "개표 결과")
        self.tabs.addTab(self.data_view, "판독 자료")
        self.tabs.addTab(self.stats_view, "판독 매수")

        root.addWidget(title)
        root.addWidget(self.tabs, 1)

        self.setStyleSheet("#resultsTitle { font-size: 22px; font-weight: 600; }")

    def set_db_path(self, db_path):
        for view in (self.vote_view, self.data_view, self.stats_view):
            try:
                view.set_db_path(db_path)
            except Exception:
                pass


class SettingsInterface(QWidget):
    PARTIAL_OFFSET_KEYS = ("exam_no", "birth", "name", "subject", "question")

    auto_open_changed = Signal(bool)
    auto_retry_changed = Signal(bool)
    high_performance_changed = Signal(bool)
    error_popup_changed = Signal(bool)
    marker_deskew_changed = Signal(bool)
    debug_save_changed = Signal(bool)
    auto_scale_dpi_changed = Signal(bool)
    dpi_changed = Signal(int)
    global_offset_x_changed = Signal(int)
    global_offset_y_changed = Signal(int)
    partial_offset_changed = Signal(str, str, int)
    omr_marker_threshold_changed = Signal(int)
    omr_block_size_changed = Signal(int)
    omr_c_changed = Signal(int)
    omr_pixel_ratio_changed = Signal(float)
    omr_red_cutoff_changed = Signal(int)
    omr_open_kernel_changed = Signal(int)
    log_level_changed = Signal(str)
    locale_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        self._settings = QSettings("OMR", "OMRProject")
        self._db = DBManager()
        self._current_db_path = None
        self._loading_omr_settings = False
        self._init_ui()
        self._load_settings()
        self.refresh_omr_settings()

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
        self.chk_high_performance = QCheckBox("고성능 모드 (배치 판독 시 CPU 코어 최대 사용)")
        self.chk_high_performance.toggled.connect(self._on_high_performance_changed)
        self.chk_error_popup = QCheckBox("오류 팝업 표시")
        self.chk_error_popup.toggled.connect(self._on_error_popup_changed)
        self.chk_auto_scale_dpi = QCheckBox("DPI 변경 시 좌표 자동 스케일")
        self.chk_auto_scale_dpi.toggled.connect(self._on_auto_scale_dpi_changed)
        self.chk_marker_deskew = QCheckBox("마커 기반 데스큐 사용")
        self.chk_marker_deskew.toggled.connect(self._on_marker_deskew_changed)
        offset_row = QHBoxLayout()
        offset_row.addWidget(QLabel("전역 X 오프셋"))
        self.spin_offset_x = QSpinBox()
        self.spin_offset_x.setRange(-2000, 2000)
        self.spin_offset_x.setSingleStep(1)
        self.spin_offset_x.valueChanged.connect(self._on_global_offset_x_changed)
        offset_row.addWidget(self.spin_offset_x)
        offset_row.addSpacing(12)
        offset_row.addWidget(QLabel("전역 Y 오프셋"))
        self.spin_offset_y = QSpinBox()
        self.spin_offset_y.setRange(-2000, 2000)
        self.spin_offset_y.setSingleStep(1)
        self.spin_offset_y.valueChanged.connect(self._on_global_offset_y_changed)
        offset_row.addWidget(self.spin_offset_y)
        offset_row.addStretch(1)
        self.partial_offset_spins = {}
        partial_group = HoverGroupBox("부분 오프셋")
        partial_layout = QGridLayout(partial_group)
        partial_layout.setContentsMargins(8, 8, 8, 8)
        partial_layout.setHorizontalSpacing(8)
        partial_layout.setVerticalSpacing(6)
        partial_layout.addWidget(QLabel("항목"), 0, 0)
        partial_layout.addWidget(QLabel("X"), 0, 1)
        partial_layout.addWidget(QLabel("Y"), 0, 2)
        partial_labels = {
            "exam_no": "수험번호",
            "birth": "생년월일",
            "name": "이름",
            "subject": "선택과목",
            "question": "문항",
        }
        for row, key in enumerate(self.PARTIAL_OFFSET_KEYS, start=1):
            partial_layout.addWidget(QLabel(partial_labels.get(key, key)), row, 0)
            spin_x = QSpinBox()
            spin_x.setRange(-2000, 2000)
            spin_x.setSingleStep(1)
            spin_x.valueChanged.connect(
                lambda value, section=key: self._on_partial_offset_changed(section, "x", value)
            )
            partial_layout.addWidget(spin_x, row, 1)
            self.partial_offset_spins[(key, "x")] = spin_x
            spin_y = QSpinBox()
            spin_y.setRange(-2000, 2000)
            spin_y.setSingleStep(1)
            spin_y.valueChanged.connect(
                lambda value, section=key: self._on_partial_offset_changed(section, "y", value)
            )
            partial_layout.addWidget(spin_y, row, 2)
            self.partial_offset_spins[(key, "y")] = spin_y
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("스캔 DPI"))
        self.spin_dpi = QSpinBox()
        self.spin_dpi.setRange(50, 600)
        self.spin_dpi.setSingleStep(50)
        self.spin_dpi.setValue(150)
        self.spin_dpi.valueChanged.connect(self._on_dpi_changed)
        dpi_row.addWidget(self.spin_dpi)
        dpi_row.addStretch(1)
        scan_layout.addWidget(self.chk_auto_retry)
        scan_layout.addWidget(self.chk_high_performance)
        scan_layout.addWidget(self.chk_error_popup)
        scan_layout.addWidget(self.chk_auto_scale_dpi)
        scan_layout.addWidget(self.chk_marker_deskew)
        scan_layout.addLayout(offset_row)
        scan_layout.addWidget(partial_group)
        scan_layout.addLayout(dpi_row)

        self.omr_tuning_group = HoverGroupBox("OMR 기표 인식 튜닝 (프로젝트 DB)")
        self.omr_tuning_group.setObjectName("omrTuningGroup")
        omr_layout = QVBoxLayout(self.omr_tuning_group)
        omr_layout.setContentsMargins(14, 18, 14, 12)
        omr_layout.setSpacing(10)

        self.lbl_omr_tuning_header = QLabel("답안 인식 및 전처리 튜닝")
        self.lbl_omr_tuning_header.setObjectName("omrTuningHeader")
        self.lbl_omr_tuning_desc = QLabel(
            "폼 JSON 값을 먼저 불러오고, 여기서 변경한 값은 프로젝트 DB에 저장되어 폼 기본값을 덮어씁니다."
        )
        self.lbl_omr_tuning_desc.setObjectName("omrTuningDesc")
        self.lbl_omr_tuning_desc.setWordWrap(True)

        tip_marker_threshold = (
            "마커 임계값 (사이드/상단 마커 검출 전용)\n"
            "- 마커 윤곽 검출용 그레이스케일 threshold에 사용됩니다\n"
            "- 답안 버블 픽셀 카운트 기준을 직접 조절하는 값은 아닙니다\n"
            "- 기본값: 120 (프로젝트 fallback)\n"
            "- 권장값: 120~150 (마커 누락/노이즈 상황에 따라)\n"
            "- 노이즈가 마커로 오검출되면 올리고, 마커를 놓치면 낮춰보세요"
        )
        tip_block_size = (
            "적응형 임계값 블록 크기 (홀수)\n"
            "- 값이 클수록 로컬 threshold 계산 창이 넓어집니다\n"
            "- 짝수 입력 시 내부에서 홀수로 보정됩니다\n"
            "- 기본값: 15\n"
            "- 권장값: 11~19 (처음은 15 권장)"
        )
        tip_c = (
            "적응형 임계값 C 값\n"
            "- C를 낮추면 연한 마킹이 더 잘 살아남습니다\n"
            "- C를 높이면 노이즈는 줄지만 연한 마킹을 놓칠 수 있습니다\n"
            "- 기본값: 7\n"
            "- 권장값: 3~5 (연한 연필), 7~9 (노이즈 많은 스캔)"
        )
        tip_red_cutoff = (
            "적응형 임계값 이전 Red 채널 컷오프\n"
            "- 이 값보다 밝은 픽셀은 먼저 흰색으로 강제 처리됩니다\n"
            "- 값을 높일수록 연한 연필/펜 마킹이 더 보존됩니다\n"
            "- 기본값: 180\n"
            "- 권장값: 160~190 (연한 마킹이면 180부터 시작)"
        )
        tip_open_kernel = (
            "이진화 이후 morphology open 커널\n"
            "- 적응형 threshold 이후 작은 노이즈 점을 제거합니다\n"
            "- 값이 크면 가늘거나 연한 마킹이 지워질 수 있습니다\n"
            "- 기본값: 3\n"
            "- 권장값: 1 (연한 마킹), 3 (균형)"
        )
        tip_pixel_ratio = (
            "ROI 채움 비율 임계값 (문항/수험정보 판독)\n"
            "- 채워진 픽셀 비율이 이 값 이상이면 기표로 판정합니다\n"
            "- 코드 기본 fallback: 0.05\n"
            "- 권장값: 0.04~0.06 (연한 마킹은 낮게)\n"
            "- 폼 JSON에 question_layout.mark_threshold가 있으면 문항 영역은 그 값을 우선 사용할 수 있습니다"
        )

        self.spin_omr_marker_threshold = QSpinBox()
        self.spin_omr_marker_threshold.setRange(0, 255)
        self.spin_omr_marker_threshold.setSingleStep(5)
        self.spin_omr_marker_threshold.setToolTip(tip_marker_threshold)
        self.spin_omr_marker_threshold.valueChanged.connect(self._on_omr_marker_threshold_changed)
        self.spin_omr_marker_threshold.setMinimumWidth(132)

        self.spin_omr_block_size = QSpinBox()
        self.spin_omr_block_size.setRange(3, 255)
        self.spin_omr_block_size.setSingleStep(2)
        self.spin_omr_block_size.setToolTip(tip_block_size)
        self.spin_omr_block_size.valueChanged.connect(self._on_omr_block_size_changed)
        self.spin_omr_block_size.setMinimumWidth(132)

        self.spin_omr_c = QSpinBox()
        self.spin_omr_c.setRange(0, 30)
        self.spin_omr_c.setSingleStep(1)
        self.spin_omr_c.setToolTip(tip_c)
        self.spin_omr_c.valueChanged.connect(self._on_omr_c_changed)
        self.spin_omr_c.setMinimumWidth(132)

        self.spin_omr_red_cutoff = QSpinBox()
        self.spin_omr_red_cutoff.setRange(0, 255)
        self.spin_omr_red_cutoff.setSingleStep(5)
        self.spin_omr_red_cutoff.setToolTip(tip_red_cutoff)
        self.spin_omr_red_cutoff.valueChanged.connect(self._on_omr_red_cutoff_changed)
        self.spin_omr_red_cutoff.setMinimumWidth(132)

        self.spin_omr_open_kernel = QSpinBox()
        self.spin_omr_open_kernel.setRange(1, 31)
        self.spin_omr_open_kernel.setSingleStep(2)
        self.spin_omr_open_kernel.setToolTip(tip_open_kernel)
        self.spin_omr_open_kernel.valueChanged.connect(self._on_omr_open_kernel_changed)
        self.spin_omr_open_kernel.setMinimumWidth(132)

        self.spin_omr_pixel_ratio = QDoubleSpinBox()
        self.spin_omr_pixel_ratio.setRange(0.0, 1.0)
        self.spin_omr_pixel_ratio.setDecimals(3)
        self.spin_omr_pixel_ratio.setSingleStep(0.005)
        self.spin_omr_pixel_ratio.setToolTip(tip_pixel_ratio)
        self.spin_omr_pixel_ratio.valueChanged.connect(self._on_omr_pixel_ratio_changed)
        self.spin_omr_pixel_ratio.setMinimumWidth(132)

        def _mk_omr_label(text: str, tip: str) -> QLabel:
            lb = QLabel(text)
            lb.setObjectName("omrFieldLabel")
            lb.setToolTip(tip)
            return lb

        def _mk_omr_field_card(title: str, tip: str, editor: QWidget, helper_text: str) -> QWidget:
            card = QWidget()
            card.setObjectName("omrFieldCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(4)
            title_label = _mk_omr_label(title, tip)
            helper_label = QLabel(helper_text)
            helper_label.setObjectName("omrFieldHint")
            helper_label.setWordWrap(True)
            helper_label.setToolTip(tip)
            card_layout.addWidget(title_label)
            card_layout.addWidget(helper_label)
            card_layout.addWidget(editor)
            return card

        omr_header_panel = QWidget()
        omr_header_panel.setObjectName("omrHeaderPanel")
        omr_header_layout = QVBoxLayout(omr_header_panel)
        omr_header_layout.setContentsMargins(10, 8, 10, 8)
        omr_header_layout.setSpacing(3)
        omr_header_layout.addWidget(self.lbl_omr_tuning_header)
        omr_header_layout.addWidget(self.lbl_omr_tuning_desc)
        omr_layout.addWidget(omr_header_panel)

        self.omr_fields_panel = QWidget()
        self.omr_fields_panel.setObjectName("omrFieldsPanel")
        omr_fields_layout = QGridLayout(self.omr_fields_panel)
        omr_fields_layout.setContentsMargins(0, 0, 0, 0)
        omr_fields_layout.setHorizontalSpacing(8)
        omr_fields_layout.setVerticalSpacing(8)
        for col in range(3):
            omr_fields_layout.setColumnStretch(col, 1)

        omr_fields_layout.addWidget(
            _mk_omr_field_card("마커 임계값", tip_marker_threshold, self.spin_omr_marker_threshold, "마커 검출 전용"),
            0, 0
        )
        omr_fields_layout.addWidget(
            _mk_omr_field_card("블록 크기", tip_block_size, self.spin_omr_block_size, "적응형 threshold 윈도우"),
            0, 1
        )
        omr_fields_layout.addWidget(
            _mk_omr_field_card("C 값", tip_c, self.spin_omr_c, "연한 마킹 민감도"),
            0, 2
        )
        omr_fields_layout.addWidget(
            _mk_omr_field_card("Red Cutoff", tip_red_cutoff, self.spin_omr_red_cutoff, "전처리 백색화 컷오프"),
            1, 0
        )
        omr_fields_layout.addWidget(
            _mk_omr_field_card("Open Kernel", tip_open_kernel, self.spin_omr_open_kernel, "노이즈 제거 강도"),
            1, 1
        )
        omr_fields_layout.addWidget(
            _mk_omr_field_card("Pixel Ratio", tip_pixel_ratio, self.spin_omr_pixel_ratio, "답안/필드 채움 비율 기준"),
            1, 2
        )
        omr_layout.addWidget(self.omr_fields_panel)

        self.lbl_omr_precedence = QLabel(
            "우선순위: 폼 JSON 기본값 -> 프로젝트 DB override. 변경값은 DB에 저장되고 현재 파이프라인에도 즉시 반영됩니다(다음 분석/스캔 호출부터)."
        )
        self.lbl_omr_precedence.setObjectName("omrTuningNote")
        self.lbl_omr_precedence.setWordWrap(True)
        omr_layout.addWidget(self.lbl_omr_precedence)

        self.lbl_omr_tuning_info = QLabel("프로젝트 DB를 선택하면 OMR 튜닝을 편집할 수 있습니다.")
        self.lbl_omr_tuning_info.setObjectName("omrTuningStatus")
        self.lbl_omr_tuning_info.setWordWrap(True)
        omr_layout.addWidget(self.lbl_omr_tuning_info)

        scan_layout.addWidget(self.omr_tuning_group)

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
        root.addWidget(font_group)
        root.addWidget(scan_group)
        root.addWidget(debug_group)
        root.addWidget(locale_group)
        root.addStretch(1)

        self.setStyleSheet(
            "#settingsInterface { background: #F6F8FC; }"
            "#settingsTitle { font-size: 22px; font-weight: 700; color: #0F172A; }"
            "#settingsInterface QGroupBox {"
            " background: #FFFFFF;"
            " border: 1px solid #E1E7EE;"
            " border-radius: 12px;"
            " margin-top: 10px;"
            " padding: 14px 10px 10px 10px;"
            "}"
            "#settingsInterface QGroupBox::title {"
            " subcontrol-origin: margin;"
            " subcontrol-position: top left;"
            " left: 10px;"
            " top: 1px;"
            " padding: 0 6px;"
            " color: #334155;"
            " font-weight: 600;"
            "}"
            "#settingsInterface QCheckBox { color: #1F2937; spacing: 6px; }"
            "#settingsInterface QLabel { color: #1F2937; }"
            "#settingsInterface QSpinBox, #settingsInterface QDoubleSpinBox, #settingsInterface QComboBox {"
            " background: #FFFFFF;"
            " border: 1px solid #D8E0EC;"
            " border-radius: 8px;"
            " min-height: 28px;"
            " padding: 2px 8px;"
            " selection-background-color: #DCEAFE;"
            "}"
            "#settingsInterface QSpinBox:hover, #settingsInterface QDoubleSpinBox:hover, #settingsInterface QComboBox:hover {"
            " border-color: #B8CAE7;"
            "}"
            "#settingsInterface QSpinBox:focus, #settingsInterface QDoubleSpinBox:focus, #settingsInterface QComboBox:focus {"
            " border: 1px solid #2E6BD9;"
            "}"
            "#settingsInterface QSlider::groove:horizontal {"
            " height: 4px;"
            " background: #DCE4F1;"
            " border-radius: 2px;"
            "}"
            "#settingsInterface QSlider::sub-page:horizontal {"
            " background: #2E6BD9;"
            " border-radius: 2px;"
            "}"
            "#settingsInterface QSlider::handle:horizontal {"
            " width: 12px;"
            " margin: -5px 0;"
            " border-radius: 6px;"
            " background: #2E6BD9;"
            " border: 1px solid #1F5FCB;"
            "}"
            "#omrTuningGroup {"
            " background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #F6FAFF, stop:1 #FDFEFF);"
            " border: 1px solid #D7E4FB;"
            " border-radius: 14px;"
            " padding-top: 18px;"
            "}"
            "#omrTuningHeader { font-size: 13px; font-weight: 700; color: #1E3A8A; }"
            "#omrTuningDesc { font-size: 11px; color: #566273; }"
            "#omrHeaderPanel {"
            " background: rgba(255,255,255,0.88);"
            " border: 1px solid #E2ECFB;"
            " border-radius: 10px;"
            "}"
            "#omrFieldsPanel { background: transparent; border: none; }"
            "#omrFieldCard {"
            " background: rgba(255,255,255,0.96);"
            " border: 1px solid #E4ECF8;"
            " border-radius: 10px;"
            "}"
            "#omrTuningGroup QLabel#omrFieldLabel { font-weight: 600; color: #334155; }"
            "#omrFieldHint { font-size: 10px; color: #718096; }"
            "#omrTuningNote {"
            " background: #FFFFFF;"
            " border: 1px solid #DCE7FB;"
            " border-radius: 8px;"
            " padding: 6px 8px;"
            " color: #315CA8;"
            "}"
            "#omrTuningStatus { font-size: 11px; color: #1E6BB8; }"
            "QToolTip {"
            " background: #FFFFFF;"
            " color: #0F172A;"
            " border: 1px solid #CBD8EC;"
            " padding: 8px 10px;"
            " border-radius: 8px;"
            "}"
        )

    def _load_settings(self):
        self.chk_auto_open.setChecked(self._settings.value("startup/auto_open", False, type=bool))
        self._settings.setValue("theme/dark", False)

        font_size = self._settings.value("font/size", 10, type=int)
        self.slider_font.setValue(font_size)
        self.lbl_font.setText(f"기본: {font_size}")

        self.chk_auto_retry.setChecked(self._settings.value("scan/auto_retry", False, type=bool))
        self.chk_high_performance.setChecked(self._settings.value("scan/high_performance", False, type=bool))
        self.chk_error_popup.setChecked(self._settings.value("scan/error_popups", True, type=bool))
        self.chk_auto_scale_dpi.setChecked(self._settings.value("scan/auto_scale_dpi", True, type=bool))
        self.chk_marker_deskew.setChecked(self._settings.value("scan/marker_deskew", True, type=bool))
        self.spin_dpi.setValue(self._settings.value("scan/dpi", 150, type=int))
        self.spin_offset_x.setValue(self._settings.value("scan/global_offset_x", 0, type=int))
        self.spin_offset_y.setValue(self._settings.value("scan/global_offset_y", 0, type=int))
        for section in self.PARTIAL_OFFSET_KEYS:
            for axis in ("x", "y"):
                spin = self.partial_offset_spins.get((section, axis))
                if spin is None:
                    continue
                key = f"scan/offset_{section}_{axis}"
                spin.setValue(self._settings.value(key, 0, type=int))
        self.chk_debug_save.setChecked(self._settings.value("debug/save_on_error", False, type=bool))

        log_level = self._settings.value("log/level", "INFO", type=str)
        idx = self.cbo_log_level.findText(log_level)
        if idx >= 0:
            self.cbo_log_level.setCurrentIndex(idx)

        locale = self._settings.value("locale", "한국어 (ko-KR)", type=str)
        idx = self.cbo_locale.findText(locale)
        if idx >= 0:
            self.cbo_locale.setCurrentIndex(idx)

    @staticmethod
    def _parse_omr_int(raw, default: int, min_value: int | None = None, max_value: int | None = None) -> int:
        try:
            value = int(float(raw))
        except Exception:
            value = int(default)
        if min_value is not None:
            value = max(int(min_value), value)
        if max_value is not None:
            value = min(int(max_value), value)
        return int(value)

    @staticmethod
    def _parse_omr_float(raw, default: float, min_value: float | None = None, max_value: float | None = None) -> float:
        try:
            value = float(raw)
        except Exception:
            value = float(default)
        if min_value is not None:
            value = max(float(min_value), value)
        if max_value is not None:
            value = min(float(max_value), value)
        return float(value)

    def _set_omr_tuning_enabled(self, enabled: bool):
        if hasattr(self, "omr_tuning_group"):
            self.omr_tuning_group.setEnabled(bool(enabled))

    def set_project_db(self, db_path: str | None, pipeline=None):
        self._current_db_path = db_path if db_path else None
        self.refresh_omr_settings(pipeline=pipeline)

    def refresh_omr_settings(self, pipeline=None):
        defaults = {
            "marker_threshold": 120,
            "block_size": 15,
            "c": 7,
            "pixel_ratio": 0.05,
            "red_cutoff": 180,
            "open_kernel": 3,
        }

        engine = getattr(pipeline, "engine", None) if pipeline is not None else None
        if engine is not None:
            defaults["marker_threshold"] = int(getattr(engine, "marker_thresh", defaults["marker_threshold"]))
            defaults["block_size"] = int(getattr(engine, "block_size", defaults["block_size"]))
            defaults["c"] = int(getattr(engine, "C", defaults["c"]))
            defaults["pixel_ratio"] = float(getattr(engine, "pixel_threshold", defaults["pixel_ratio"]))
            defaults["red_cutoff"] = int(
                getattr(
                    engine,
                    "red_cutoff",
                    getattr(getattr(engine, "image_processor", None), "red_cutoff", defaults["red_cutoff"]),
                )
            )
            defaults["open_kernel"] = int(
                getattr(
                    engine,
                    "open_kernel",
                    getattr(getattr(engine, "image_processor", None), "open_kernel", defaults["open_kernel"]),
                )
            )

        has_db = bool(self._current_db_path and os.path.exists(self._current_db_path))
        self._loading_omr_settings = True
        try:
            self.spin_omr_marker_threshold.setValue(self._parse_omr_int(defaults["marker_threshold"], 120, 0, 255))
            self.spin_omr_block_size.setValue(self._parse_omr_int(defaults["block_size"], 15, 3, 255))
            self.spin_omr_c.setValue(self._parse_omr_int(defaults["c"], 7, 0, 30))
            self.spin_omr_pixel_ratio.setValue(self._parse_omr_float(defaults["pixel_ratio"], 0.05, 0.0, 1.0))
            self.spin_omr_red_cutoff.setValue(self._parse_omr_int(defaults["red_cutoff"], 180, 0, 255))
            self.spin_omr_open_kernel.setValue(self._parse_omr_int(defaults["open_kernel"], 3, 1, 31))
        finally:
            self._loading_omr_settings = False

        self._set_omr_tuning_enabled(has_db)
        if hasattr(self, "lbl_omr_tuning_info"):
            if has_db:
                self.lbl_omr_tuning_info.setText(
                    "준비됨. 값은 현재 프로젝트 DB에 저장되며, 현재 파이프라인에도 즉시 반영됩니다(다음 스캔/분석 호출부터)."
                )
            else:
                self.lbl_omr_tuning_info.setText("프로젝트 DB를 먼저 선택하면 OMR 튜닝 항목이 활성화됩니다.")

    def _save_omr_db_value(self, key: str, value) -> bool:
        if self._loading_omr_settings:
            return False
        if not self._current_db_path or not os.path.exists(self._current_db_path):
            return False
        try:
            self._db.save_setting(self._current_db_path, key, value)
            return True
        except Exception:
            return False

    def _on_omr_marker_threshold_changed(self, value: int):
        if self._save_omr_db_value("omr_threshold", int(value)):
            self.omr_marker_threshold_changed.emit(int(value))

    def _on_omr_block_size_changed(self, value: int):
        if self._save_omr_db_value("omr_block_size", int(value)):
            self.omr_block_size_changed.emit(int(value))

    def _on_omr_c_changed(self, value: int):
        if self._save_omr_db_value("omr_c", int(value)):
            self.omr_c_changed.emit(int(value))

    def _on_omr_pixel_ratio_changed(self, value: float):
        if self._save_omr_db_value("omr_pixel_ratio", float(value)):
            self.omr_pixel_ratio_changed.emit(float(value))

    def _on_omr_red_cutoff_changed(self, value: int):
        if self._save_omr_db_value("omr_red_cutoff", int(value)):
            self.omr_red_cutoff_changed.emit(int(value))

    def _on_omr_open_kernel_changed(self, value: int):
        if self._save_omr_db_value("omr_open_kernel", int(value)):
            self.omr_open_kernel_changed.emit(int(value))

    def _on_auto_open_changed(self, checked: bool):
        self._settings.setValue("startup/auto_open", checked)
        self.auto_open_changed.emit(checked)

    def _on_toggle_dark(self, checked: bool):
        try:
            setTheme(Theme.LIGHT)
        except Exception:
            pass
        self._settings.setValue("theme/dark", False)

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

    def _on_high_performance_changed(self, checked: bool):
        self._settings.setValue("scan/high_performance", checked)
        self.high_performance_changed.emit(checked)

    def _on_error_popup_changed(self, checked: bool):
        self._settings.setValue("scan/error_popups", checked)
        self.error_popup_changed.emit(checked)

    def _on_auto_scale_dpi_changed(self, checked: bool):
        self._settings.setValue("scan/auto_scale_dpi", checked)
        self.auto_scale_dpi_changed.emit(checked)

    def _on_marker_deskew_changed(self, checked: bool):
        self._settings.setValue("scan/marker_deskew", checked)
        self.marker_deskew_changed.emit(checked)

    def _on_dpi_changed(self, value: int):
        self._settings.setValue("scan/dpi", int(value))
        self.dpi_changed.emit(int(value))

    def _on_global_offset_x_changed(self, value: int):
        self._settings.setValue("scan/global_offset_x", int(value))
        self.global_offset_x_changed.emit(int(value))

    def _on_global_offset_y_changed(self, value: int):
        self._settings.setValue("scan/global_offset_y", int(value))
        self.global_offset_y_changed.emit(int(value))

    def _on_partial_offset_changed(self, section: str, axis: str, value: int):
        sec = str(section).strip().lower()
        ax = str(axis).strip().lower()
        if sec not in self.PARTIAL_OFFSET_KEYS or ax not in ("x", "y"):
            return
        self._settings.setValue(f"scan/offset_{sec}_{ax}", int(value))
        self.partial_offset_changed.emit(sec, ax, int(value))

    def _on_debug_save_changed(self, checked: bool):
        self._settings.setValue("debug/save_on_error", checked)
        self.debug_save_changed.emit(checked)

    def _on_log_level_changed(self, level: str):
        self._settings.setValue("log/level", level)
        self.log_level_changed.emit(level)

    def _on_locale_changed(self, label: str):
        self._settings.setValue("locale", label)
        self.locale_changed.emit(label)


class OMRScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "QMainWindow, QFrame, QStackedWidget, QWidget {"
            " background-color: #FFFFFF; }"
        )
        self.setWindowTitle("OMR_PRO")
        self.resize(1280, 800)
        self._build_shell()

        self._settings = QSettings("OMR", "OMRProject")
        self.current_db_path = None
        self._nav_routes = []
        self._nav_lock_routes = None

        self.home_interface = HomeInterface(self)
        self.scan_interface = ScanInterface(self)
        self.results_exam_interface = ResultsExamInterface(self)
        self.results_church_interface = ResultsChurchInterface(self)
        self.results_rebuild_interface = ResultsRebuildInterface(self)
        self.settings_interface = SettingsInterface(self)

        self._init_navigation()
        self._connect_signals()
        self._apply_saved_settings()
        self._auto_open_last_db()

    def _build_shell(self):
        root = QWidget(self)
        root.setObjectName("mainRoot")
        root.setAttribute(Qt.WA_TranslucentBackground, False)
        root.setAttribute(Qt.WA_StyledBackground, True)
        root.setAutoFillBackground(True)
        self.setCentralWidget(root)

        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.navigationInterface = NavigationInterface(root, showReturnButton=True)
        self.navigationInterface.setAttribute(Qt.WA_TranslucentBackground, False)
        self.navigationInterface.setAttribute(Qt.WA_StyledBackground, True)
        self.navigationInterface.setAutoFillBackground(True)
        self.navigationInterface.setStyleSheet("NavigationInterface { background: #FFFFFF; background-color: #FFFFFF; }")
        try:
            self.navigationInterface.setAcrylicEnabled(False)
        except Exception:
            pass
        self._enforce_navigation_panel_style()
        panel = getattr(self.navigationInterface, "panel", None)
        if panel is not None and hasattr(panel, "expandAni"):
            try:
                panel.expandAni.finished.connect(self._enforce_navigation_panel_style)
            except Exception:
                pass

        self.stackedWidget = QStackedWidget(root)
        self.stackedWidget.setObjectName("mainStackedWidget")
        self.stackedWidget.setAttribute(Qt.WA_TranslucentBackground, False)
        self.stackedWidget.setAttribute(Qt.WA_StyledBackground, True)
        self.stackedWidget.setAutoFillBackground(True)
        self.stackedWidget.currentChanged.connect(self._on_current_interface_changed)

        root_layout.addWidget(self.navigationInterface)
        root_layout.addWidget(self.stackedWidget, 1)

    def _enforce_navigation_panel_style(self):
        panel = getattr(self.navigationInterface, "panel", None)
        if panel is None:
            return

        panel.setAttribute(Qt.WA_TranslucentBackground, False)
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setAutoFillBackground(True)
        panel.setObjectName("sideNavPanel")
        try:
            panel.setProperty("transparent", False)
        except Exception:
            pass

        scroll_widget = getattr(panel, "scrollWidget", None)
        if scroll_widget is not None:
            scroll_widget.setObjectName("sideNavScrollWidget")
            scroll_widget.setAttribute(Qt.WA_TranslucentBackground, False)
            scroll_widget.setAttribute(Qt.WA_StyledBackground, True)
            scroll_widget.setAutoFillBackground(True)

        panel.setStyleSheet(
            """
            #sideNavPanel, #sideNavPanel[menu=true], #sideNavPanel[menu=false], #sideNavPanel[transparent=true] {
                background: #FFFFFF;
                background-color: #FFFFFF;
                border: 1px solid #E1E7EE;
                border-top-right-radius: 7px;
                border-bottom-right-radius: 7px;
            }
            #sideNavPanel QScrollArea, #sideNavScrollWidget {
                background: #FFFFFF;
                background-color: #FFFFFF;
                border: none;
            }
            """
        )

    def _fix_scanner_grid_after_layout_change(self):
        if hasattr(self, "scan_interface"):
            try:
                self.scan_interface.scanner_view.ensure_main_grid_visible()
            except Exception:
                pass

    def _on_current_interface_changed(self, index: int):
        widget = self.stackedWidget.widget(index)
        if widget is None:
            return
        try:
            self.navigationInterface.setCurrentItem(widget.objectName())
        except Exception:
            pass

    def switchTo(self, interface: QWidget):
        if interface in (
            getattr(self, "results_exam_interface", None),
            getattr(self, "results_church_interface", None),
            getattr(self, "results_rebuild_interface", None),
        ):
            if self.current_db_path and hasattr(interface, "set_db_path"):
                try:
                    interface.set_db_path(self.current_db_path)
                except Exception:
                    pass

        self.stackedWidget.setCurrentWidget(interface)
        try:
            self.navigationInterface.setCurrentItem(interface.objectName())
        except Exception:
            pass
        if interface is getattr(self, "settings_interface", None):
            try:
                self.settings_interface.refresh_omr_settings(
                    getattr(self.scan_interface.scanner_view, "pipeline", None)
                )
            except Exception:
                pass
        if interface is getattr(self, "scan_interface", None):
            self._fix_scanner_grid_after_layout_change()

    def _init_navigation(self):
        self.addSubInterface(
            self.home_interface,
            _icon("HOME"),
            "홈",
            selected=True,
            on_click=self._on_home_nav_clicked,
        )
        self.addSubInterface(
            self.scan_interface,
            _icon("SCAN", _icon("CAMERA")),
            "스캔 판독",
        )
        self.addSubInterface(
            self.results_exam_interface,
            _icon("DOCUMENT"),
            "시험 관리",
            on_click=self._on_exam_nav_clicked,
        )
        self.addSubInterface(
            self.results_church_interface,
            _icon("PEOPLE"),
            "교회 선거",
            on_click=self._on_church_nav_clicked,
        )
        self.addSubInterface(
            self.results_rebuild_interface,
            _icon("CITY"),
            "재개발 총회",
            on_click=self._on_rebuild_nav_clicked,
        )
        self.addSubInterface(
            self.settings_interface,
            _icon("SETTING"),
            "설정",
            position=NavigationItemPosition.BOTTOM,
        )

    def addSubInterface(self, interface, icon, text, position=NavigationItemPosition.TOP, selected=False, on_click=None):
        interface.setObjectName(text)
        self.stackedWidget.addWidget(interface)
        route_key = interface.objectName()
        click_handler = on_click if on_click is not None else (lambda: self.switchTo(interface))
        self.navigationInterface.addItem(
            routeKey=route_key,
            icon=icon,
            text=text,
            onClick=click_handler,
            position=position,
        )
        self._nav_routes.append(route_key)
        if selected:
            self.switchTo(interface)

    def _connect_signals(self):
        self.home_interface.open_file_settings.connect(self.open_file_setting)
        self.home_interface.open_coord_settings.connect(self.open_coord_calibrator)
        self.home_interface.open_env_settings.connect(self.open_env_menu)
        self.home_interface.open_exam_results.connect(self._on_home_select_exam)
        self.home_interface.open_church_results.connect(self._on_home_select_church)
        self.home_interface.open_rebuild_results.connect(self._on_home_select_rebuild)
        self.scan_interface.scanner_view.closed_signal.connect(self._return_home_from_scan)
        self.settings_interface.auto_retry_changed.connect(self._apply_auto_retry)
        self.settings_interface.high_performance_changed.connect(self._apply_high_performance_mode)
        self.settings_interface.error_popup_changed.connect(self._apply_error_popups)
        self.settings_interface.debug_save_changed.connect(self._apply_debug_save)
        self.settings_interface.auto_scale_dpi_changed.connect(self._apply_auto_scale_dpi)
        self.settings_interface.marker_deskew_changed.connect(self._apply_marker_deskew)
        self.settings_interface.dpi_changed.connect(self._apply_scan_dpi)
        self.settings_interface.global_offset_x_changed.connect(self._apply_global_offset_x)
        self.settings_interface.global_offset_y_changed.connect(self._apply_global_offset_y)
        self.settings_interface.partial_offset_changed.connect(self._apply_partial_offset)
        self.settings_interface.omr_marker_threshold_changed.connect(self._apply_omr_marker_threshold)
        self.settings_interface.omr_block_size_changed.connect(self._apply_omr_block_size)
        self.settings_interface.omr_c_changed.connect(self._apply_omr_c)
        self.settings_interface.omr_pixel_ratio_changed.connect(self._apply_omr_pixel_ratio)
        self.settings_interface.omr_red_cutoff_changed.connect(self._apply_omr_red_cutoff)
        self.settings_interface.omr_open_kernel_changed.connect(self._apply_omr_open_kernel)
        self.settings_interface.log_level_changed.connect(self._apply_log_level)

    def open_file_setting(self):
        dlg = FileSettingsDialog(self)
        dlg.db_selected_signal.connect(self.on_db_changed)
        dlg.exec_()

    def on_db_changed(self, path, title):
        self.current_db_path = path
        self.setWindowTitle(f"OMR_P - [{title}]")
        self.scan_interface.scanner_view.set_current_db(path)
        self.results_exam_interface.set_db_path(path)
        self.results_church_interface.set_db_path(path)
        self.results_rebuild_interface.set_db_path(path)
        try:
            self.settings_interface.set_project_db(
                path,
                getattr(self.scan_interface.scanner_view, "pipeline", None),
            )
        except Exception:
            pass
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
        if not db_path:
            return
        try:
            self.settings_interface.set_project_db(
                db_path,
                getattr(self.scan_interface.scanner_view, "pipeline", None),
            )
        except Exception:
            pass
        self.switchTo(self.settings_interface)

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
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid #DDE3EA;"
            " border-radius: 12px; padding: 6px; }"
            "QMenu::item { padding: 8px 18px; margin: 2px 6px; border-radius: 8px; }"
            "QMenu::item:selected { background: #E6F0FF; }"
            "QMenu::item:disabled { color: #999; }"
            "QMenu::separator { height: 1px; background: #E9EDF2; margin: 6px 10px; }"
        )

        menu.addAction(_icon("DOCUMENT").icon(), "양식/좌표 설정", self.open_form_setting)
        menu.addAction(_icon("EDIT").icon(), "기표 인식 설정", self.open_mark_setting)
        menu.addSeparator()
        menu.addAction(_icon("FOLDER").icon(), "저장 경로 설정", self.open_path_setting)
        menu.addAction(_icon("PEOPLE").icon(), "고사장/시험실 설정", self.open_site_setting)
        menu.exec_(global_pos)

    def _set_nav_item_enabled(self, route_key: str, enabled: bool):
        try:
            item = self.navigationInterface.widget(route_key)
        except Exception:
            return
        item.setEnabled(enabled)

    def _lock_navigation(self, allowed_routes):
        allowed = set(allowed_routes)
        allowed.add("설정")
        self._nav_lock_routes = allowed
        for route_key in self._nav_routes:
            self._set_nav_item_enabled(route_key, route_key in allowed)

    def _unlock_navigation(self):
        self._nav_lock_routes = None
        for route_key in self._nav_routes:
            self._set_nav_item_enabled(route_key, True)

    def _on_home_nav_clicked(self):
        self._unlock_navigation()
        if hasattr(self, "home_interface") and hasattr(self.home_interface, "clear_mode_selection"):
            self.home_interface.clear_mode_selection()
        self.switchTo(self.home_interface)

    def _return_home_from_scan(self):
        self._unlock_navigation()
        self.switchTo(self.home_interface)

    def _ensure_db_selected(self, context_label: str = "해당 기능") -> bool:
        if self.current_db_path and os.path.exists(self.current_db_path):
            return True

        reply = QMessageBox.question(
            self,
            "DB 선택 필요",
            f"{context_label}을(를) 사용하려면 먼저 DB 파일을 선택해야 합니다.\n지금 파일 설정을 여시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self.open_file_setting()
        return bool(self.current_db_path and os.path.exists(self.current_db_path))

    def _activate_exam_mode(self):
        if not self._ensure_db_selected("시험 관리"):
            return False
        self._lock_navigation({"홈", "스캔 판독", "시험 관리"})
        self.scan_interface.scanner_view.pipeline.set_candidate_enabled(True)
        self.scan_interface.scanner_view.error_editor_profile = "score"
        if hasattr(self, "home_interface") and hasattr(self.home_interface, "select_exam"):
            self.home_interface.select_exam()
        return True

    def _activate_church_mode(self):
        if not self._ensure_db_selected("교회 선거"):
            return False
        self._lock_navigation({"홈", "스캔 판독", "교회 선거"})
        self.scan_interface.scanner_view.pipeline.set_candidate_enabled(False)
        self.scan_interface.scanner_view.error_editor_profile = "church"
        if hasattr(self, "home_interface") and hasattr(self.home_interface, "select_church"):
            self.home_interface.select_church()
        return True

    def _activate_rebuild_mode(self):
        if not self._ensure_db_selected("재개발 총회"):
            return False
        self._lock_navigation({"홈", "스캔 판독", "재개발 총회"})
        self.scan_interface.scanner_view.pipeline.set_candidate_enabled(False)
        self.scan_interface.scanner_view.error_editor_profile = "rebuild"
        if hasattr(self, "home_interface") and hasattr(self.home_interface, "select_rebuild"):
            self.home_interface.select_rebuild()
        return True

    def _on_home_select_exam(self):
        if not self._activate_exam_mode():
            if hasattr(self, "home_interface") and hasattr(self.home_interface, "clear_mode_selection"):
                self.home_interface.clear_mode_selection()
            return

    def _on_home_select_church(self):
        if not self._activate_church_mode():
            if hasattr(self, "home_interface") and hasattr(self.home_interface, "clear_mode_selection"):
                self.home_interface.clear_mode_selection()
            return

    def _on_home_select_rebuild(self):
        if not self._activate_rebuild_mode():
            if hasattr(self, "home_interface") and hasattr(self.home_interface, "clear_mode_selection"):
                self.home_interface.clear_mode_selection()
            return

    def _on_exam_nav_clicked(self):
        if not self._activate_exam_mode():
            return
        self.switchTo(self.results_exam_interface)

    def _on_church_nav_clicked(self):
        if not self._activate_church_mode():
            return
        self.switchTo(self.results_church_interface)

    def _on_rebuild_nav_clicked(self):
        if not self._activate_rebuild_mode():
            return
        self.switchTo(self.results_rebuild_interface)

    def _apply_saved_settings(self):
        self._apply_auto_retry(self._settings.value("scan/auto_retry", False, type=bool))
        self._apply_high_performance_mode(self._settings.value("scan/high_performance", False, type=bool))
        self._apply_error_popups(self._settings.value("scan/error_popups", True, type=bool))
        self._apply_debug_save(self._settings.value("debug/save_on_error", False, type=bool))
        self._apply_auto_scale_dpi(self._settings.value("scan/auto_scale_dpi", True, type=bool))
        self._apply_marker_deskew(self._settings.value("scan/marker_deskew", True, type=bool))
        self._apply_scan_dpi(self._settings.value("scan/dpi", 150, type=int))
        self._apply_global_offset_x(self._settings.value("scan/global_offset_x", 0, type=int))
        self._apply_global_offset_y(self._settings.value("scan/global_offset_y", 0, type=int))
        for section in SettingsInterface.PARTIAL_OFFSET_KEYS:
            for axis in ("x", "y"):
                key = f"scan/offset_{section}_{axis}"
                self._apply_partial_offset(section, axis, self._settings.value(key, 0, type=int))
        self._apply_log_level(self._settings.value("log/level", "INFO", type=str))

    def _apply_auto_retry(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "control_panel") and hasattr(view.control_panel, "chk_auto_retry"):
            view.control_panel.chk_auto_retry.setChecked(enabled)

    def _apply_high_performance_mode(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "set_demo_high_performance_mode"):
            view.set_demo_high_performance_mode(bool(enabled))
        else:
            view.demo_high_performance_mode = bool(enabled)

    def _apply_error_popups(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "set_error_popups_enabled"):
            view.set_error_popups_enabled(enabled)

    def _apply_debug_save(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.set_debug_options(save_on_error=enabled)

    def _apply_auto_scale_dpi(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.set_auto_scale_dpi(enabled)

    def _apply_marker_deskew(self, enabled: bool):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.set_marker_deskew_enabled(bool(enabled))

    def _apply_scan_dpi(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.set_dpi(int(value))

    def _apply_global_offset_x(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(global_offset_x=int(value))

    def _apply_global_offset_y(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(global_offset_y=int(value))

    def _apply_partial_offset(self, section: str, axis: str, value: int):
        sec = str(section).strip().lower()
        ax = str(axis).strip().lower()
        if sec not in SettingsInterface.PARTIAL_OFFSET_KEYS or ax not in ("x", "y"):
            return
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            kwargs = {f"{sec}_offset_{ax}": int(value)}
            view.pipeline.engine.configure(**kwargs)

    def _apply_omr_marker_threshold(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(marker_thresh=int(value))

    def _apply_omr_block_size(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(block_size=int(value))

    def _apply_omr_c(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(C=int(value))

    def _apply_omr_pixel_ratio(self, value: float):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(pixel_ratio=float(value))

    def _apply_omr_red_cutoff(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(red_cutoff=int(value))

    def _apply_omr_open_kernel(self, value: int):
        view = self.scan_interface.scanner_view
        if hasattr(view, "pipeline"):
            view.pipeline.engine.configure(open_kernel=int(value))

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
