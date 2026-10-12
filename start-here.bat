@echo off
REM TRISHUL-Q - portable start (Windows). Just double-click this file.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-here.ps1"
echo.
echo (Server band karne ke liye is window me Ctrl+C dabao.)
pause
