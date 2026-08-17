@echo off
cd /d "%~dp0"
call ".venv\Scripts\python.exe" -m nextday_v2.main
pause
