# OMR_Project

Windows 32bit Python(3.10) 기반 OMR 처리/집계 애플리케이션입니다.

## 개발 환경 요구사항

- Windows
- Python 3.10 32bit

## 초기 세팅

```powershell
py -3.10-32 -m venv .venv32
.\.venv32\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 실행 방법

```powershell
python main.py
```

## Windows 설치 파일 만들기

Python 3.10 64비트와 Inno Setup 6가 설치된 Windows에서 다음 명령을 실행합니다.

```powershell
.\packaging\build_installer.ps1
```

완성된 설치 파일은 `release\OMR_Project_Setup_v1.0.0.exe`에 생성됩니다. 설치 시 바탕화면 바로가기가 기본으로 만들어집니다.

## VS Code 설정

- 인터프리터를 `.venv32\Scripts\python.exe`로 선택
- 패키지 인식 문제가 있으면 `Python: Restart Language Server` 실행

## 트러블슈팅

### PySide2가 없다고 뜨는 경우

원인: 32bit/64bit 인터프리터 불일치일 가능성이 큽니다.

아래 명령으로 현재 인터프리터와 비트수를 확인하세요.

```powershell
python -c "import struct,sys; print(struct.calcsize('P')*8); print(sys.executable)"
```

PySide2 및 Fluent Widgets import 확인:

```powershell
python -c "import PySide2, qfluentwidgets; print('ok')"
```
