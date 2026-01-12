import twain
import os
import ctypes
from datetime import datetime
from ctypes import wintypes

# ========================================================
# [윈도우 메모리 관리 함수 설정]
# ========================================================
kernel32 = ctypes.windll.kernel32

# 함수 인자/리턴 타입 명시 (안전성을 위해 필수)
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p

kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = None # BOOL이지만 보통 무시

kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

# 편의를 위한 래퍼 함수
def GlobalLock(hMem): return kernel32.GlobalLock(hMem)
def GlobalUnlock(hMem): return kernel32.GlobalUnlock(hMem)
def GlobalFree(hMem): return kernel32.GlobalFree(hMem)
def GlobalSize(hMem): return kernel32.GlobalSize(hMem)

# ========================================================
# [스캐너 클래스]
# ========================================================
class ScannerDevice:
    def __init__(self):
        self.sm = None      # Source Manager
        self.source = None  # Scanner Source
        # 윈도우 기본 경로 찾기
        self.win_dir = os.environ.get('WINDIR', 'C:\\Windows')

    def connect(self, hwnd):
        """TWAIN 드라이버 연결"""
        try:
            # 64비트 파이썬에서도 32비트 TWAIN 드라이버를 로드하기 위한 경로 지정
            dsm_name = os.path.join(self.win_dir, 'twain_32.dll')
            if not os.path.exists(dsm_name):
                dsm_name = os.path.join(self.win_dir, 'SysWOW64', 'twain_32.dll')

            self.sm = twain.SourceManager(parent_window=hwnd, dsm_name=dsm_name)
            return True, "TWAIN 연결 성공"
        except Exception as e:
            return False, f"TWAIN 연결 실패: {e}\n(스캐너 드라이버가 설치되어 있는지 확인하세요)"

    def open_scanner(self):
        """스캐너 장비 선택 및 열기"""
        if not self.sm: return False, "Source Manager 미연결"

        try:
            # 스캐너 선택창 띄우기
            self.source = self.sm.OpenSource()
            if self.source:
                return True, self.source.GetSourceName()
            else:
                return False, "스캐너 선택 취소"
        except Exception as e:
            return False, str(e)

    def check_paper(self):
        """급지 확인"""
        if not self.source: return False
        try:
            return self.source.GetCapability(twain.CAP_FEEDERLOADED)
        except:
            return True # 센서 지원 안하면 그냥 있다고 가정

    def close(self):
        """연결 종료"""
        if self.source:
            # self.source.destroy() # 라이브러리에 따라 필요할수도 없을수도 있음
            self.source = None
        if self.sm:
            # self.sm.destroy()
            self.sm = None

    def scan(self, save_folder=None):
        """스캔 실행 및 저장 (Generator)"""
        # 저장 경로 설정
        if save_folder is None:
            save_folder = os.path.join(os.getcwd(), "data", "scan_images")
        
        if not os.path.exists(save_folder):
            os.makedirs(save_folder, exist_ok=True)

        if not self.source: return

        # 1. 스캔 설정 (150 DPI, 컬러) - 실패해도 계속 진행
        try:
            self.source.SetCapability(twain.ICAP_XRESOLUTION, twain.TWTY_FIX32, 150.0)
            self.source.SetCapability(twain.ICAP_YRESOLUTION, twain.TWTY_FIX32, 150.0)
            self.source.SetCapability(twain.ICAP_PIXELTYPE, twain.TWTY_UINT16, twain.TWPT_RGB)
        except:
            pass

        # 2. 스캔 시작 (UI 숨김: 0, 0 / 보이게 하려면: 1, 0)
        try:
            self.source.RequestAcquire(0, 0)
        except twain.exc.DSTransferCancelled:
            return

        # 3. 이미지 전송 루프
        try:
            info = self.source.GetImageInfo()
        except:
            info = None

        while info:
            try:
                # 메모리 전송
                (handle, pointer) = self.source.XferImageNatively()
                
                # 파일명 생성
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"scan_{timestamp}.bmp"
                full_path = os.path.join(save_folder, filename)

                # BMP 저장
                self._save_dib_to_bmp(handle, full_path)
                
                # 메모리 해제
                GlobalUnlock(handle)
                GlobalFree(handle)
                
                # UI에 알림
                yield full_path

            except twain.exc.DSTransferCancelled:
                break
            except Exception as e:
                print(f"전송 오류: {e}")
                break
            
            # 다음 장 확인
            try:
                info = self.source.GetImageInfo()
            except:
                break

    def _save_dib_to_bmp(self, handle, filepath):
        """DIB 핸들을 BMP 파일로 저장 (간편 방식)"""
        lock = GlobalLock(handle)
        if not lock: return
        
        size = GlobalSize(handle)
        
        with open(filepath, "wb") as f:
            # 1. BMP 헤더 작성 (14 bytes)
            f.write(b'BM') 
            f.write((size + 14).to_bytes(4, byteorder='little')) # 파일 크기
            f.write((0).to_bytes(2, byteorder='little')) # 예약
            f.write((0).to_bytes(2, byteorder='little')) # 예약
            
            # 픽셀 데이터 시작 위치 계산 (헤더크기 14 + DIB헤더크기)
            # DIB 헤더의 첫 4바이트가 DIB 헤더의 크기임
            dib_header_size = int.from_bytes(ctypes.string_at(lock, 4), byteorder='little')
            offset = 14 + dib_header_size
            
            f.write(offset.to_bytes(4, byteorder='little'))
            
            # 2. DIB 데이터 쓰기
            data = ctypes.string_at(lock, size)
            f.write(data)
            
        GlobalUnlock(handle)