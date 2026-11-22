@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 只启动中继服务（不开面板）...
python -m relay.app --no-gui
pause