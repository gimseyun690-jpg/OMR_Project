from __future__ import annotations

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QBrush, QColor
from PySide2.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QTableWidgetItem
from PySide2.QtGui import QStandardItem, QStandardItemModel


class _GridItemProxy:
    """QTableWidgetItem-like proxy for compatibility with existing handlers."""

    def __init__(self, grid: "DataGrid", row: int, col: int):
        self._grid = grid
        self._row = int(row)
        self._col = int(col)

    def row(self):
        return self._row

    def column(self):
        return self._col

    def text(self):
        return self._grid._cell_text(self._row, self._col)

    def setText(self, text):
        self._grid._set_cell_text(self._row, self._col, text)

    def setForeground(self, value):
        self._grid._set_cell_foreground(self._row, self._col, value)

    def setFlags(self, flags):
        self._grid._set_cell_flags(self._row, self._col, flags)

    def flags(self):
        return self._grid._get_cell_flags(self._row, self._col)

    def setTextAlignment(self, align):
        self._grid._set_cell_alignment(self._row, self._col, align)


class DataGrid(QTableView):
    itemChanged = Signal(object)

    def __init__(self):
        super().__init__()
        self._headers = [
            "판독번호",
            "양식코드",
            "고사장",
            "시험실",
            "표기오류",
            "점검구분",
            "표기내용",
            "앞면경로",
            "앞면파일명",
        ]
        self._editable_cols = {2, 3}
        self._model = QStandardItemModel(0, len(self._headers), self)
        self._model.setHorizontalHeaderLabels(self._headers)
        self.setModel(self._model)
        self._model.itemChanged.connect(self._on_model_item_changed)
        self.init_ui()

    def init_ui(self):
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.EditKeyPressed
        )
        self.setStyleSheet(
            """
            QTableView { background-color: white; gridline-color: #d0d0d0; }
            QHeaderView::section {
                background-color: #E6E6E6;
                color: black;
                padding: 4px;
                border: 1px solid #b0b0b0;
                font-weight: bold; font-size: 11px;
            }
            """
        )

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.resizeSection(0, 60)
        header.resizeSection(1, 60)
        header.resizeSection(6, 200)

    def _make_item(self, text, col: int):
        item = QStandardItem(str(text))
        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if col in self._editable_cols:
            flags |= Qt.ItemIsEditable
        item.setFlags(flags)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _get_std_item(self, row: int, col: int):
        if row < 0 or col < 0:
            return None
        if row >= self._model.rowCount() or col >= self._model.columnCount():
            return None
        return self._model.item(row, col)

    def _ensure_std_item(self, row: int, col: int):
        if row < 0 or col < 0:
            return None
        while row >= self._model.rowCount():
            self._model.insertRow(self._model.rowCount())
        while col >= self._model.columnCount():
            self._model.setColumnCount(self._model.columnCount() + 1)
        item = self._model.item(row, col)
        if item is None:
            item = self._make_item("", col)
            self._model.setItem(row, col, item)
        return item

    def _cell_text(self, row: int, col: int) -> str:
        item = self._get_std_item(row, col)
        return item.text() if item is not None else ""

    def _set_cell_text(self, row: int, col: int, text):
        item = self._ensure_std_item(row, col)
        if item is not None:
            item.setText(str(text))

    def _set_cell_foreground(self, row: int, col: int, value):
        item = self._ensure_std_item(row, col)
        if item is None:
            return
        if isinstance(value, QBrush):
            brush = value
        elif isinstance(value, QColor):
            brush = QBrush(value)
        else:
            brush = QBrush(QColor(value))
        item.setForeground(brush)

    def _set_cell_flags(self, row: int, col: int, flags):
        item = self._ensure_std_item(row, col)
        if item is not None:
            item.setFlags(flags)

    def _get_cell_flags(self, row: int, col: int):
        item = self._get_std_item(row, col)
        if item is None:
            base = Qt.ItemIsSelectable | Qt.ItemIsEnabled
            if col in self._editable_cols:
                base |= Qt.ItemIsEditable
            return base
        return item.flags()

    def _set_cell_alignment(self, row: int, col: int, align):
        item = self._ensure_std_item(row, col)
        if item is not None:
            item.setTextAlignment(int(align))

    def _on_model_item_changed(self, std_item: QStandardItem):
        if std_item is None:
            return
        self.itemChanged.emit(_GridItemProxy(self, std_item.row(), std_item.column()))

    # ---- Compatibility helpers (QTableWidget-like surface) -----------------
    def rowCount(self):
        return self._model.rowCount()

    def columnCount(self):
        return self._model.columnCount()

    def setRowCount(self, rows: int):
        rows = max(0, int(rows))
        cur = self._model.rowCount()
        if rows == cur:
            return
        if rows < cur:
            self._model.removeRows(rows, cur - rows)
        else:
            self._model.insertRows(cur, rows - cur)

    def setColumnCount(self, cols: int):
        self._model.setColumnCount(max(0, int(cols)))

    def setHorizontalHeaderLabels(self, labels):
        self._model.setHorizontalHeaderLabels([str(v) for v in labels])

    def insertRow(self, row: int):
        self._model.insertRow(int(row))

    def removeRow(self, row: int):
        self._model.removeRow(int(row))

    def item(self, row: int, col: int):
        std_item = self._get_std_item(int(row), int(col))
        if std_item is None:
            return None
        return _GridItemProxy(self, int(row), int(col))

    def setItem(self, row: int, col: int, item):
        row = int(row)
        col = int(col)
        if isinstance(item, _GridItemProxy):
            text = item.text()
            flags = item.flags()
        elif isinstance(item, QTableWidgetItem):
            text = item.text()
            flags = item.flags()
        else:
            text = str(item) if item is not None else ""
            flags = self._get_cell_flags(row, col)

        std_item = self._ensure_std_item(row, col)
        if std_item is None:
            return
        std_item.setText(str(text))
        std_item.setFlags(flags)
        std_item.setTextAlignment(Qt.AlignCenter)

    def scrollToItem(self, item):
        if item is None:
            return
        row = item.row() if hasattr(item, "row") else None
        col = item.column() if hasattr(item, "column") else None
        if row is None or col is None:
            return
        index = self._model.index(int(row), int(col))
        if index.isValid():
            self.scrollTo(index, QAbstractItemView.PositionAtCenter)

    def add_row_data(self, data_list):
        row_items = [self._make_item(text, col=i) for i, text in enumerate(data_list)]
        self._model.appendRow(row_items)
