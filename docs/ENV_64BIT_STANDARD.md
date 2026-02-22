# 64-bit Standard Environment (D Drive)

This project now uses the following as the standard 64-bit runtime environment:

- `D:\OMR_Project_envs\.venv64`

This avoids C drive disk pressure and prevents confusion with the local project venv (`.\.venv64`).

## Why `PySide2-Fluent-Widgets` looked "not installed"

The package was installed in the **D-drive venv**, but not in the local project venv.

- `pip` package name: `PySide2-Fluent-Widgets`
- Python import name: `qfluentwidgets`

Both are correct. Example:

```powershell
D:\OMR_Project_envs\.venv64\Scripts\python.exe -m pip show PySide2-Fluent-Widgets
D:\OMR_Project_envs\.venv64\Scripts\python.exe -c "import qfluentwidgets; print('OK')"
```

## Standard run command

```powershell
D:\OMR_Project_envs\.venv64\Scripts\python.exe main.py
```

Or use:

- `run_main_64.bat`

## IDE interpreter (VS Code / similar)

Set the interpreter to:

- `D:\OMR_Project_envs\.venv64\Scripts\python.exe`

The workspace file (`OMR_Project.code-workspace`) is configured with this path as the default.

## Setup / Rebuild the D-drive 64-bit venv

Use the helper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\setup_venv64_d.ps1
```

What it does:

1. Creates `D:\OMR_Project_envs\.venv64`
2. Installs `requirements.txt`
3. Pins `numpy<2` for PySide2 runtime stability (current project baseline)

## Verify the environment

Use the helper script:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\check_venv64_d.ps1
```

It checks:

- 64-bit interpreter
- `PySide2-Fluent-Widgets` package presence
- `qfluentwidgets` import
- `PySide2/cv2/numpy` imports
- `main.py` syntax

## Notes on `numpy` version

Current recommended baseline for the 64-bit UI runtime:

- `numpy<2`

Reason:

- The current `PySide2` stack in this project can produce compatibility warnings/issues with `numpy 2.x`.
- We prioritize stable UI startup and predictable runtime behavior.

We may revisit this later (for example by introducing `requirements-64.txt`).

## Troubleshooting (quick order)

1. Confirm which Python is actually being used

```powershell
D:\OMR_Project_envs\.venv64\Scripts\python.exe -c "import sys; print(sys.executable)"
```

2. Check package installation (`pip` name)

```powershell
D:\OMR_Project_envs\.venv64\Scripts\python.exe -m pip show PySide2-Fluent-Widgets
```

3. Check import (`module` name)

```powershell
D:\OMR_Project_envs\.venv64\Scripts\python.exe -c "import qfluentwidgets; print('OK')"
```

4. Confirm bitness

```powershell
D:\OMR_Project_envs\.venv64\Scripts\python.exe -c "import struct; print(struct.calcsize('P')*8)"
```

Expected output:

- `64`
