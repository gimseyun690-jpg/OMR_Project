import twain
import os
import ctypes
from datetime import datetime
from ctypes import wintypes

# ========================================================
# [윈도우 메모리 관리 함수 설정]
# ========================================================
kernel32 = ctypes.windll.kernel32

kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p

# BOOL 반환 (성공/실패 판단 가능)
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.restype = wintypes.HGLOBAL

kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

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
        self.win_dir = os.environ.get('WINDIR', 'C:\\Windows')
        self.double_feed_enabled = False
        self.scanner_name = ""
        self.dpi = 150

        # 스캐너별 예외 메시지 키워드 보정(필요 시 추가)
        self._scanner_keyword_map = {
            "FUJITSU": ["doublefeed", "double feed", "multi feed", "multifeed", "doublefeed"],
            "EPSON": ["doublefeed", "double feed", "multi feed", "multifeed", "doublefeed"],
            "RICOH": ["doublefeed", "double feed", "multi feed", "multifeed", "doublefeed"],
            "CANON": ["doublefeed", "double feed", "multi feed", "multifeed", "doublefeed"],
        }

        # TWAIN condition code -> (code, message)
        self._cc_map = {}
        self._build_cc_map()

    def connect(self, hwnd):
        """TWAIN 드라이버 연결"""
        try:
            dsm_name = os.path.join(self.win_dir, 'twain_32.dll')
            if not os.path.exists(dsm_name):
                dsm_name = os.path.join(self.win_dir, 'SysWOW64', 'twain_32.dll')

            self.sm = twain.SourceManager(parent_window=hwnd, dsm_name=dsm_name)
            return True, "TWAIN 연결 성공"
        except Exception as e:
            return False, f"TWAIN 연결 실패: {e}\n(스캐너 드라이버가 설치되어 있는지 확인하세요)"

    def set_dpi(self, dpi: int):
        try:
            self.dpi = int(dpi)
        except Exception:
            self.dpi = 150

    def open_scanner(self):
        """스캐너 장비 선택 및 열기"""
        if not self.sm:
            return False, "Source Manager 미연결"

        try:
            self.source = self.sm.OpenSource()
            if self.source:
                # 이중 급지 감지(가능한 드라이버에서만 설정됨)
                self._try_enable_double_feed()
                try:
                    self.scanner_name = self.source.GetSourceName() or ""
                except Exception:
                    self.scanner_name = ""
                return True, self.scanner_name if self.scanner_name else "스캐너"
            return False, "스캐너 선택 취소"
        except Exception as e:
            return False, str(e)

    def check_paper(self):
        """급지 확인"""
        if not self.source:
            return False
        try:
            cap = self.source.GetCapability(twain.CAP_FEEDERLOADED)
            # 드라이버/라이브러리에 따라 반환 형태가 다를 수 있어 bool로 정규화
            if isinstance(cap, (tuple, list)):
                # 흔한 형태: (rc, value) or (value,)
                for v in reversed(cap):
                    if isinstance(v, (bool, int)):
                        return bool(v)
            if isinstance(cap, (bool, int)):
                return bool(cap)
            return True
        except:
            return True  # 센서 지원 안하면 그냥 있다고 가정

    def close(self):
        """연결 종료"""
        self.source = None
        self.sm = None

    def scan(self, save_folder=None):
        """스캔 실행 및 저장 (Generator)"""
        if save_folder is None:
            save_folder = os.path.join(os.getcwd(), "data", "scan_images")

        os.makedirs(save_folder, exist_ok=True)

        if not self.source:
            return

        # 1) 스캔 설정 (실패해도 진행)
        try:
            self.source.SetCapability(twain.ICAP_XRESOLUTION, twain.TWTY_FIX32, float(self.dpi))
            self.source.SetCapability(twain.ICAP_YRESOLUTION, twain.TWTY_FIX32, float(self.dpi))
            self.source.SetCapability(twain.ICAP_PIXELTYPE, twain.TWTY_UINT16, twain.TWPT_RGB)
        except:
            pass

        # 2) 스캔 시작 (UI 숨김: 0,0)
        try:
            self.source.RequestAcquire(0, 0)
        except twain.exc.DSTransferCancelled:
            return
        except Exception as e:
            code, msg, retryable, auto_retry = self._classify_exception(e)
            raise RuntimeError(self._pack_error(code, msg, retryable, auto_retry))

        # 3) 전송 루프
        try:
            info = self.source.GetImageInfo()
        except:
            info = None

        file_index = 1

        while info:
            handle = None
            try:
                (handle, _pointer) = self.source.XferImageNatively()

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"scan_{timestamp}.bmp"
                file_index += 1
                full_path = os.path.join(save_folder, filename)

                self._save_dib_to_bmp(handle, full_path)

                yield full_path

            except twain.exc.DSTransferCancelled:
                # 전송 취소 시에도 핸들이 넘어왔다면 해제해야 함
                pass 
            except Exception as e:
                code, msg, retryable, auto_retry = self._classify_exception(e)
                raise RuntimeError(self._pack_error(code, msg, retryable, auto_retry))
            finally:
                # ★ 핵심: 성공하든 실패하든 핸들을 받았다면 무조건 해제
                if handle:
                    GlobalFree(handle)
                    handle = None # 중복 해제 방지

            # 다음 장 확인
            try:
                info = self.source.GetImageInfo()
            except:
                break

    def _try_enable_double_feed(self):
        """드라이버가 지원하면 이중 급지 감지를 활성화"""
        if not self.source:
            return
        try:
            # CAP_DOUBLEFEEDDETECTION (많은 스캐너에서 지원)
            self.source.SetCapability(twain.CAP_DOUBLEFEEDDETECTION, twain.TWTY_UINT16, 1)
            # CAP_DOUBLEFEEDDETECTIONRESPONSE (가능하면 스캔 중단)
            try:
                self.source.SetCapability(twain.CAP_DOUBLEFEEDDETECTIONRESPONSE, twain.TWTY_UINT16, 2)
            except Exception:
                pass
            self.double_feed_enabled = True
        except Exception:
            self.double_feed_enabled = False

    def _build_cc_map(self):
        """TWAIN condition code 매핑 구성(존재하는 상수만 등록)"""
        def _add_cc(name, code, msg):
            if code is not None:
                self._cc_map[code] = (name, msg)

        _add_cc("DF", getattr(twain, "TWCC_DOUBLEFEED", None), "이중 급지 감지됨: 용지를 확인한 뒤 다시 스캔하세요.")
        _add_cc("JAM", getattr(twain, "TWCC_PAPERJAM", None), "용지 걸림(잼) 발생: 스캐너 내부를 확인하세요.")
        _add_cc("COVER", getattr(twain, "TWCC_PAPERLIGHT", None), "커버 열림/용지 감지 문제: 스캐너 상태를 확인하세요.")
        _add_cc("NO_PAPER", getattr(twain, "TWCC_NODS", None), "급지대에 용지가 없습니다.")
        _add_cc("BAD_PAPER", getattr(twain, "TWCC_BADVALUE", None), "용지/설정 값 오류: 스캐너 설정을 확인하세요.")
        _add_cc("OPERATION", getattr(twain, "TWCC_OPERATIONERROR", None), "스캐너 동작 오류가 발생했습니다.")
        _add_cc("BUSY", getattr(twain, "TWCC_BUSY", None), "스캐너가 사용 중입니다. 잠시 후 다시 시도하세요.")
        _add_cc("MEMORY", getattr(twain, "TWCC_LOWMEMORY", None), "메모리 부족으로 스캔 실패.")
        _add_cc("FORMAT", getattr(twain, "TWCC_BADFORMAT", None), "전송 포맷 오류로 스캔 실패.")

    def _pack_error(self, code, msg, retryable, auto_retry):
        return f"SCAN_ERR|{code}|{1 if retryable else 0}|{1 if auto_retry else 0}|{msg}"

    def _get_condition_code(self):
        """TWAIN 상태 코드 조회(지원하는 드라이버만)"""
        if not self.source:
            return None
        try:
            status = self.source.GetStatus()
        except Exception:
            return None

        if isinstance(status, (tuple, list)):
            for v in reversed(status):
                if isinstance(v, int):
                    return v
        if isinstance(status, int):
            return status
        return None

    def _match_scanner_keywords(self, msg_lower: str) -> bool:
        if not msg_lower:
            return False
        name = (self.scanner_name or "").upper()
        for key, words in self._scanner_keyword_map.items():
            if key in name:
                for w in words:
                    if w in msg_lower:
                        return True
        return False

    def _classify_exception(self, e):
        """스캐너 예외를 코드/메시지로 분류"""
        msg = str(e)
        msg_lower = msg.lower()

        # 1) TWAIN condition code 우선
        cc = self._get_condition_code()
        if cc is not None and cc in self._cc_map:
            code, user_msg = self._cc_map[cc]
            retryable = code not in ("DF", "JAM", "NO_PAPER", "COVER")
            auto_retry = code in ("BUSY",)
            return code, user_msg, retryable, auto_retry

        # 2) 메시지 키워드 기반 분류
        if "double" in msg_lower or "multi" in msg_lower or "multifeed" in msg_lower or "doublefeed" in msg_lower:
            return "DF", "이중 급지 감지됨: 용지를 확인한 뒤 다시 스캔하세요.", False, False
        if self._match_scanner_keywords(msg_lower):
            return "DF", "이중 급지 감지됨: 용지를 확인한 뒤 다시 스캔하세요.", False, False
        if "jam" in msg_lower:
            return "JAM", "용지 걸림(잼) 발생: 스캐너 내부를 확인하세요.", False, False
        if "cover" in msg_lower or "open" in msg_lower:
            return "COVER", "커버 열림/장치 커버를 확인하세요.", False, False
        if "no paper" in msg_lower or "empty" in msg_lower or "no feeder" in msg_lower:
            return "NO_PAPER", "급지대에 용지가 없습니다.", False, False
        if "busy" in msg_lower:
            return "BUSY", "스캐너가 사용 중입니다. 잠시 후 다시 시도하세요.", True, True
        if "cancel" in msg_lower:
            return "CANCEL", "사용자에 의해 스캔이 취소되었습니다.", False, False

        # 3) 알 수 없는 오류
        return "UNKNOWN", f"스캐너 오류: {msg}", True, False

    # ---------------------------
    # DIB -> BMP 저장 (정확 버전)
    # ---------------------------
    def _save_dib_to_bmp(self, handle, filepath):
        """
        DIB(HGLOBAL) 메모리를 BMP 파일로 저장.
        - BITMAPFILEHEADER(14) + DIB 전체(byte-for-byte) 기록
        - bfOffBits를 bpp/압축/팔레트/비트필드 고려해서 정확히 계산
        """
        lock_ptr = GlobalLock(handle)
        if not lock_ptr:
            raise RuntimeError("GlobalLock failed")

        try:
            size = GlobalSize(handle)
            if not size or size < 40:
                raise RuntimeError(f"Invalid DIB size: {size}")

            dib = ctypes.string_at(lock_ptr, size)

            # --- DIB 헤더 파싱 ---
            # biSize (DWORD) [0:4]
            biSize = int.from_bytes(dib[0:4], "little", signed=False)
            if biSize < 40 or biSize > size:
                raise RuntimeError(f"Unsupported/invalid DIB header size: {biSize}")

            # BITMAPINFOHEADER 기준 오프셋들
            # biBitCount: WORD at 14
            # biCompression: DWORD at 16
            # biClrUsed: DWORD at 32
            # (biSizeImage: DWORD at 20) <- 필요하면 사용 가능

            bpp = int.from_bytes(dib[14:16], "little", signed=False)
            compression = int.from_bytes(dib[16:20], "little", signed=False)
            clr_used = int.from_bytes(dib[32:36], "little", signed=False)

            # --- 팔레트 크기 계산 ---
            # 팔레트는 RGBQUAD(4 bytes) * colors
            if clr_used != 0:
                colors = clr_used
            else:
                if bpp in (1, 4, 8):
                    colors = 1 << bpp
                else:
                    colors = 0
            palette_size = colors * 4

            # --- 비트필드 마스크 크기 계산 ---
            # compression:
            # BI_RGB = 0
            # BI_RLE8 = 1
            # BI_RLE4 = 2
            # BI_BITFIELDS = 3  (BITMAPINFOHEADER(40)일 때 마스크가 헤더 뒤 12바이트로 붙는 경우)
            # BI_JPEG = 4
            # BI_PNG = 5
            # BI_ALPHABITFIELDS = 6 (경우에 따라 16바이트 마스크)
            masks_size = 0
            if biSize == 40:
                if compression == 3:      # BI_BITFIELDS
                    masks_size = 12
                elif compression == 6:    # BI_ALPHABITFIELDS
                    masks_size = 16
            else:
                # BITMAPV4HEADER(108), BITMAPV5HEADER(124)는 마스크가 헤더 내부에 포함됨
                masks_size = 0

            # --- 픽셀 데이터 시작 오프셋 (DIB 기준) ---
            dib_pixel_offset = biSize + masks_size + palette_size

            # 안전장치
            if dib_pixel_offset < biSize or dib_pixel_offset > size:
                # 드라이버가 비표준으로 주는 경우도 있어서 너무 엄격히 죽이지 말고 fallback
                dib_pixel_offset = min(max(14 + biSize, biSize), size)

            # --- BMP 파일 헤더(BITMAPFILEHEADER) 구성 ---
            # bfType: 'BM' (2)
            # bfSize: 전체 파일 크기 (4)
            # bfReserved1: 0 (2)
            # bfReserved2: 0 (2)
            # bfOffBits: 픽셀 시작 위치 = 14 + dib_pixel_offset (4)
            bfOffBits = 14 + dib_pixel_offset
            bfSize = 14 + size

            with open(filepath, "wb") as f:
                # BITMAPFILEHEADER (14 bytes)
                f.write(b"BM")
                f.write(bfSize.to_bytes(4, "little", signed=False))
                f.write((0).to_bytes(2, "little", signed=False))
                f.write((0).to_bytes(2, "little", signed=False))
                f.write(bfOffBits.to_bytes(4, "little", signed=False))

                # DIB 전체 기록
                f.write(dib)

        finally:
            GlobalUnlock(handle)

