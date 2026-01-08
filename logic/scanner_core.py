import twain
import os
import ctypes
from datetime import datetime
from ctypes import wintypes

# 윈도우 API (메모리 잠금용 - 이미지 데이터 가져올 때 필수)
kernel32 = ctypes.windll.kernel32
GlobalLock = kernel32.GlobalLock
GlobalUnlock = kernel32.GlobalUnlock
GlobalSize = kernel32.GlobalSize

class ScannerDevice:
    def __init__(self):
        self.sm = None      # Source Manager
        self.source = None  # Scanner Source
        self.win_dir = os.environ.get('WINDIR', 'C:\\Windows')

    def connect(self, hwnd):
        """
        TWAIN 드라이버 연결 (32비트 DLL 강제 로드)
        :param hwnd: 메인 윈도우의 핸들값 (int)
        """
        try:
            # 1. DLL 경로 찾기 (twain_32.dll)
            dsm_name = os.path.join(self.win_dir, 'twain_32.dll')
            if not os.path.exists(dsm_name):
                dsm_name = os.path.join(self.win_dir, 'SysWOW64', 'twain_32.dll')

            # 2. Source Manager 열기
            self.sm = twain.SourceManager(parent_window=hwnd, dsm_name=dsm_name)
            return True, "TWAIN 연결 성공"
        except Exception as e:
            return False, f"TWAIN 연결 실패: {e}"

    def open_scanner(self, product_name=None):
        """스캐너 장비 선택 및 열기"""
        if not self.sm:
            return False, "Source Manager가 연결되지 않았습니다."

        try:
            if product_name:
                self.source = self.sm.OpenSource(product_name)
            else:
                # 파라미터가 없으면 선택창 띄우기
                self.source = self.sm.OpenSource()
            
            if self.source:
                return True, f"장비 연결됨: {self.source.GetIdentity()['ProductName']}"
            else:
                return False, "장비 선택 취소됨"
        except Exception as e:
            return False, f"장비 열기 오류: {e}"

    def check_paper(self):
        """급지대 종이 감지 (True: 있음, False: 없음)"""
        if not self.source: return False
        try:
            # CAP_FEEDERLOADED 기능값 읽기
            return self.source.GetCapability(twain.CAP_FEEDERLOADED)
        except:
            # 센서 미지원 구형 장비는 항상 True로 가정
            return True

    def scan(self, save_folder="data/scan_images"):
        """
        스캔 실행 및 이미지 저장 (제너레이터)
        한 장 스캔할 때마다 저장된 파일 경로를 yield로 반환
        """
        if not self.source: return

        # 1. 스캔 설정 (150 DPI, 컬러)
        try:
            self.source.SetCapability(twain.ICAP_XRESOLUTION, twain.TWTY_FIX32, 150.0)
            self.source.SetCapability(twain.ICAP_YRESOLUTION, twain.TWTY_FIX32, 150.0)
            self.source.SetCapability(twain.ICAP_PIXELTYPE, twain.TWTY_UINT16, twain.TWPT_RGB)
        except:
            pass

        # 2. 스캔 시작 요청 (UI 숨김)
        self.source.RequestAcquire(0, 0)

        # 3. 이미지 전송 루프
        info = self.source.GetImageInfo()
        while info:
            try:
                # 메모리에서 이미지 데이터 가져오기 (Native Transfer)
                (handle, pointer) = self.source.XferImageNatively()
                
                # 파일명 생성
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"scan_{timestamp}.bmp"
                full_path = os.path.join(save_folder, filename)
                os.makedirs(save_folder, exist_ok=True)

                # DIB(Device Independent Bitmap) 핸들을 BMP 파일로 저장
                self._save_dib_to_bmp(handle, full_path)
                
                # 메모리 해제
                GlobalUnlock(handle)
                kernel32.GlobalFree(handle)
                
                # ★ 중요: UI에게 "파일 저장됐어!"라고 알려줌
                yield full_path

            except twain.exc.DSTransferCancelled:
                break # 사용자가 취소함
            
            # 다음 장 확인
            try:
                info = self.source.GetImageInfo()
            except:
                break

    def close(self):
        """장비 연결 해제"""
        if self.source:
            self.source.destroy()
            self.source = None
        if self.sm:
            self.sm.destroy()
            self.sm = None

    def _save_dib_to_bmp(self, handle, filepath):
        """
        [내부함수] 메모리상의 DIB 데이터를 BMP 파일로 변환 저장
        (TWAIN은 순수 데이터만 주기 때문에 BMP 헤더를 직접 붙여야 함)
        """
        lock = GlobalLock(handle)
        size = GlobalSize(handle)
        
        with open(filepath, "wb") as f:
            # 1. BMP 파일 헤더 작성 (14 bytes)
            # 'BM' 마커
            f.write(b'BM') 
            # 전체 파일 크기 (헤더 14 + DIB 크기)
            f.write((size + 14).to_bytes(4, byteorder='little'))
            # 예약 영역
            f.write((0).to_bytes(2, byteorder='little'))
            f.write((0).to_bytes(2, byteorder='little'))
            
            # 픽셀 데이터 시작 위치 (헤더 14 + DIB Info Header 크기 읽어오기)
            # DIB의 첫 4바이트가 헤더 크기임
            dib_header_size = int.from_bytes(ctypes.string_at(lock, 4), byteorder='little')
            offset = 14 + dib_header_size
            
            # 만약 팔레트가 있으면 offset 조정 필요하지만 24bit RGB는 보통 없음
            # 안전하게 기본 오프셋 계산 (보통 54 byte)
            f.write(offset.to_bytes(4, byteorder='little'))
            
            # 2. DIB 데이터 쓰기
            # ctypes 포인터에서 데이터 읽어서 파일에 쓰기
            data = ctypes.string_at(lock, size)
            f.write(data)
            
        GlobalUnlock(handle)