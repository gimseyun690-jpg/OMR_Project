import os
import sys


def base_dir():
    """PyInstaller 실행 경로와 개발 경로를 모두 지원하는 기준 경로."""
    if getattr(sys, "_MEIPASS", None):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def data_path(*parts):
    """data 폴더 기준 경로 생성."""
    return os.path.join(base_dir(), "data", *parts)
