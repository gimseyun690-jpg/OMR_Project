from PySide2.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QSpinBox,
    QDoubleSpinBox,
    QPushButton,
    QMessageBox,
    QGroupBox,
)

from database import DBManager


class MarkSettingsDialog(QDialog):
    def __init__(self, parent=None, db_path=None):
        super().__init__(parent)
        self.setWindowTitle("OMR Mark Settings")
        self.resize(420, 280)
        self.db = DBManager()
        self.db_path = db_path

        self.init_ui()
        self.load_data()

    def init_ui(self):
        layout = QVBoxLayout()

        grp = QGroupBox("Recognition Parameters")
        form = QFormLayout()

        self.sb_threshold = QSpinBox()
        self.sb_threshold.setRange(0, 255)
        self.sb_threshold.setSingleStep(5)
        self.sb_threshold.setToolTip("Marker threshold for timing-mark detection. Default: 120")
        form.addRow("Threshold:", self.sb_threshold)

        self.sb_c = QSpinBox()
        self.sb_c.setRange(0, 30)
        self.sb_c.setSingleStep(1)
        self.sb_c.setToolTip("AdaptiveThreshold C value. Default: 7")
        form.addRow("C:", self.sb_c)

        self.sb_pixel_ratio = QDoubleSpinBox()
        self.sb_pixel_ratio.setRange(0.0, 1.0)
        self.sb_pixel_ratio.setDecimals(3)
        self.sb_pixel_ratio.setSingleStep(0.01)
        self.sb_pixel_ratio.setToolTip("Mark fill ratio threshold. Default: 0.05")
        form.addRow("Pixel Ratio:", self.sb_pixel_ratio)

        grp.setLayout(form)
        layout.addWidget(grp)

        info = QLabel("Defaults: threshold=120, C=7, pixel_ratio=0.05")
        info.setStyleSheet("color: #1E6BB8;")
        layout.addWidget(info)

        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save_data)
        layout.addWidget(btn_save)

        self.setLayout(layout)

    def load_data(self):
        if not self.db_path:
            return
        thresh = self.db.get_setting(self.db_path, "omr_threshold", "120")
        c_value = self.db.get_setting(self.db_path, "omr_c", "7")
        ratio = self.db.get_setting(self.db_path, "omr_pixel_ratio", "0.05")

        self.sb_threshold.setValue(int(float(thresh)))
        self.sb_c.setValue(int(float(c_value)))
        self.sb_pixel_ratio.setValue(float(ratio))

    def save_data(self):
        if not self.db_path:
            return
        self.db.save_setting(self.db_path, "omr_threshold", self.sb_threshold.value())
        self.db.save_setting(self.db_path, "omr_c", self.sb_c.value())
        self.db.save_setting(self.db_path, "omr_pixel_ratio", self.sb_pixel_ratio.value())
        QMessageBox.information(self, "Saved", "OMR mark settings saved.")
        self.accept()
