@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PORT=8000
for /f "delims=" %%p in ('C:\ProgramData\anaconda3\python.exe -c "import json; print(json.load(open('config.json', encoding='utf-8')).get('port', 8000))" 2^>nul') do set PORT=%%p

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING" 2^>nul') do (
  echo Stopping server PID %%a
  taskkill /PID %%a /F >nul 2>&1
)
echo Done.
