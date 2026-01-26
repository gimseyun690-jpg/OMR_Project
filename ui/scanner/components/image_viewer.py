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

        # 이미지 출력 라벨
        self.lbl = QLabel()
        self.lbl.setAlignment(Qt.AlignCenter)
        self.lbl.setFixedSize(width, height)
        self.lbl.setStyleSheet(
            "background-color: #eee;"
            "background-image: linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc),"
            "linear-gradient(45deg, #ccc 25%, transparent 25%, transparent 75%, #ccc 75%, #ccc);"
            "background-size: 20px 20px;"
            "background-position: 0 0, 10px 10px;"
            "border: 1px solid #888;"
        )
        layout.addWidget(self.lbl)
        self.setLayout(layout)

    def set_image_path(self, image_path: str):
        """이미지 파일 경로를 받아 즉시 표시"""
        if not image_path or not os.path.exists(image_path):
            self.clear()
            return
        try:
            img_array = np.fromfile(image_path, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            self.set_image_cv(img)
        except Exception:
            self.clear()

    def set_image_cv(self, image_cv):
        """OpenCV 이미지(numpy)를 받아 표시"""
        if image_cv is None:
            self.clear()
            return
        # 고화질 필요 없으므로 라벨 크기에 맞게 축소 후 변환
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
        """이미지 초기화"""
        self._pixmap = None
        self.lbl.clear()

    def resizeEvent(self, event):
        # 리사이즈 시 현재 이미지 비율 유지
        self._refresh()
        super().resizeEvent(event)

    def _refresh(self):
        """현재 pixmap을 라벨 크기에 맞게 리스케일"""
        if not self._pixmap:
            return
        scaled = self._pixmap.scaled(self.lbl.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.lbl.setPixmap(scaled)

