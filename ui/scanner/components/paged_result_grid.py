from PySide2.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel
from PySide2.QtCore import Signal

from ui.scanner.components.data_grid import DataGrid


class PagedResultGrid(QWidget):
    """메인 결과 그리드 + 페이징 컨트롤."""

    page_changed = Signal(int)
    page_size_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_page = 1
        self.page_size = 100
        self._init_ui()

    def _init_ui(self):
        self.grid = DataGrid()

        self.btn_prev = QPushButton("이전")
        self.btn_next = QPushButton("다음")
        self.cbo_page_size = QComboBox()
        self.cbo_page_size.addItems(["50", "100", "200", "500", "1000"])
        self.cbo_page_size.setCurrentText("100")

        self.btn_prev.clicked.connect(self._on_prev)
        self.btn_next.clicked.connect(self._on_next)
        self.cbo_page_size.currentTextChanged.connect(self._on_page_size)

        pager = QHBoxLayout()
        pager.addWidget(self.btn_prev)
        pager.addWidget(self.btn_next)
        pager.addStretch(1)
        pager.addWidget(QLabel("페이지 크기:"))
        pager.addWidget(self.cbo_page_size)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.grid)
        layout.addLayout(pager)

    def _on_prev(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.page_changed.emit(self.current_page)

    def _on_next(self):
        self.current_page += 1
        self.page_changed.emit(self.current_page)

    def _on_page_size(self, text: str):
        try:
            self.page_size = int(text)
        except Exception:
            self.page_size = 100
        self.page_size_changed.emit(self.page_size)
