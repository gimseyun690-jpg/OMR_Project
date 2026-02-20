from __future__ import annotations

import ctypes
import importlib
import os
from ctypes import wintypes
from datetime import datetime
from typing import Iterable


# Win32 global memory helpers (for TWAIN native transfer handle)
_kernel32 = ctypes.windll.kernel32
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = wintypes.BOOL
_kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalFree.restype = wintypes.HGLOBAL
_kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalSize.restype = ctypes.c_size_t


def _global_lock(hmem):
    return _kernel32.GlobalLock(hmem)


def _global_unlock(hmem):
    return _kernel32.GlobalUnlock(hmem)


def _global_free(hmem):
    return _kernel32.GlobalFree(hmem)


def _global_size(hmem):
    return _kernel32.GlobalSize(hmem)


class _BaseBackend:
    BACKEND_NAME = "base"

    def __init__(self, source_name_hint: str | None = None, vendor_preference: str | None = None):
        self.source_name_hint = str(source_name_hint or "").strip()
        self.vendor_preference = str(vendor_preference or "").strip().upper()
        self.dpi = 150
        self.scanner_name = ""
        self.double_feed_enabled = False

    @property
    def display_name(self) -> str:
        return self.BACKEND_NAME

    def set_dpi(self, dpi: int):
        try:
            self.dpi = int(dpi)
        except Exception:
            self.dpi = 150

    @staticmethod
    def pack_error(code: str, message: str, retryable: bool, auto_retry: bool) -> str:
        return f"SCAN_ERR|{code}|{1 if retryable else 0}|{1 if auto_retry else 0}|{message}"

    def connect(self, hwnd):
        raise NotImplementedError

    def open_scanner(self):
        raise NotImplementedError

    def check_paper(self):
        return True

    def scan(self, save_folder=None):
        raise NotImplementedError

    def close(self):
        pass


