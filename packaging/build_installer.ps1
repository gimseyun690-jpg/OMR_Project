$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv-build\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    py -3.10-64 -m venv (Join-Path $projectRoot ".venv-build")
}

& $python -m pip install -r (Join-Path $projectRoot "requirements-build.txt")

Push-Location $projectRoot
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name "OMR_Project" `
        --icon "resources\app_icon.ico" `
        --add-data "resources;resources" `
        --add-data "data;data" `
        --add-data "omr_master.db;." `
        --hidden-import "twain" `
        --hidden-import "win32com.client" `
        --collect-all "qfluentwidgets" `
        --collect-all "qframelesswindow" `
        "main.py"
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed (exit code $LASTEXITCODE)."
    }

    $isccCandidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    $iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) {
        throw "Inno Setup 6 (ISCC.exe)을 찾을 수 없습니다."
    }

    & $iscc "packaging\installer.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup build failed (exit code $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
