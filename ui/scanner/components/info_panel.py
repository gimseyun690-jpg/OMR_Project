from PyQt5.QtWidgets import QGroupBox, QLabel, QGridLayout, QFrame
from PyQt5.QtCore import Qt

class InfoPanel(QGroupBox):
    def __init__(self):
        super().__init__()
        self.setTitle("판독 현황")
        self.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #aaa; margin-top: 10px; }")
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()

        # 1. 스타일 설정 (글자 크기, 색상)
        style_title = "color: #555; font-size: 12px;"
        style_data = "color: blue; font-size: 18px; font-weight: bold;"
        style_red = "color: red; font-size: 18px; font-weight: bold;"

        # 2. 라벨 생성
        self.lbl_total = QLabel("0"); self.lbl_total.setStyleSheet(style_data)
        self.lbl_place = QLabel("-"); self.lbl_place.setStyleSheet(style_data)
        self.lbl_room = QLabel("1"); self.lbl_room.setStyleSheet(style_data)
        self.lbl_temp = QLabel("0"); self.lbl_temp.setStyleSheet(style_red)

        # 3. 배치 (행, 열)
        layout.addWidget(QLabel("총 판독매수:", styleSheet=style_title), 0, 0)
        layout.addWidget(self.lbl_total, 1, 0)
        
        layout.addWidget(QLabel("현재 고사장:", styleSheet=style_title), 0, 1)
        layout.addWidget(self.lbl_place, 1, 1)

        layout.addWidget(QLabel("현재 시험실:", styleSheet=style_title), 0, 2)
        layout.addWidget(self.lbl_room, 1, 2)
        
        layout.addWidget(QLabel("임시 판독매수:", styleSheet=style_title), 0, 3)
        layout.addWidget(self.lbl_temp, 1, 3)

        self.setLayout(layout)

    def update_info(self, total, place, room, temp):
        """외부에서 정보를 갱신할 때 호출하는 함수"""
        self.lbl_total.setText(str(total))
        self.lbl_place.setText(place)
        self.lbl_room.setText(str(room))
        self.lbl_temp.setText(str(temp))