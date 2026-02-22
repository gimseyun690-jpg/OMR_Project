@echo off
setlocal

set "VENV_PY=D:\OMR_Project_envs\.venv64\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [ERROR] 64-bit venv python not found: %VENV_PY%
    exit /b 1
)

cd /d "%~dp0"
"%VENV_PY%" main.py

endlocal
