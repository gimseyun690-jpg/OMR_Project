from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _clamp_byte(value: int) -> int:
    if value < 0:
        return 0
    if value > 255:
        return 255
    return int(value)


def _generate_rgb_pixels(width: int, height: int, dpi: int) -> bytes:
    """
    Generate a deterministic dummy RGB image (PPM payload).
    This simulates a scanned page without requiring PIL/cv2/numpy.
    """
    buf = bytearray(width * height * 3)
    dpi_factor = max(1, min(600, int(dpi)))
    for y in range(height):
        for x in range(width):
            # light paper background + subtle gradients
            base = 235 + ((x * 7 + y * 3 + dpi_factor) % 10)
            r = _clamp_byte(base)
            g = _clamp_byte(base - ((x + dpi_factor) % 5))
            b = _clamp_byte(base - ((y + dpi_factor) % 4))

            # red form lines (simulates OMR sheet print)
            if x % max(40, width // 14) in (0, 1) or y % max(35, height // 18) in (0, 1):
                r, g, b = 220, 60, 60

            # dark pencil marks
            if ((x - width // 4) ** 2 + (y - height // 3) ** 2) < (min(width, height) // 20) ** 2:
                r, g, b = 65, 65, 65
            if ((x - (width * 3 // 5)) ** 2 + (y - (height * 2 // 3)) ** 2) < (min(width, height) // 24) ** 2:
                r, g, b = 35, 35, 35

            idx = (y * width + x) * 3
            buf[idx] = r
            buf[idx + 1] = g
            buf[idx + 2] = b
    return bytes(buf)


def _generate_gray_pixels(width: int, height: int, dpi: int, binary: bool = False) -> bytes:
    buf = bytearray(width * height)
    dpi_factor = max(1, min(600, int(dpi)))
    for y in range(height):
        for x in range(width):
            val = 235 + ((x * 5 + y * 2 + dpi_factor) % 12)
            if x % max(40, width // 14) in (0, 1) or y % max(35, height // 18) in (0, 1):
                val = 190
            if ((x - width // 4) ** 2 + (y - height // 3) ** 2) < (min(width, height) // 20) ** 2:
                val = 70
            if ((x - (width * 3 // 5)) ** 2 + (y - (height * 2 // 3)) ** 2) < (min(width, height) // 24) ** 2:
                val = 30
            if binary:
                val = 255 if val > 150 else 0
            buf[y * width + x] = _clamp_byte(val)
    return bytes(buf)


def _write_ppm(path: Path, width: int, height: int, rgb_payload: bytes) -> None:
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    with path.open("wb") as f:
        f.write(header)
        f.write(rgb_payload)


def _write_pgm(path: Path, width: int, height: int, gray_payload: bytes) -> None:
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    with path.open("wb") as f:
        f.write(header)
        f.write(gray_payload)


def _save_dummy_scan(
    output_dir: Path,
    dpi: int,
    color_mode: str,
    width: int,
    height: int,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".ppm" if color_mode == "color" else ".pgm"
    file_name = f"scan_{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
    out_path = (output_dir / file_name).resolve()

    if color_mode == "color":
        payload = _generate_rgb_pixels(width=width, height=height, dpi=dpi)
        _write_ppm(out_path, width=width, height=height, rgb_payload=payload)
    elif color_mode == "gray":
        payload = _generate_gray_pixels(width=width, height=height, dpi=dpi, binary=False)
        _write_pgm(out_path, width=width, height=height, gray_payload=payload)
    elif color_mode == "bw":
        payload = _generate_gray_pixels(width=width, height=height, dpi=dpi, binary=True)
        _write_pgm(out_path, width=width, height=height, gray_payload=payload)
    else:
        raise ValueError(f"Unsupported color mode: {color_mode}")

    return out_path


def _parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="32-bit scanner worker (mock mode)")
    parser.add_argument("--dpi", type=int, default=300, help="Scan DPI (e.g., 150/200/300)")
    parser.add_argument(
        "--color-mode",
        type=str,
        default="color",
        choices=["color", "gray", "bw"],
        help="Output color mode",
    )
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save scanned image")
    parser.add_argument("--width", type=int, default=1240, help="Dummy image width")
    parser.add_argument("--height", type=int, default=1754, help="Dummy image height")
    parser.add_argument(
        "--simulate-delay-ms",
        type=int,
        default=0,
        help="Mock delay before returning (for timeout tests)",
    )
    parser.add_argument(
        "--mock-fail",
        action="store_true",
        help="Force worker failure (for bridge error handling tests)",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.mock_fail:
        _log("[scanner_worker_32] Mock failure requested")
        return 2

    if args.simulate_delay_ms > 0:
        time.sleep(max(0, int(args.simulate_delay_ms)) / 1000.0)

    dpi = max(50, min(1200, int(args.dpi)))
    width = max(64, int(args.width))
    height = max(64, int(args.height))
    output_dir = Path(args.output_dir)

    try:
        # TODO: Replace this mock implementation with actual TWAIN/WIA acquisition.
        # The production flow should save the scanned file and print only its final path to stdout.
        path = _save_dummy_scan(
            output_dir=output_dir,
            dpi=dpi,
            color_mode=str(args.color_mode),
            width=width,
            height=height,
        )
    except Exception as exc:
        _log(f"[scanner_worker_32] Scan failed: {exc}")
        return 1

    print(str(path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
