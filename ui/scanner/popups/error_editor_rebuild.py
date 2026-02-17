# -*- coding: utf-8 -*-
from ui.scanner.popups.error_editor_base import BaseErrorCorrectionDialog


class RebuildErrorCorrectionDialog(BaseErrorCorrectionDialog):
    def __init__(self, parent=None, image_cv=None, scan_results=None, image_path=""):
        super().__init__(
            parent=parent,
            image_cv=image_cv,
            scan_results=scan_results,
            image_path=image_path,
            title="재개발선거 오류 조회/수정",
            choice_labels=["찬성", "반대"],
        )
