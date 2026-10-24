@echo off
setlocal
cd /d "%~dp0"
if not exist "dist\release\EmailCenter-Setup-1.0.1-Windows-x64.exe" (
  echo Installer fehlt: dist\release\EmailCenter-Setup-1.0.1-Windows-x64.exe
  pause
  exit /b 1
)
start "" "%~dp0dist\release\EmailCenter-Setup-1.0.1-Windows-x64.exe"
