import os
import sys
import traceback
import ctypes

STARTUP_LOG = os.path.join(os.path.dirname(__file__), "startup.log")


def _log_startup(message: str):
    try:
        with open(STARTUP_LOG, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def _to_short_path(path: str) -> str:
    try:
        buf_size = 260
        buffer = ctypes.create_unicode_buffer(buf_size)
        out_len = ctypes.windll.kernel32.GetShortPathNameW(path, buffer, buf_size)
        if out_len > 0:
            return buffer.value 
    except Exception:
        pass
    return path


# Force 100% UI scale (ignore Windows display scaling)
try:
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["QT_FONT_DPI"] = "96"
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
except Exception as e:
    print(f"[InitWarn] Qt scaling/style setup failed: {e}")
    _log_startup(f"[InitWarn] scaling/style setup failed: {e}")

import PySide2  # noqa: F401
from PySide2.QtCore import QObject, QEvent, Qt
from PySide2.QtGui import QFont, QColor, QPalette
from PySide2.QtWidgets import QApplication, QMessageBox, QWidget

# On some Windows setups (especially non-ASCII paths), explicit plugin paths are safer.
_pyside_dir = os.path.dirname(PySide2.__file__)
_plugins_dir = os.path.join(_pyside_dir, "plugins")
_platforms_dir = os.path.join(_plugins_dir, "platforms")
if os.path.isdir(_plugins_dir):
    os.environ["QT_PLUGIN_PATH"] = _to_short_path(_plugins_dir)
if os.path.isdir(_platforms_dir):
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = _to_short_path(_platforms_dir)
_log_startup(
    f"[Startup] pyside_dir={_pyside_dir} "
    f"plugins_exists={os.path.isdir(_plugins_dir)} "
    f"platforms_exists={os.path.isdir(_platforms_dir)}"
)

# Check Fluent Widgets availability early
try:
    _log_startup(f"[Startup] python={sys.executable}")
    import qfluentwidgets  # noqa: F401
except Exception:
    _log_startup("[Fatal] qfluentwidgets import failed")
    _log_startup(traceback.format_exc())
    app = QApplication(sys.argv)
    QMessageBox.critical(
        None,
        "Dependency Error",
        "PySide2-Fluent-Widgets import failed.\n\n"
        "Check startup.log for details.\n"
        "Run this command again if needed:\n"
        "python -m pip install -r requirements.txt",
    )
    sys.exit(1)

from qfluentwidgets import setTheme, Theme
from ui.main_window import OMRScannerApp


GLOBAL_WHITE_QSS = """
QWidget, QDialog, QMessageBox {
    background-color: #FFFFFF;
    color: #000000;
}
QToolTip {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #BFBFBF;
}
QMessageBox QLabel {
    color: #000000;
    background-color: #FFFFFF;
}
QMessageBox QPushButton {
    background-color: #FFFFFF;
    color: #000000;
    border: 1px solid #CFCFCF;
    padding: 4px 10px;
}
QAbstractScrollArea { background: #FFFFFF; color: #111111; }
QTabWidget::pane { border: 1px solid #E1E7EE; background: #FFFFFF; }
QTabBar::tab { background: #F7F9FC; color: #111111; padding: 6px 12px; border: 1px solid #E1E7EE; }
QTabBar::tab:selected { background: #FFFFFF; }
QTableWidget { background: #FFFFFF; color: #111111; gridline-color: #E5E7EB; }
QHeaderView::section { background: #F1F5F9; color: #111111; border: 1px solid #E1E7EE; }
QTableCornerButton::section { background: #F1F5F9; border: 1px solid #E1E7EE; }
"""


class _WhiteModeEventFilter(QObject):
    """Force opaque white background for late-created top-level widgets/dialogs."""

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Show, QEvent.Polish) and isinstance(obj, QWidget):
            try:
                obj.setAttribute(Qt.WA_TranslucentBackground, False)
            except Exception:
                pass
            obj.setAttribute(Qt.WA_StyledBackground, True)
            obj.setAutoFillBackground(True)
        return False


def _apply_global_white_mode(app: QApplication):
    # Force light mode at startup to avoid dark fallback.
    try:
        setTheme(Theme.LIGHT)
    except Exception:
        pass

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#FFFFFF"))
    pal.setColor(QPalette.Base, QColor("#FFFFFF"))
    pal.setColor(QPalette.AlternateBase, QColor("#FFFFFF"))
    pal.setColor(QPalette.Button, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
    pal.setColor(QPalette.WindowText, QColor("#000000"))
    pal.setColor(QPalette.Text, QColor("#000000"))
    pal.setColor(QPalette.ButtonText, QColor("#000000"))
    pal.setColor(QPalette.ToolTipText, QColor("#000000"))
    app.setPalette(pal)

    app.setStyleSheet(GLOBAL_WHITE_QSS)

    filter_obj = _WhiteModeEventFilter(app)
    app.installEventFilter(filter_obj)
    app._white_mode_filter = filter_obj


def main():
    _log_startup("[Startup] main() entered")
    _log_startup(
        f"[Startup] env QT_OPENGL={os.environ.get('QT_OPENGL')} "
        f"QT_QUICK_BACKEND={os.environ.get('QT_QUICK_BACKEND')} "
        f"QT_AUTO_SCREEN_SCALE_FACTOR={os.environ.get('QT_AUTO_SCREEN_SCALE_FACTOR')} "
        f"QT_ENABLE_HIGHDPI_SCALING={os.environ.get('QT_ENABLE_HIGHDPI_SCALING')} "
        f"QT_SCALE_FACTOR={os.environ.get('QT_SCALE_FACTOR')} "
        f"QT_FONT_DPI={os.environ.get('QT_FONT_DPI')}"
    )
    app = QApplication(sys.argv)
    _log_startup("[Startup] QApplication created")
    _apply_global_white_mode(app)
    _log_startup("[Startup] global white mode applied")

    font = QFont("Malgun Gothic", 10)
    app.setFont(font)

    window = OMRScannerApp()
    _log_startup("[Startup] OMRScannerApp created")
    window.showMaximized()
    _log_startup("[Startup] window shown")

    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log_startup("[Fatal] unhandled exception in main")
        _log_startup(traceback.format_exc())
        raise
