@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
call stop_server.bat
start "Tomodachi Server" cmd /k start_server.bat

