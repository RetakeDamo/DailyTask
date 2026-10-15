@echo off
chcp 65001 >nul
rem ============================================================
rem  推送到 GitHub（双击运行，或把仓库地址作为参数传进来）
rem     推送Github.bat https://github.com/用户名/仓库名.git
rem ============================================================
setlocal
cd /d "%~dp0"

where pwsh >nul 2>&1
if %errorlevel%==0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_to_github.ps1" %*
    exit /b %errorlevel%
)

where powershell >nul 2>&1
if %errorlevel%==0 (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0push_to_github.ps1" %*
    exit /b %errorlevel%
)

echo 未找到 PowerShell，请在 Git Bash 里手动执行：
echo   git remote add origin ^<仓库地址^>
echo   git push -u origin main
echo   git push origin --tags
pause
exit /b 1
