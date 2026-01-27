import json
import locale
from pathlib import Path


def _preferred_encoding() -> str:
    enc = locale.getpreferredencoding(False) or "utf-8"
    return enc


def _decode_bytes(raw: bytes, encodings: list[str]) -> tuple[str, str]:
    for enc in encodings:
        try:
            return raw.decode(enc), enc
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    preferred = _preferred_encoding()
    # UTF-8 is tried first to avoid mojibake if the file is UTF-8 on a non-UTF-8 locale.
    encodings = ["utf-8-sig", "utf-8"]
    if preferred not in encodings:
        encodings.append(preferred)
    encodings.extend(["cp949", "euc-kr"])
    text, _ = _decode_bytes(raw, encodings)
    return text


def read_json(path: str | Path):
    text = read_text(path)
    return json.loads(text)


def write_text(path: str | Path, text: str) -> str:
    preferred = _preferred_encoding()
    try:
        Path(path).write_text(text, encoding=preferred)
        return preferred
    except UnicodeEncodeError:
        Path(path).write_text(text, encoding="utf-8")
        return "utf-8"


def write_json(path: str | Path, data, **json_kwargs) -> str:
    if "ensure_ascii" not in json_kwargs:
        json_kwargs["ensure_ascii"] = False
    text = json.dumps(data, **json_kwargs)
    return write_text(path, text)
