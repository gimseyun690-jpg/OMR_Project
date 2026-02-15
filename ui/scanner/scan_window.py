from PySide2.QtWidgets import QWidget
from PySide2.QtCore import Signal, QThreadPool, QTimer

from logic.omr_engine import OMREngine
from logic.services.scan_service import ScanService
from logic.services.scan_session_controller import ScanSessionController
from ui.scanner.handlers.scan_flow import ScanFlowMixin
from ui.scanner.handlers.demo_flow import DemoFlowMixin
from ui.scanner.handlers.review_flow import ReviewFlowMixin
from ui.scanner.handlers.grid_sync import GridSyncMixin
from ui.scanner.handlers.ui_setup import UiSetupMixin


class ScannerReadingView(QWidget, UiSetupMixin, GridSyncMixin, ReviewFlowMixin, DemoFlowMixin, ScanFlowMixin):
    closed_signal = Signal()

    def set_project_db(self, db_path):
        self.set_current_db(db_path)

    def __init__(self, parent=None):
        super().__init__(parent)


        # 초기 변수 초기화
        self.total_read = 0
        self.next_read_num = 1
        self.worker = None
        self.session_start_read_num = 1
        self.session_end_read_num = 0
        self.thread_pool = QThreadPool()
        self.scan_in_progress = False
        self._stop_requested = False
        self.pending_results = {}
        self.next_emit_read_num = 1
        self.pending_analyze = 0
        self.last_scan_params = None
        self.last_error_code = ""
        self.show_error_popups = True
        self.current_summary_row = None
        self.session_start_room_text = None
        self._summary_refresh_timer = QTimer(self)
        self._summary_refresh_timer.setSingleShot(True)
        self._summary_refresh_timer.timeout.connect(self._refresh_summary_async)
        self._summary_task_running = False
        self._summary_refresh_pending = False
        self._grid_block_changes = False

        # 서비스 + 컨트롤러 (UI는 컨트롤러만 호출)
        self.service = ScanService()
        self.controller = ScanSessionController(self.service)
        self.pipeline = self.controller.pipeline

        # 엔진 & DB 매니저 생성
        self.engine = OMREngine()  # 로컬 미리보기/도우미 용도
        self.db = self.controller.db
        self.current_db_path = None  # 현재 열려있는 DB 경로
        
        # [중요] 기준 좌표 (find.py에서 검출한 타이밍 마크 위치) - 필요 시 조정
        self.ref_anchor = (100, 500) 

        # UI 초기화
        self.init_ui()
        self.connect_signals()

