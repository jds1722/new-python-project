@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo 실행 환경이 없습니다. requirements.txt 패키지를 먼저 설치하세요.
  pause
  exit /b 1
)
set "TCL_LIBRARY=%~dp0..\multilayer-tif-sorter-prototype\runtime\python313\tcl\tcl8.6"
set "TK_LIBRARY=%~dp0..\multilayer-tif-sorter-prototype\runtime\python313\tcl\tk8.6"
start "TIFF Channel Extractor" ".venv\Scripts\pythonw.exe" "main.py"
if errorlevel 1 pause