class _TwainBackend(_BaseBackend):
    BACKEND_NAME = "twain"

    def __init__(
        self,
        source_name_hint: str | None = None,
        vendor_preference: str | None = None,
        strict_vendor_match: bool = False,
    ):
        super().__init__(source_name_hint=source_name_hint, vendor_preference=vendor_preference)
        self.twain = None
        self.sm = None
        self.source = None
        self.win_dir = os.environ.get("WINDIR", r"C:\Windows")
        self._cc_map = {}
        self.strict_vendor_match = bool(strict_vendor_match)

    @property
    def display_name(self) -> str:
        if self.vendor_preference == "PANASONIC":
            return "panasonic-twain"
        return "twain"

    def _ensure_twain(self):
        if self.twain is not None:
            return True, ""
        try:
            self.twain = importlib.import_module("twain")
            self._build_cc_map()
            return True, ""
        except Exception as e:
            return False, f"TWAIN 모듈 로드 실패: {e}"

    def connect(self, hwnd):
        ok, err = self._ensure_twain()
        if not ok:
            return False, err

        try:
            dsm_name = os.path.join(self.win_dir, "twain_32.dll")
            if not os.path.exists(dsm_name):
                dsm_name = os.path.join(self.win_dir, "SysWOW64", "twain_32.dll")
            self.sm = self.twain.SourceManager(parent_window=hwnd, dsm_name=dsm_name)
            return True, "TWAIN 연결 성공"
        except Exception as e:
            return False, f"TWAIN 연결 실패: {e}"

    def _iter_source_names(self) -> list[str]:
        if not self.sm:
            return []
        method_names = ("GetSourceList", "GetSourceNames", "SourceList")
        for name in method_names:
            fn = getattr(self.sm, name, None)
            if not callable(fn):
                continue
            try:
                raw = fn()
                if isinstance(raw, (list, tuple)):
                    out = [str(v) for v in raw if str(v).strip()]
                    if out:
                        return out
            except Exception:
                pass
        return []

    def _choose_source_name(self) -> tuple[str | None, str]:
        source_names = self._iter_source_names()
        if not source_names:
            if self.strict_vendor_match and self.vendor_preference:
                return None, f"{self.vendor_preference} TWAIN 소스 목록을 찾지 못했습니다."
            return None, ""

        hint = self.source_name_hint.lower()
        hint_match = None
        if hint:
            for name in source_names:
                if hint in name.lower():
                    hint_match = name
                    break

        vendor_match = None
        if self.vendor_preference:
            for name in source_names:
                if self.vendor_preference in name.upper():
                    vendor_match = name
                    break

        if self.strict_vendor_match and self.vendor_preference:
            if vendor_match is None:
                return None, f"{self.vendor_preference} TWAIN 소스를 찾지 못했습니다."
            if hint_match and self.vendor_preference in hint_match.upper():
                return hint_match, ""
            return vendor_match, ""

        if hint_match:
            return hint_match, ""
        if vendor_match:
            return vendor_match, ""
        return None, ""

    def open_scanner(self):
        if not self.sm:
            return False, "TWAIN SourceManager 미연결"

        try:
            source_name, source_select_msg = self._choose_source_name()
            if self.strict_vendor_match and self.vendor_preference and not source_name:
                return False, source_select_msg or f"{self.vendor_preference} TWAIN 소스를 찾지 못했습니다."

            self.source = None
            if source_name:
                try:
                    # py-twain generally supports OpenSource(name)
                    self.source = self.sm.OpenSource(source_name)
                except Exception:
                    self.source = None

            if self.source is None:
                self.source = self.sm.OpenSource()

            if not self.source:
                return False, "스캐너 선택 취소"

            try:
                self.scanner_name = self.source.GetSourceName() or ""
            except Exception:
                self.scanner_name = ""

            self._try_enable_double_feed()
            return True, self.scanner_name if self.scanner_name else "스캐너"
        except Exception as e:
            return False, str(e)

    def check_paper(self):
        if not self.source or self.twain is None:
            return True
        try:
            cap = self.source.GetCapability(self.twain.CAP_FEEDERLOADED)
            if isinstance(cap, (tuple, list)):
                for value in reversed(cap):
                    if isinstance(value, (bool, int)):
                        return bool(value)
            if isinstance(cap, (bool, int)):
                return bool(cap)
            return True
        except Exception:
            return True

    def close(self):
        self.source = None
        self.sm = None

    def scan(self, save_folder=None):
        if save_folder is None:
            save_folder = os.path.join(os.getcwd(), "data", "scan_images")
        os.makedirs(save_folder, exist_ok=True)

        if not self.source or self.twain is None:
            return

        try:
            self.source.SetCapability(self.twain.ICAP_XRESOLUTION, self.twain.TWTY_FIX32, float(self.dpi))
            self.source.SetCapability(self.twain.ICAP_YRESOLUTION, self.twain.TWTY_FIX32, float(self.dpi))
            self.source.SetCapability(self.twain.ICAP_PIXELTYPE, self.twain.TWTY_UINT16, self.twain.TWPT_RGB)
        except Exception:
            pass

        try:
            self.source.RequestAcquire(0, 0)
        except self.twain.exc.DSTransferCancelled:
            return
        except Exception as e:
            code, msg, retryable, auto_retry = self._classify_exception(e)
            raise RuntimeError(self.pack_error(code, msg, retryable, auto_retry))

        try:
            info = self.source.GetImageInfo()
        except Exception:
            info = None

        while info:
            handle = None
            try:
                handle, _ = self.source.XferImageNatively()
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                full_path = os.path.join(save_folder, f"scan_{ts}.bmp")
                self._save_dib_to_bmp(handle, full_path)
                yield full_path
            except self.twain.exc.DSTransferCancelled:
                pass
            except Exception as e:
                code, msg, retryable, auto_retry = self._classify_exception(e)
                raise RuntimeError(self.pack_error(code, msg, retryable, auto_retry))
            finally:
                if handle:
                    _global_free(handle)
                    handle = None

            try:
                info = self.source.GetImageInfo()
            except Exception:
                break

    def _try_enable_double_feed(self):
        if not self.source or self.twain is None:
            return
        try:
            if hasattr(self.twain, "CAP_DOUBLEFEEDDETECTION"):
                self.source.SetCapability(self.twain.CAP_DOUBLEFEEDDETECTION, self.twain.TWTY_UINT16, 1)
            if hasattr(self.twain, "CAP_DOUBLEFEEDDETECTIONRESPONSE"):
                try:
                    self.source.SetCapability(self.twain.CAP_DOUBLEFEEDDETECTIONRESPONSE, self.twain.TWTY_UINT16, 2)
                except Exception:
                    pass
            self.double_feed_enabled = True
        except Exception:
            self.double_feed_enabled = False

    def _build_cc_map(self):
        twain = self.twain
        self._cc_map = {}
        if twain is None:
            return

        def add(name, code, msg):
            if code is not None:
                self._cc_map[int(code)] = (name, msg)

        add("DF", getattr(twain, "TWCC_DOUBLEFEED", None), "이중 급지가 감지되었습니다. 용지를 확인 후 다시 스캔하세요.")
        add("JAM", getattr(twain, "TWCC_PAPERJAM", None), "용지 걸림이 발생했습니다. 스캐너 내부를 확인하세요.")
        add("COVER", getattr(twain, "TWCC_PAPERLIGHT", None), "커버 열림 또는 급지 문제입니다. 장비 상태를 확인하세요.")
        add("NO_PAPER", getattr(twain, "TWCC_NODS", None), "급지대에 용지가 없습니다.")
        add("BAD_PAPER", getattr(twain, "TWCC_BADVALUE", None), "용지/설정 값 오류입니다.")
        add("OPERATION", getattr(twain, "TWCC_OPERATIONERROR", None), "스캐너 동작 중 오류가 발생했습니다.")
        add("BUSY", getattr(twain, "TWCC_BUSY", None), "스캐너가 사용 중입니다. 잠시 후 다시 시도하세요.")
        add("MEMORY", getattr(twain, "TWCC_LOWMEMORY", None), "메모리 부족으로 스캔 실패했습니다.")
        add("FORMAT", getattr(twain, "TWCC_BADFORMAT", None), "전송 포맷 오류로 스캔 실패했습니다.")

    def _get_condition_code(self):
        if not self.source:
            return None
        try:
            status = self.source.GetStatus()
        except Exception:
            return None
        if isinstance(status, (tuple, list)):
            for value in reversed(status):
                if isinstance(value, int):
                    return value
        if isinstance(status, int):
            return status
        return None

    def _classify_exception(self, e):
        msg = str(e)
        msg_lower = msg.lower()

        cc = self._get_condition_code()
        if cc is not None and cc in self._cc_map:
            code, user_msg = self._cc_map[cc]
            retryable = code not in ("DF", "JAM", "NO_PAPER", "COVER")
            auto_retry = code in ("BUSY",)
            return code, user_msg, retryable, auto_retry

        if any(k in msg_lower for k in ("double", "multi", "multifeed", "doublefeed")):
            return "DF", "이중 급지가 감지되었습니다. 용지를 확인 후 다시 스캔하세요.", False, False
        if "jam" in msg_lower:
            return "JAM", "용지 걸림이 발생했습니다. 스캐너 내부를 확인하세요.", False, False
        if "cover" in msg_lower or "open" in msg_lower:
            return "COVER", "커버 열림/장비 커버를 확인하세요.", False, False
        if "no paper" in msg_lower or "empty" in msg_lower:
            return "NO_PAPER", "급지대에 용지가 없습니다.", False, False
        if "busy" in msg_lower:
            return "BUSY", "스캐너가 사용 중입니다. 잠시 후 다시 시도하세요.", True, True
        if "cancel" in msg_lower:
            return "CANCEL", "사용자에 의해 스캔이 취소되었습니다.", False, False

        return "UNKNOWN", f"스캐너 오류: {msg}", True, False

    def _save_dib_to_bmp(self, handle, filepath):
        lock_ptr = _global_lock(handle)
        if not lock_ptr:
            raise RuntimeError("GlobalLock failed")

        try:
            size = _global_size(handle)
            if not size or size < 40:
                raise RuntimeError(f"Invalid DIB size: {size}")

            dib = ctypes.string_at(lock_ptr, size)
            bi_size = int.from_bytes(dib[0:4], "little", signed=False)
            if bi_size < 40 or bi_size > size:
                raise RuntimeError(f"Invalid DIB header size: {bi_size}")

            bpp = int.from_bytes(dib[14:16], "little", signed=False)
            compression = int.from_bytes(dib[16:20], "little", signed=False)
            clr_used = int.from_bytes(dib[32:36], "little", signed=False)

            if clr_used != 0:
                colors = clr_used
            elif bpp in (1, 4, 8):
                colors = 1 << bpp
            else:
                colors = 0
            palette_size = colors * 4

            masks_size = 0
            if bi_size == 40:
                if compression == 3:
                    masks_size = 12
                elif compression == 6:
                    masks_size = 16

            dib_pixel_offset = bi_size + masks_size + palette_size
            if dib_pixel_offset < bi_size or dib_pixel_offset > size:
                dib_pixel_offset = min(max(14 + bi_size, bi_size), size)

            bf_off_bits = 14 + dib_pixel_offset
            bf_size = 14 + size

            with open(filepath, "wb") as f:
                f.write(b"BM")
                f.write(bf_size.to_bytes(4, "little", signed=False))
                f.write((0).to_bytes(2, "little", signed=False))
                f.write((0).to_bytes(2, "little", signed=False))
                f.write(bf_off_bits.to_bytes(4, "little", signed=False))
                f.write(dib)
        finally:
            _global_unlock(handle)


