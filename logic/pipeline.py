# logic/pipeline.py
import os
from datetime import datetime

from database import DBManager
from logic.omr_engine import OMREngine

DEFAULT_SCAN_DIR = os.path.join(os.getcwd(), "data", "scan_images")


class ScanPipeline:
    """
    UI는 이 파이프라인만 호출하도록 만드는 게 목표.
    - 이미지 1장 들어오면: (선택)판독 -> DB저장 -> UI에 row_data 반환
    """

    def __init__(self):
        self.db = DBManager()
        self.omr = OMREngine()

        # 실행 컨텍스트(메인에서 선택되는 값들)
        self.project_db_path: str | None = None
        self.scan_dir: str = DEFAULT_SCAN_DIR

        # 기본값(나중에 UI 설정 탭과 연결)
        self.place: str = "스캐너1"
        self.room: str = "1"
        self.sheet_code: str = "1"

        # 폼/ROI (현재 프로젝트에는 폼정의가 없으므로 None으로 둠)
        self.questions_rois = None

        self._read_num = 0

    def set_project(self, project_db_path: str | None):
        self.project_db_path = project_db_path

    def set_scan_dir(self, scan_dir: str):
        self.scan_dir = scan_dir

    def reset_counter(self):
        self._read_num = 0

    def process_image(self, image_path: str, source: str = "스캔") -> list[str]:
        """
        :return: DataGrid에 바로 꽂을 row_data (컬럼 9개)
        """
        self._read_num += 1
        filename = os.path.basename(image_path)

        # 1) (선택) OMR 판독
        mark_status = "대기"
        mark_content = "-"
        check_state = "완료"

        if self.questions_rois:
            final_status, sheet_results, _debug_img = self.omr.analyze_sheet(image_path, self.questions_rois)
            mark_status = "정상" if final_status == "정상" else "오류"

            # 예: 각 문항의 marked 인덱스를 간단 문자열로(추후 원하는 포맷으로 변경 가능)
            # 정상: "1:0,2:1,3:0" / 공란/중복: 표시 포함
            parts = []
            for r in sheet_results:
                q = r["q_num"]
                st = r["status"]
                mk = r["marked"]
                parts.append(f"{q}:{mk}({st})")
            mark_content = " | ".join(parts) if parts else "-"

        # 2) DB 저장 (프로젝트 DB가 선택되어 있을 때만)
        if self.project_db_path:
            self.db.insert_scan_result(
                self.project_db_path,
                data={
                    "read_num": self._read_num,
                    "place": self.place,
                    "room": self.room,
                    "path": image_path,
                },
            )

        # 3) UI 그리드 row_data (DataGrid 컬럼 순서와 100% 일치)
        row_data = [
            str(self._read_num),     # 판독번호
            str(self.sheet_code),    # 용지코드
            self.place,              # 판독고사장
            str(self.room),          # 판독시험실
            source if source != "스캔" else mark_status,  # 표기오류(현재는 상태로 사용)
            check_state,             # 점검구분
            mark_content,            # 표기내용
            image_path,              # 앞면경로
            filename,                # 앞면파일명
        ]
        return row_data
