@echo off
chcp 65001 > nul
echo ============================================
echo    一键报价系统 - 启动中...
echo    赛正慧采商城
echo ============================================
echo.
cd /d "%~dp0"
python app.py
pause