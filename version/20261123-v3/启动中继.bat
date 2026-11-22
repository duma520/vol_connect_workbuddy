@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   WorkBuddy 多账号中继 正在启动...
echo ========================================
echo.
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 python，请先安装 Python 3.10 或以上。
    pause
    exit /b 1
)
"%PY%" -m relay.app
if errorlevel 1 (
    echo.
    echo [提示] 启动失败，请把上面的报错发给开发者。
    pause
)