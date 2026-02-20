from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from PySide2.QtCore import Qt
from PySide2.QtGui import QColor, QPainter
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from database import DBManager

try:
    from qfluentwidgets import CardWidget, PrimaryPushButton
except Exception:
    CardWidget = QFrame
    PrimaryPushButton = QPushButton

try:
    from PySide2.QtCharts import (
        QBarCategoryAxis,
        QBarSeries,
        QBarSet,
        QChart,
        QChartView,
        QPieSeries,
        QValueAxis,
    )
except Exception:
    QBarCategoryAxis = None
    QBarSeries = None
    QBarSet = None
    QChart = None
    QChartView = None
    QPieSeries = None
    QValueAxis = None


class MetricCard(CardWidget):
    def __init__(self, title: str, accent: str = "#2563EB", parent=None):
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.lbl_title = QLabel(str(title))
        self.lbl_title.setObjectName("metricTitle")
        self.lbl_value = QLabel("0")
        self.lbl_value.setObjectName("metricValue")
        self.lbl_value.setStyleSheet(f"color: {accent};")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("metricSub")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)
        layout.addStretch(1)

    def set_value(self, value: str, sub: str = ""):
        self.lbl_value.setText(str(value))
        self.lbl_sub.setText(str(sub or ""))


class ScanStatsView(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self._last_scan_count = -1
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("판독 통계 대시보드")
        self.lbl_title.setObjectName("statsTitle")
        self.lbl_subtitle = QLabel("고사장별 분포, 정상/오류 비율, 누적 현황")
        self.lbl_subtitle.setObjectName("statsSubtitle")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)

        header_row.addLayout(title_col, 1)
        self.btn_refresh = PrimaryPushButton("새로고침")
        self.btn_refresh.clicked.connect(lambda: self.load_data(force=True))
        header_row.addWidget(self.btn_refresh, 0, Qt.AlignRight | Qt.AlignVCenter)
        root.addLayout(header_row)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(10)
        self.card_total = MetricCard("총 판독")
        self.card_normal = MetricCard("정상", accent="#16A34A")
        self.card_error = MetricCard("오류", accent="#DC2626")
        self.card_error_rate = MetricCard("오류율", accent="#EA580C")
        metric_row.addWidget(self.card_total)
        metric_row.addWidget(self.card_normal)
        metric_row.addWidget(self.card_error)
        metric_row.addWidget(self.card_error_rate)
        root.addLayout(metric_row)

        chart_row = QHBoxLayout()
        chart_row.setSpacing(10)
        self.bar_card = CardWidget()
        self.bar_card.setObjectName("chartCard")
        bar_layout = QVBoxLayout(self.bar_card)
        bar_layout.setContentsMargins(12, 10, 12, 10)
        bar_layout.setSpacing(8)
        self.lbl_bar = QLabel("고사장/시험실별 판독 매수")
        self.lbl_bar.setObjectName("chartTitle")
        bar_layout.addWidget(self.lbl_bar)

        self.pie_card = CardWidget()
        self.pie_card.setObjectName("chartCard")
        pie_layout = QVBoxLayout(self.pie_card)
        pie_layout.setContentsMargins(12, 10, 12, 10)
        pie_layout.setSpacing(8)
        self.lbl_pie = QLabel("정상/오류 비율")
        self.lbl_pie.setObjectName("chartTitle")
        pie_layout.addWidget(self.lbl_pie)

        self.bar_chart_view = None
        self.pie_chart_view = None
        if QChartView is not None:
            self.bar_chart_view = QChartView()
            self.bar_chart_view.setRenderHint(QPainter.Antialiasing)
            self.bar_chart_view.setMinimumHeight(220)
            bar_layout.addWidget(self.bar_chart_view, 1)

            self.pie_chart_view = QChartView()
            self.pie_chart_view.setRenderHint(QPainter.Antialiasing)
            self.pie_chart_view.setMinimumHeight(220)
            pie_layout.addWidget(self.pie_chart_view, 1)
        else:
            bar_layout.addWidget(QLabel("QtCharts 모듈을 찾지 못해 그래프를 표시할 수 없습니다."))
            pie_layout.addWidget(QLabel("QtCharts 모듈을 찾지 못해 그래프를 표시할 수 없습니다."))

        chart_row.addWidget(self.bar_card, 2)
        chart_row.addWidget(self.pie_card, 1)
        root.addLayout(chart_row)

        self.table_card = CardWidget()
        self.table_card.setObjectName("tableCard")
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(12, 10, 12, 12)
        table_layout.setSpacing(8)
        self.lbl_table = QLabel("고사장별 상세")
        self.lbl_table.setObjectName("chartTitle")
        table_layout.addWidget(self.lbl_table)

        self.table = QTableWidget()
        self.table.setObjectName("statsTable")
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["고사장/스캐너", "시험실", "총매수", "정상", "오류", "오류율"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)
        root.addWidget(self.table_card, 1)

        self.setStyleSheet(
            """
            #statsTitle { font-size: 22px; font-weight: 700; color: #0F172A; }
            #statsSubtitle { font-size: 12px; color: #64748B; }
            #metricCard, #chartCard, #tableCard {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 12px;
            }
            #metricTitle { font-size: 12px; color: #64748B; }
            #metricValue { font-size: 28px; font-weight: 700; color: #0F172A; }
            #metricSub { font-size: 11px; color: #94A3B8; }
            #chartTitle { font-size: 14px; font-weight: 600; color: #0F172A; }
            #statsTable {
                gridline-color: #E2E8F0;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                border: none;
                border-bottom: 1px solid #E2E8F0;
                padding: 6px;
                font-weight: 600;
                color: #334155;
            }
            """
        )

    def set_db_path(self, path):
        path = path or None
        changed = path != self.current_db_path
        self.current_db_path = path

        if not self.current_db_path:
            self._clear_all()
            return

        if not changed and self._is_scan_count_unchanged():
            return
        self.load_data(force=True)

    def _clear_all(self):
        self.table.setRowCount(0)
        self.card_total.set_value("0")
        self.card_normal.set_value("0")
        self.card_error.set_value("0")
        self.card_error_rate.set_value("0.0%")
        self._last_scan_count = -1

    def _is_scan_count_unchanged(self) -> bool:
        try:
            return self.db.get_scan_count(self.current_db_path) == self._last_scan_count
        except Exception:
            return False

    @staticmethod
    def _item(text: str):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    @staticmethod
    def _fmt_num(value: int) -> str:
        return f"{int(value):,}"

    def _update_metric_cards(self, total: int, normal: int, error: int, groups: int):
        rate = (float(error) / float(total) * 100.0) if total > 0 else 0.0
        self.card_total.set_value(self._fmt_num(total), f"고사장 그룹 {groups}개")
        self.card_normal.set_value(self._fmt_num(normal), "정상 판독")
        self.card_error.set_value(self._fmt_num(error), "오류/미점검")
        self.card_error_rate.set_value(f"{rate:.1f}%", "오류 비율")

    def _update_table(self, rows: Sequence[Tuple]):
        self.table.setRowCount(len(rows) + 1)
        total_all = 0
        total_normal = 0
        total_error = 0

        for i, row in enumerate(rows):
            scanner, room, read_cnt, err_cnt = row
            total = int(read_cnt)
            err = int(err_cnt)
            normal = total - err
            rate = (float(err) / float(total) * 100.0) if total > 0 else 0.0

            total_all += total
            total_normal += normal
            total_error += err

            self.table.setItem(i, 0, self._item(scanner))
            self.table.setItem(i, 1, self._item(room))
            self.table.setItem(i, 2, self._item(self._fmt_num(total)))
            self.table.setItem(i, 3, self._item(self._fmt_num(normal)))
            self.table.setItem(i, 4, self._item(self._fmt_num(err)))
            self.table.setItem(i, 5, self._item(f"{rate:.1f}%"))

        last = len(rows)
        total_rate = (float(total_error) / float(total_all) * 100.0) if total_all > 0 else 0.0
        self.table.setItem(last, 0, self._item("전체 합계"))
        self.table.setItem(last, 1, self._item("-"))
        self.table.setItem(last, 2, self._item(self._fmt_num(total_all)))
        self.table.setItem(last, 3, self._item(self._fmt_num(total_normal)))
        self.table.setItem(last, 4, self._item(self._fmt_num(total_error)))
        self.table.setItem(last, 5, self._item(f"{total_rate:.1f}%"))

        for c in range(6):
            item = self.table.item(last, c)
            if item is not None:
                item.setBackground(QColor("#FEF3C7"))

    def _build_bar_chart(self, rows: Sequence[Tuple]):
        if self.bar_chart_view is None or QChart is None:
            return

        sorted_rows = sorted(rows, key=lambda x: int(x[2]), reverse=True)[:12]
        labels = []
        normal_vals = []
        error_vals = []
        for scanner, room, read_cnt, err_cnt in sorted_rows:
            total = int(read_cnt)
            err = int(err_cnt)
            normal = max(0, total - err)
            labels.append(f"{scanner}\n{room}")
            normal_vals.append(normal)
            error_vals.append(err)

        set_normal = QBarSet("정상")
        set_error = QBarSet("오류")
        for v in normal_vals:
            set_normal.append(float(v))
        for v in error_vals:
            set_error.append(float(v))
        set_normal.setColor(QColor("#22C55E"))
        set_error.setColor(QColor("#EF4444"))

        series = QBarSeries()
        series.append(set_normal)
        series.append(set_error)

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("상위 12개 그룹 판독 현황")
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)

        axis_x = QBarCategoryAxis()
        axis_x.append(labels if labels else ["-"])
        axis_x.setLabelsAngle(-35)
        axis_y = QValueAxis()
        max_val = max([1] + [n + e for n, e in zip(normal_vals, error_vals)])
        axis_y.setRange(0, max_val * 1.15)
        axis_y.setLabelFormat("%d")

        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        self.bar_chart_view.setChart(chart)

    def _build_pie_chart(self, normal: int, error: int):
        if self.pie_chart_view is None or QChart is None or QPieSeries is None:
            return

        series = QPieSeries()
        n_slice = series.append("정상", float(max(0, normal)))
        e_slice = series.append("오류", float(max(0, error)))
        n_slice.setColor(QColor("#22C55E"))
        e_slice.setColor(QColor("#EF4444"))
        e_slice.setExploded(error > 0)
        e_slice.setLabelVisible(error > 0)

        for s in series.slices():
            s.setLabelVisible(True)
            s.setLabel(f"{s.label()} {s.percentage() * 100.0:.1f}%")

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("정상/오류 비중")
        chart.setAnimationOptions(QChart.SeriesAnimations)
        chart.legend().setVisible(False)
        self.pie_chart_view.setChart(chart)

    def load_data(self, force=False):
        if not self.current_db_path:
            self._clear_all()
            return
        if not force and self._is_scan_count_unchanged():
            return

        rows = self.db.get_summary_by_scanner(self.current_db_path) or []
        total, normal, error = self.db.get_statistics(self.current_db_path)
        groups = len(rows)

        self._update_metric_cards(total, normal, error, groups)
        self._update_table(rows)
        self._build_bar_chart(rows)
        self._build_pie_chart(normal, error)

        self._last_scan_count = int(total)
