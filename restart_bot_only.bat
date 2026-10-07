@echo off
chcp 65001 >nul
title HyperHub Bot Restarter
echo ========================================================
echo        🔄 HYPERHUB BOT RESTARTER (GIỮ NGUYÊN TUNNEL)
echo ========================================================
echo.
echo 1. Đang tắt tiến trình Discord Bot cũ...
taskkill /f /fi "WINDOWTITLE eq HyperHub Discord Bot*" >nul 2>&1
timeout /t 2 /nobreak >nul

echo 2. Đang khởi động lại Discord Bot...
cd /d "%~dp0Bot"
start "HyperHub Discord Bot" cmd /k "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && set PYTHONPATH=%~dp0 && C:\Users\Mk2012\AppData\Local\Python\pythoncore-3.14-64\python.exe bot.py"

echo.
echo ========================================================
echo  ✅ Đã reset Discord Bot thành công!
echo  - Ngrok Tunnel vẫn giữ nguyên (URL cố định vĩnh viễn)
echo  - Web Vercel sẽ tự động kết nối lại sau 3-5 giây!
echo ========================================================
echo.
pause
