from PySide2.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QGridLayout, QTableWidget, QHeaderView, QPushButton,
    QTableWidgetItem, QLineEdit, QSpinBox, QCheckBox
)
from PySide2.QtCore import Qt
from database import DBManager


class VoteCountView(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DBManager()
        self.current_db_path = None
        self._updating_table = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Settings (user editable)
        grp_settings = QGroupBox("\uc9d1\uacc4 \uc124\uc815")
        grp_settings.setStyleSheet("font-weight: bold; background-color: white;")
        grid_settings = QGridLayout(grp_settings)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("\uc9d1\uacc4 \uc81c\ubaa9")
        self.title_edit.textChanged.connect(self.on_title_changed)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 200)
        self.count_spin.setValue(5)
        self.count_spin.valueChanged.connect(self.on_q_count_changed)

        self.target_title_edit = QLineEdit()
        self.target_title_edit.setPlaceholderText("\uc9d1\uacc4 \ub300\uc0c1 \uc120\ud0dd")
        self.target_title_edit.textChanged.connect(self.on_target_title_changed)

        self.target_opt1_edit = QLineEdit()
        self.target_opt1_edit.setPlaceholderText("\ub300\uc0c11")
        self.target_opt1_edit.textChanged.connect(self.on_target_opt1_changed)

        self.target_opt2_edit = QLineEdit()
        self.target_opt2_edit.setPlaceholderText("\ub300\uc0c12")
        self.target_opt2_edit.textChanged.connect(self.on_target_opt2_changed)

        grid_settings.addWidget(QLabel("\uc9d1\uacc4 \uc81c\ubaa9:"), 0, 0)
        grid_settings.addWidget(self.title_edit, 0, 1)
        grid_settings.addWidget(QLabel("\uc548\uac74 \uac1c\uc218:"), 0, 2)
        grid_settings.addWidget(self.count_spin, 0, 3)
        grid_settings.addWidget(QLabel("\uc9d1\uacc4\ub300\uc0c1 \uc81c\ubaa9:"), 1, 0)
        grid_settings.addWidget(self.target_title_edit, 1, 1)
        grid_settings.addWidget(QLabel("\ub300\uc0c11 \uc774\ub984:"), 2, 0)
        grid_settings.addWidget(self.target_opt1_edit, 2, 1)
        grid_settings.addWidget(QLabel("\ub300\uc0c12 \uc774\ub984:"), 2, 2)
        grid_settings.addWidget(self.target_opt2_edit, 2, 3)
        layout.addWidget(grp_settings)

        # Targets (user selectable)
        self.grp_check = QGroupBox("\uc9d1\uacc4 \ub300\uc0c1 \uc120\ud0dd")
        self.grp_check.setStyleSheet("font-weight: bold; background-color: white;")
        grid_check = QGridLayout(self.grp_check)
        self.chk_target1 = QCheckBox("\ub300\uc0c11")
        self.chk_target2 = QCheckBox("\ub300\uc0c12")
        self.chk_target1.stateChanged.connect(self.on_target_check_changed)
        self.chk_target2.stateChanged.connect(self.on_target_check_changed)
        grid_check.addWidget(self.chk_target1, 0, 0)
        grid_check.addWidget(self.chk_target2, 1, 0)
        layout.addWidget(self.grp_check)

        self.lbl_title = QLabel("")
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.lbl_title)

        # Results table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "\uc548\uac74\uba85", "\ucc2c\uc131(1)", "\ubc18\ub300(2)", "\uae30\uad8c/\ubb34\ud6a8"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setStyleSheet("""
            QHeaderView::section { background-color: #E1F5FE; border: 1px solid #90CAF9; font-weight: bold; }
            QTableWidget { gridline-color: #ccc; font-size: 13px; }
        """)
        self.table.itemChanged.connect(self.on_table_item_changed)
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("\uacb0\uacfc \uc0c8\ub85c\uace0\uce68")
        self.btn_refresh.setMinimumHeight(40)
        self.btn_refresh.setStyleSheet("background-color: #E8F5E9; font-weight: bold;")
        self.btn_refresh.clicked.connect(self.load_data)

        self.btn_export = QPushButton("\uc5d1\uc140 \ub0b4\ubcf4\ub0b4\uae30")
        self.btn_export.setMinimumHeight(40)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_export)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def set_db_path(self, path):
        self.current_db_path = path

        title = self.db.get_setting(self.current_db_path, "vote_count_title", "")
        q_count = self.db.get_setting(self.current_db_path, "vote_count_q_count", "5")
        target_title = self.db.get_setting(self.current_db_path, "vote_target_title", "\uc9d1\uacc4 \ub300\uc0c1 \uc120\ud0dd")
        target_opt1 = self.db.get_setting(self.current_db_path, "vote_target_opt1", "\ub300\uc0c11")
        target_opt2 = self.db.get_setting(self.current_db_path, "vote_target_opt2", "\ub300\uc0c12")
        target_chk1 = self.db.get_setting(self.current_db_path, "vote_target_chk1", "1")
        target_chk2 = self.db.get_setting(self.current_db_path, "vote_target_chk2", "1")

        self.title_edit.blockSignals(True)
        self.count_spin.blockSignals(True)
        self.target_title_edit.blockSignals(True)
        self.target_opt1_edit.blockSignals(True)
        self.target_opt2_edit.blockSignals(True)
        self.chk_target1.blockSignals(True)
        self.chk_target2.blockSignals(True)

        self.title_edit.setText(title)
        try:
            self.count_spin.setValue(int(q_count))
        except ValueError:
            self.count_spin.setValue(5)
        self.target_title_edit.setText(target_title)
        self.target_opt1_edit.setText(target_opt1)
        self.target_opt2_edit.setText(target_opt2)
        self.chk_target1.setChecked(str(target_chk1) == "1")
        self.chk_target2.setChecked(str(target_chk2) == "1")

        self.title_edit.blockSignals(False)
        self.count_spin.blockSignals(False)
        self.target_title_edit.blockSignals(False)
        self.target_opt1_edit.blockSignals(False)
        self.target_opt2_edit.blockSignals(False)
        self.chk_target1.blockSignals(False)
        self.chk_target2.blockSignals(False)

        self.on_title_changed(self.title_edit.text())
        self.on_target_title_changed(self.target_title_edit.text())
        self.on_target_opt1_changed(self.target_opt1_edit.text())
        self.on_target_opt2_changed(self.target_opt2_edit.text())
        self.load_data()

    def load_data(self):
        if not self.current_db_path:
            return

        q_count = self.count_spin.value()
        stats = self.db.get_vote_counts(self.current_db_path, q_count=q_count)
        names = self._get_item_names(q_count)

        self._updating_table = True
        self.table.setRowCount(len(stats))
        for row, (q_num, counts) in enumerate(stats.items()):
            name_text = names[row] if row < len(names) else f"{q_num}\ubc88 \uc548\uac74"
            self.table.setItem(row, 0, self._name_item(name_text))
            self.table.setItem(row, 1, self._item(str(counts["1"])))
            self.table.setItem(row, 2, self._item(str(counts["2"])))
            others = counts["0"] + counts["3"]
            self.table.setItem(row, 3, self._item(str(others)))
        self._updating_table = False

    def on_q_count_changed(self, value):
        if self.current_db_path:
            self.db.save_setting(self.current_db_path, "vote_count_q_count", value)
        self.load_data()

    def on_title_changed(self, text):
        self.lbl_title.setText(text.strip())
        if self.current_db_path:
            self.db.save_setting(self.current_db_path, "vote_count_title", text)

    def on_target_title_changed(self, text):
        self.grp_check.setTitle(text.strip() or "\uc9d1\uacc4 \ub300\uc0c1 \uc120\ud0dd")
        if self.current_db_path:
            self.db.save_setting(self.current_db_path, "vote_target_title", text)

    def on_target_opt1_changed(self, text):
        self.chk_target1.setText(text.strip() or "\ub300\uc0c11")
        if self.current_db_path:
            self.db.save_setting(self.current_db_path, "vote_target_opt1", text)

    def on_target_opt2_changed(self, text):
        self.chk_target2.setText(text.strip() or "\ub300\uc0c12")
        if self.current_db_path:
            self.db.save_setting(self.current_db_path, "vote_target_opt2", text)

    def on_target_check_changed(self, _state=None):
        if self.current_db_path:
            self.db.save_setting(self.current_db_path, "vote_target_chk1", "1" if self.chk_target1.isChecked() else "0")
            self.db.save_setting(self.current_db_path, "vote_target_chk2", "1" if self.chk_target2.isChecked() else "0")

    def on_table_item_changed(self, item):
        if self._updating_table or not self.current_db_path:
            return
        if item.column() != 0:
            return
        names = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            names.append(name_item.text().strip() if name_item else "")
        self.db.save_setting(self.current_db_path, "vote_item_names", "|".join(names))

    def _get_item_names(self, q_count):
        raw = self.db.get_setting(self.current_db_path, "vote_item_names", "")
        names = [s.strip() for s in raw.split("|")] if raw else []
        result = []
        for i in range(q_count):
            if i < len(names) and names[i]:
                result.append(names[i])
            else:
                result.append(f"{i+1}\ubc88 \uc548\uac74")
        return result

    def _item(self, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _name_item(self, text):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        return item

