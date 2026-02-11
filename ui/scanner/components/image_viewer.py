import os
import cv2
import numpy as np
from PySide2.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide2.QtCore import Qt
from PySide2.QtGui import QPixmap, QImage


class ImageViewer(QWidget):
    def __init__(self, width=200, height=210):
        super().__init__()
        self._pixmap = None
        self._init_ui(width, height)

    def _init_ui(self, width, height):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setFixedSize(width, height)
        self.lbl.setStyleSheet(
            "background-color: #FFFFFF;"
            "border: 1px solid #888;"
        )
        layout.addWidget(self.lbl)
        self.setLayout(layout)

    def set_image_path(self, image_path: str, engine=None, use_warp: bool = False):
        if not image_path or not os.path.exists(image_path):
            self.clear()
            return
        try:
            img_array = np.fromfile(image_path, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if use_warp and engine is not None and img is not None:
                try:
                    aligned_img, ok, _ = engine.align_image_warp(img)
                    if ok and aligned_img is not None:
                        img = aligned_img
                except Exception:
                    pass
            self.set_image_cv(img)
        except Exception:
            self.clear()

    def set_image_cv(self, image_cv):
        if image_cv is None:
            self.clear()
            return
        target_w = self.lbl.width()
        target_h = self.lbl.height()
        if target_w > 0 and target_h > 0:
            image_cv = cv2.resize(image_cv, (target_w, target_h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        bytes_per_line = w * 3
        qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        self._pixmap = pixmap
        self._refresh()

    def clear(self):
        self._pixmap = None
        self.lbl.clear()

    def resizeEvent(self, event):
        self._refresh()
        super().resizeEvent(event)

    def _refresh(self):
        if not self._pixmap:
            return
        scaled = self._pixmap.scaled(self.lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl.setPixmap(scaled)