class _WiaBackend(_BaseBackend):
    BACKEND_NAME = "wia"

    def __init__(self, source_name_hint: str | None = None, vendor_preference: str | None = None):
        super().__init__(source_name_hint=source_name_hint, vendor_preference=vendor_preference)
        self.win32 = None
        self.device_manager = None
        self.device_info = None
        self.device = None

    def _ensure_wia(self):
        if self.win32 is not None:
            return True, ""
        try:
            self.win32 = importlib.import_module("win32com.client")
            return True, ""
        except Exception as e:
            return False, f"WIA(pywin32) 모듈 로드 실패: {e}"

    def connect(self, hwnd):
        del hwnd
        ok, err = self._ensure_wia()
        if not ok:
            return False, err
        try:
            self.device_manager = self.win32.Dispatch("WIA.DeviceManager")
            return True, "WIA 연결 성공"
        except Exception as e:
            return False, f"WIA 연결 실패: {e}"

    @staticmethod
    def _safe_prop(info, name: str):
        try:
            return str(info.Properties(name).Value)
        except Exception:
            return ""

    def _iter_device_infos(self):
        if self.device_manager is None:
            return []
        try:
            return list(self.device_manager.DeviceInfos)
        except Exception:
            return []

    def _pick_device_info(self):
        infos = self._iter_device_infos()
        if not infos:
            return None

        hint = self.source_name_hint.lower()
        if hint:
            for info in infos:
                name = self._safe_prop(info, "Name").lower()
                desc = self._safe_prop(info, "Description").lower()
                if hint in name or hint in desc:
                    return info

        if self.vendor_preference:
            vendor = self.vendor_preference.lower()
            for info in infos:
                name = self._safe_prop(info, "Name").lower()
                desc = self._safe_prop(info, "Description").lower()
                if vendor in name or vendor in desc:
                    return info

        return infos[0]

    def open_scanner(self):
        if self.device_manager is None:
            return False, "WIA DeviceManager 미연결"
        try:
            self.device_info = self._pick_device_info()
            if self.device_info is None:
                return False, "WIA 장치를 찾을 수 없습니다."
            self.device = self.device_info.Connect()
            self.scanner_name = self._safe_prop(self.device_info, "Name")
            return True, self.scanner_name if self.scanner_name else "WIA Scanner"
        except Exception as e:
            return False, str(e)

    def check_paper(self):
        return True

    @staticmethod
    def _set_prop(props, prop_id_or_name, value):
        try:
            props(prop_id_or_name).Value = value
            return True
        except Exception:
            pass
        try:
            props[str(prop_id_or_name)].Value = value
            return True
        except Exception:
            return False

    def _classify_exception(self, e):
        msg = str(e)
        low = msg.lower()
        if "paper" in low and ("empty" in low or "feeder" in low or "no" in low):
            return "NO_PAPER", "급지대에 용지가 없습니다.", False, False
        if "busy" in low:
            return "BUSY", "스캐너가 사용 중입니다. 잠시 후 다시 시도하세요.", True, True
        if "cancel" in low:
            return "CANCEL", "사용자에 의해 스캔이 취소되었습니다.", False, False
        return "UNKNOWN", f"WIA 스캔 오류: {msg}", True, False

    def scan(self, save_folder=None):
        if save_folder is None:
            save_folder = os.path.join(os.getcwd(), "data", "scan_images")
        os.makedirs(save_folder, exist_ok=True)

        if self.device is None:
            return

        # WIA property IDs (commonly used, may vary by driver)
        # 6146/6147: Horizontal/Vertical Resolution
        # 6148/6149: Horizontal/Vertical Start Position
        # 3088: Document Handling Select (feeder/flatbed)
        try:
            item = self.device.Items[1]
        except Exception:
            raise RuntimeError(self.pack_error("OPEN", "WIA 장치 아이템을 가져오지 못했습니다.", True, False))

        self._set_prop(item.Properties, 6146, int(self.dpi))
        self._set_prop(item.Properties, 6147, int(self.dpi))
        self._set_prop(item.Properties, 6148, 0)
        self._set_prop(item.Properties, 6149, 0)
        # Try feeder mode; ignore on unsupported drivers.
        self._set_prop(self.device.Properties, 3088, 1)

        scanned_any = False
        index = 1
        while True:
            try:
                image = item.Transfer()
            except Exception as e:
                code, msg, retryable, auto_retry = self._classify_exception(e)
                # For ADF, no more pages often appears as a generic exception after at least one scan.
                if scanned_any and code in ("NO_PAPER", "CANCEL"):
                    break
                raise RuntimeError(self.pack_error(code, msg, retryable, auto_retry))

            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out = os.path.join(save_folder, f"scan_{ts}_{index:03d}.jpg")
            index += 1
            try:
                image.SaveFile(out)
            except Exception as e:
                raise RuntimeError(self.pack_error("SAVE", f"WIA 이미지 저장 실패: {e}", True, False))

            scanned_any = True
            yield out

            # Conservative: if feeder is unsupported, stop at 1 page.
            if index > 2 and not self._set_prop(self.device.Properties, 3088, 1):
                break

    def close(self):
        self.device = None
        self.device_info = None
        self.device_manager = None


