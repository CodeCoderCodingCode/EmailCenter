@echo off
cd /d "%~dp0"
if exist "dist\runtime\EmailCenter\EmailCenter.exe" (
  if not exist "dist\runtime\EmailCenter\_internal\python313.dll" (
    echo Die Programmlaufzeit fehlt. Bitte Install_EmailCenter.cmd ausfuehren.
    pause
    exit /b 1
  )
  start "" /d "%~dp0dist\runtime\EmailCenter" "%~dp0dist\runtime\EmailCenter\EmailCenter.exe" %*
  exit /b 0
)
if not exist ".venv\Scripts\pythonw.exe" (
  echo Projektumgebung fehlt. Siehe README_START_HERE.txt.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "start_emailcenter.py" %*
