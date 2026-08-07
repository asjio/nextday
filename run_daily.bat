@echo off
chcp 936 >nul
REM NextDay 每日预测流程 - 双击运行
REM 必须清除PYTHONPATH, 否则Hermes环境变量会污染venv
set PYTHONPATH=
cd /d D:\工具\nextday
.venv\Scripts\python.exe -m nextday.main
echo.
echo 执行完毕, 按任意键退出...
pause >nul
