param(
    [string]$VenvPython = "D:\OMR_Project_envs\.venv64\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $VenvPython)) {
    throw "64-bit venv python not found: $VenvPython"
}

Write-Host "[CHECK] 64-bit"
& $VenvPython -c "import struct; print(struct.calcsize('P')*8)"

Write-Host "[CHECK] PySide2-Fluent-Widgets installed (package name)"
& $VenvPython -m pip show PySide2-Fluent-Widgets

Write-Host "[CHECK] qfluentwidgets import (module name)"
& $VenvPython -c "import qfluentwidgets; print('OK')"

Write-Host "[CHECK] Core runtime imports"
& $VenvPython -c "import PySide2, cv2, numpy; print(PySide2.__file__); print(cv2.__version__); print(numpy.__version__)"

Write-Host "[CHECK] main.py syntax"
& $VenvPython -m py_compile main.py

Write-Host "[DONE] 64-bit environment checks passed."
