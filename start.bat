@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   友达世界 - 多Agent社会模拟
echo ========================================
echo.

REM Find Python
set PYTHON_CMD=
if exist "C:\ProgramData\anaconda3\python.exe" set PYTHON_CMD=C:\ProgramData\anaconda3\python.exe
if exist "C:\Users\%USERNAME%\anaconda3\python.exe" set PYTHON_CMD=C:\Users\%USERNAME%\anaconda3\python.exe
if "%PYTHON_CMD%"=="" where python >nul 2>&1 && set PYTHON_CMD=python
if "%PYTHON_CMD%"=="" (
  echo [错误] 未找到 Python
  pause
  exit /b 1
)

echo Python: %PYTHON_CMD%
%PYTHON_CMD% --version

echo.
echo 安装依赖...
%PYTHON_CMD% -m pip install -r requirements.txt -q --disable-pip-version-check

echo.
echo 清理字节码缓存...
if exist __pycache__ rmdir /s /q __pycache__

echo.
echo 终止旧进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING" 2^>nul') do taskkill /PID %%a /F >nul 2>&1
timeout /t 1 /nobreak >nul

echo.
echo 启动服务器 http://localhost:8000
echo 按 Ctrl+C 停止
echo.

start /B cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"
%PYTHON_CMD% -B server.py

pause
