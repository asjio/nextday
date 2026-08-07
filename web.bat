@echo off
REM NextDay Web台账 - 双击启动
set PYTHONPATH=
cd /d D:\工具\nextday
netstat -ano | findstr ":8766" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    start http://127.0.0.1:8766
) else (
    start "" /min .venv\Scripts\python.exe -m nextday.web
    timeout /t 4 /nobreak >nul
    start http://127.0.0.1:8766
)
