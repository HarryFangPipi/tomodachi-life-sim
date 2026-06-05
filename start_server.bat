@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PYTHON_CMD=
if exist "C:\ProgramData\anaconda3\python.exe" set PYTHON_CMD=C:\ProgramData\anaconda3\python.exe
if exist "%USERPROFILE%\anaconda3\python.exe" set PYTHON_CMD=%USERPROFILE%\anaconda3\python.exe
if "%PYTHON_CMD%"=="" where python >nul 2>&1 && set PYTHON_CMD=python

if "%PYTHON_CMD%"=="" (
  echo [ERROR] Python not found.
  pause
  exit /b 1
)

echo Starting Tomodachi World...
echo Python: %PYTHON_CMD%
%PYTHON_CMD% -m pip install -r requirements.txt -q --disable-pip-version-check
%PYTHON_CMD% -B server.py
pause

