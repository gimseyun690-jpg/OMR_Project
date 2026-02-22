param(
    [string]$PythonExe = "C:\Users\user\AppData\Local\Programs\Python\Python310\python.exe",
    [string]$VenvRoot = "D:\OMR_Project_envs",
    [string]$VenvName = ".venv64"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPath = Join-Path $VenvRoot $VenvName
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
$PipCache = Join-Path $VenvRoot "pip-cache"
$TmpDir = Join-Path $VenvRoot "tmp"

Write-Host "[INFO] RepoRoot: $RepoRoot"
Write-Host "[INFO] PythonExe: $PythonExe"
Write-Host "[INFO] VenvPath : $VenvPath"

if (-not (Test-Path $PythonExe)) {
    throw "64-bit python not found: $PythonExe"
}

New-Item -ItemType Directory -Force -Path $VenvRoot | Out-Null
New-Item -ItemType Directory -Force -Path $PipCache | Out-Null
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null

if (-not (Test-Path $VenvPython)) {
    & $PythonExe -m venv $VenvPath
}

$env:TEMP = $TmpDir
$env:TMP = $TmpDir

Push-Location $RepoRoot
try {
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install --cache-dir $PipCache -r requirements.txt

    # Keep UI runtime stable with current PySide2 stack.
    & $VenvPython -m pip install --cache-dir $PipCache "numpy<2"

    Write-Host "[INFO] Setup complete."
    & $VenvPython -c "import struct, PySide2, cv2, numpy, qfluentwidgets; print('bits', struct.calcsize('P')*8); print('cv2', cv2.__version__); print('numpy', numpy.__version__); print('qfluentwidgets OK')"
}
finally {
    Pop-Location
}