class ScannerDevice:
    """
    Scanner facade with driver/backend fallback.

    Backend preference sources:
    - constructor args
    - env: OMR_SCANNER_BACKEND (auto|panasonic|twain|wia|module:Class)
    - env: OMR_SCANNER_SOURCE_HINT (scanner source/device name hint)
    - env: OMR_SCANNER_BACKEND_ORDER (comma-separated backend order for auto mode)
    """

    DEFAULT_BACKEND_ORDER = ("panasonic", "twain", "wia")

    def __init__(self, backend: str | None = None, source_name_hint: str | None = None, backend_order: Iterable[str] | None = None):
        env_backend = os.environ.get("OMR_SCANNER_BACKEND", "").strip()
        env_source_hint = os.environ.get("OMR_SCANNER_SOURCE_HINT", "").strip()
        env_order = os.environ.get("OMR_SCANNER_BACKEND_ORDER", "").strip()

        self.backend_preference = (backend or env_backend or "auto").strip()
        self.source_name_hint = (source_name_hint or env_source_hint or "").strip()

        if backend_order is None and env_order:
            backend_order = [v.strip() for v in env_order.split(",") if v.strip()]
        self.backend_order = tuple(str(v).strip().lower() for v in (backend_order or self.DEFAULT_BACKEND_ORDER) if str(v).strip())

        self._backend: _BaseBackend | None = None
        self.backend_name = ""
        self.dpi = 150
        self.scanner_name = ""
        self.double_feed_enabled = False

    def set_backend_preference(self, backend: str):
        self.backend_preference = str(backend or "auto").strip()

    def set_source_name_hint(self, source_name_hint: str | None):
        self.source_name_hint = str(source_name_hint or "").strip()

    def set_dpi(self, dpi: int):
        try:
            self.dpi = int(dpi)
        except Exception:
            self.dpi = 150
        if self._backend is not None:
            self._backend.set_dpi(self.dpi)

    def _build_backend(self, backend_name: str) -> _BaseBackend:
        raw = str(backend_name).strip()
        name = raw.lower()
        if name == "panasonic":
            return _TwainBackend(
                source_name_hint=self.source_name_hint,
                vendor_preference="PANASONIC",
                strict_vendor_match=True,
            )
        if name == "twain":
            return _TwainBackend(source_name_hint=self.source_name_hint)
        if name == "wia":
            return _WiaBackend(source_name_hint=self.source_name_hint)

        # plugin: module:ClassName or module:ClassName
        spec = raw
        if spec.lower().startswith("plugin:"):
            spec = spec[len("plugin:") :].strip()
        if ":" not in spec:
            raise ValueError(f"Unsupported scanner backend: {backend_name}")
        module_name, class_name = spec.split(":", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        instance = cls()
        if not isinstance(instance, _BaseBackend):
            # duck typing fallback
            required = ("connect", "set_dpi", "open_scanner", "check_paper", "scan", "close")
            for m in required:
                if not hasattr(instance, m):
                    raise TypeError(f"Plugin backend missing method: {m}")
        return instance

    def _candidate_backends(self) -> list[str]:
        pref = str(self.backend_preference or "").strip()
        if pref and pref.lower() != "auto":
            return [pref]

        candidates = list(self.backend_order or self.DEFAULT_BACKEND_ORDER)
        hint = self.source_name_hint.upper()
        if "PANASONIC" in hint and "panasonic" not in candidates:
            candidates.insert(0, "panasonic")

        deduped = []
        seen = set()
        for name in candidates:
            n = str(name).strip().lower()
            if not n or n in seen:
                continue
            deduped.append(n)
            seen.add(n)
        return deduped or list(self.DEFAULT_BACKEND_ORDER)

    def connect(self, hwnd):
        errors = []
        self._backend = None
        self.backend_name = ""
        self.scanner_name = ""
        self.double_feed_enabled = False

        for candidate in self._candidate_backends():
            try:
                backend = self._build_backend(candidate)
            except Exception as e:
                errors.append(f"{candidate}: 초기화 실패 ({e})")
                continue

            backend.set_dpi(self.dpi)
            ok, msg = backend.connect(hwnd)
            if ok:
                self._backend = backend
                self.backend_name = candidate
                return True, f"[{backend.display_name}] {msg}"
            errors.append(f"{candidate}: {msg}")

        return False, " / ".join(errors) if errors else "사용 가능한 스캐너 드라이버를 찾지 못했습니다."

    def open_scanner(self):
        if self._backend is None:
            return False, "드라이버가 연결되지 않았습니다. connect()를 먼저 호출하세요."
        ok, msg = self._backend.open_scanner()
        if ok:
            self.scanner_name = getattr(self._backend, "scanner_name", "") or ""
            self.double_feed_enabled = bool(getattr(self._backend, "double_feed_enabled", False))
        return ok, msg

    def check_paper(self):
        if self._backend is None:
            return False
        try:
            return bool(self._backend.check_paper())
        except Exception:
            return True

    def scan(self, save_folder=None):
        if self._backend is None:
            return
        yield from self._backend.scan(save_folder=save_folder)

    def close(self):
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:
                pass
        self._backend = None
