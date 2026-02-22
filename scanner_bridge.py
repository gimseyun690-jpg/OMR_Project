from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import cv2
import numpy as np


class ScannerBridgeError(RuntimeError):
    """Base exception for scanner IPC bridge failures."""


class ScannerWorkerTimeoutError(ScannerBridgeError):
    """Raised when the 32-bit worker does not respond before timeout."""


class ScannerWorkerProcessError(ScannerBridgeError):
    """Raised when the 32-bit worker exits abnormally."""


class ScannerWorkerOutputError(ScannerBridgeError):
    """Raised when worker stdout does not contain a valid output file path."""


class ScannerImageLoadError(ScannerBridgeError):
    """Raised when the scanned image file cannot be loaded by OpenCV."""


@dataclass
class ScanRequest:
    dpi: int = 300
    color_mode: str = "color"  # color | gray | bw
    width: int = 1240
    height: int = 1754
    extra_args: Optional[Sequence[str]] = None
    timeout_sec: Optional[float] = None


class ScannerBridge:
    """
    Launches a 32-bit scanner worker process and returns a cv2 image (numpy array)
    to the 64-bit main process.

    The bridge is intentionally isolated from UI code so it can be reused from
    PyQt/PySide event handlers, services, or batch tasks.
    """

    def __init__(
        self,
        python32_exe: str | Path,
        worker_script: str | Path,
        timeout_sec: float = 30.0,
        temp_root: str | Path | None = None,
    ) -> None:
        self.python32_exe = Path(python32_exe).resolve()
        self.worker_script = Path(worker_script).resolve()
        self.timeout_sec = float(timeout_sec)
        self.temp_root = Path(temp_root).resolve() if temp_root else None

        if not self.python32_exe.exists():
            raise FileNotFoundError(f"32-bit python executable not found: {self.python32_exe}")
        if not self.worker_script.exists():
            raise FileNotFoundError(f"Scanner worker script not found: {self.worker_script}")

    def scan_image(
        self,
        dpi: int = 300,
        color_mode: str = "color",
        width: int = 1240,
        height: int = 1754,
        timeout_sec: Optional[float] = None,
        extra_args: Optional[Sequence[str]] = None,
        keep_temp_file: bool = False,
    ) -> np.ndarray:
        request = ScanRequest(
            dpi=int(dpi),
            color_mode=str(color_mode),
            width=int(width),
            height=int(height),
            extra_args=extra_args,
            timeout_sec=timeout_sec,
        )
        return self._scan_image_request(request=request, keep_temp_file=keep_temp_file)

    def _scan_image_request(self, request: ScanRequest, keep_temp_file: bool = False) -> np.ndarray:
        temp_dir = self._make_temp_dir()
        worker_output_path: Optional[Path] = None

        try:
            command = self._build_command(output_dir=temp_dir, request=request)
            stdout_text, stderr_text, return_code = self._run_worker(
                command=command,
                timeout_sec=(self.timeout_sec if request.timeout_sec is None else float(request.timeout_sec)),
            )

            if return_code != 0:
                raise ScannerWorkerProcessError(
                    self._format_process_error(
                        message=f"Scanner worker exited with code {return_code}",
                        command=command,
                        stdout_text=stdout_text,
                        stderr_text=stderr_text,
                    )
                )

            worker_output_path = self._parse_output_path(stdout_text)
            if not worker_output_path.exists():
                raise ScannerWorkerOutputError(
                    f"Worker returned path but file does not exist: {worker_output_path}\n"
                    f"stdout={stdout_text!r}\nstderr={stderr_text!r}"
                )

            image = self._load_image_unicode(worker_output_path)
            if image is None:
                raise ScannerImageLoadError(f"OpenCV failed to load scanned image: {worker_output_path}")

            return image
        finally:
            if worker_output_path is not None and (not keep_temp_file):
                self._safe_unlink(worker_output_path)
            if not keep_temp_file:
                self._safe_rmtree(temp_dir)

    def _make_temp_dir(self) -> Path:
        root = str(self.temp_root) if self.temp_root else None
        path = tempfile.mkdtemp(prefix="omr_scan_", dir=root)
        return Path(path).resolve()

    def _build_command(self, output_dir: Path, request: ScanRequest) -> List[str]:
        cmd = [
            str(self.python32_exe),
            str(self.worker_script),
            "--dpi",
            str(int(request.dpi)),
            "--color-mode",
            str(request.color_mode),
            "--output-dir",
            str(output_dir),
            "--width",
            str(int(request.width)),
            "--height",
            str(int(request.height)),
        ]
        if request.extra_args:
            cmd.extend([str(x) for x in request.extra_args])
        return cmd

    def _run_worker(self, command: Sequence[str], timeout_sec: float) -> tuple[str, str, int]:
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        proc = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )

        try:
            stdout_text, stderr_text = proc.communicate(timeout=max(0.1, float(timeout_sec)))
        except subprocess.TimeoutExpired:
            self._terminate_process(proc)
            stdout_text, stderr_text = proc.communicate()
            raise ScannerWorkerTimeoutError(
                self._format_process_error(
                    message=f"Scanner worker timed out after {timeout_sec:.2f}s",
                    command=command,
                    stdout_text=stdout_text,
                    stderr_text=stderr_text,
                )
            )
        except Exception:
            self._terminate_process(proc)
            raise

        return stdout_text, stderr_text, int(proc.returncode if proc.returncode is not None else -1)

    @staticmethod
    def _terminate_process(proc: subprocess.Popen) -> None:
        try:
            proc.kill()
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass

    @staticmethod
    def _parse_output_path(stdout_text: str) -> Path:
        lines = [line.strip() for line in str(stdout_text or "").splitlines() if line.strip()]
        if not lines:
            raise ScannerWorkerOutputError("Scanner worker produced no stdout output path")

        # Worker contract: final stdout line is the file path.
        candidate = Path(lines[-1]).expanduser()
        if not candidate.is_absolute():
            candidate = candidate.resolve()
        return candidate

    @staticmethod
    def _load_image_unicode(path: Path) -> Optional[np.ndarray]:
        # cv2.imread may fail with non-ASCII paths on Windows. Use fromfile+imdecode.
        try:
            raw = np.fromfile(str(path), dtype=np.uint8)
            if raw.size == 0:
                return None
            return cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
        except Exception:
            return None

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)  # Python 3.8+: missing_ok exists on Path.unlink in 3.8+
        except TypeError:
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def _safe_rmtree(path: Path) -> None:
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _format_process_error(
        message: str,
        command: Sequence[str],
        stdout_text: str,
        stderr_text: str,
    ) -> str:
        return (
            f"{message}\n"
            f"command={' '.join(map(str, command))}\n"
            f"stdout={stdout_text!r}\n"
            f"stderr={stderr_text!r}"
        )


if __name__ == "__main__":
    # Minimal manual smoke test (run from 64-bit Python env)
    # Example:
    #   py -3.10-64 scanner_bridge.py "C:\\Python310-32\\python.exe"
    import sys

    if len(sys.argv) < 2:
        print("Usage: python scanner_bridge.py <path-to-32bit-python.exe>")
        raise SystemExit(1)

    py32 = Path(sys.argv[1])
    worker = Path(__file__).with_name("scanner_worker_32.py")
    bridge = ScannerBridge(py32, worker, timeout_sec=10.0)
    img = bridge.scan_image(dpi=300, color_mode="color")
    print(f"Loaded image shape={None if img is None else img.shape}, dtype={None if img is None else img.dtype}")
