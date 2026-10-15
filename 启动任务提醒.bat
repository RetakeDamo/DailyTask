@echo off
chcp 65001 >nul
rem ============================================================
rem  每日任务提醒 —— 命令行启动（便于查看错误信息）
rem ============================================================
setlocal
cd /d "%~dp0"

set "PYW="
if exist "%~dp0runtime\pythonw.exe" set "PYW=%~dp0runtime\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe" set "PYW=%LOCALAPPDATA%\Python\pythoncore-3.14-64\pythonw.exe"
if not defined PYW for %%P in (pythonw.exe) do if not defined PYW set "PYW=%%~$PATH:P"

if defined PYW (
    echo [启动] 使用 %PYW%
    start "" "%PYW%" "%~dp0main.py" %*
    exit /b 0
)

for %%P in (python.exe) do set "PY=%%~$PATH:P"
if defined PY (
    echo [启动] 使用 %PY%
    "%PY%" "%~dp0main.py" %*
    exit /b 0
)

echo 未找到 Python 运行环境，请先安装 Python 3.9+ 并勾选 Add Python to PATH。
pause
exit /b 1
