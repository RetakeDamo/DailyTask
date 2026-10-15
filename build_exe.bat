@echo off
chcp 65001 >nul
rem ============================================================
rem  打包成单文件 EXE（需要联网安装 PyInstaller）
rem  生成：dist\DailyTaskReminder.exe
rem ============================================================
setlocal
cd /d "%~dp0"

for %%P in (python.exe) do set "PY=%%~$PATH:P"
if not defined PY (
    echo 未找到 Python，请先安装 Python 3.9+（勾选 Add Python to PATH）。
    pause & exit /b 1
)

echo [1/3] 检查 PyInstaller ...
"%PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo      正在安装 PyInstaller ...
    "%PY%" -m pip install --upgrade pyinstaller || (echo 安装失败，请检查网络。 & pause & exit /b 1)
)

echo [2/3] 生成图标 ...
"%PY%" tools\make_icon.py || (echo 图标生成失败。 & pause & exit /b 1)

echo [3/3] 开始打包 ...
"%PY%" -m PyInstaller --noconfirm --clean ^
  --name DailyTaskReminder ^
  --onefile ^
  --windowed ^
  --icon app.ico ^
  --add-data "app.ico;." ^
  --hidden-import tkinter ^
  --hidden-import winsound ^
  main.py || (echo 打包失败。 & pause & exit /b 1)

echo.
echo 打包完成：%cd%\dist\DailyTaskReminder.exe
echo 可直接双击运行，也可以复制到任意位置。
pause
