@echo off
chcp 65001 >nul
title HyperHub Launcher
echo ========================================================
echo        🚀 HYPERHUB SYSTEM LAUNCHER (1-CLICK)
echo ========================================================
echo.
echo 1. Đang khởi chạy Discord Bot...
cd /d "%~dp0Bot"
start "HyperHub Discord Bot" cmd /k "chcp 65001 >nul && set PYTHONIOENCODING=utf-8 && set PYTHONPATH=%~dp0 && C:\Users\Mk2012\AppData\Local\Python\pythoncore-3.14-64\python.exe bot.py"

timeout /t 3 /nobreak >nul

echo 2. Đang khởi chạy Ngrok Tunnel Cố Định (Cầu nối HTTPS Vercel vĩnh viễn)...
cd /d "%~dp0"
start "HyperHub Ngrok Tunnel" cmd /k "%~dp0ngrok.exe http 8080 --url=https://phantasmagorically-occupative-gladys.ngrok-free.dev"

echo.
echo ========================================================
echo  ✅ Hệ thống HyperHub đã được bật thành công!
echo  - Cửa sổ 1: Discord Bot đang chạy (port 8080)
echo  - Cửa sổ 2: Ngrok Domain Cố Định: https://phantasmagorically-occupative-gladys.ngrok-free.dev
echo  - Web Vercel: https://hyperhub-one.vercel.app/
echo  - Để tắt hệ thống khi không dùng: Chạy 'stop_hyperhub.bat'
echo ========================================================
echo.
pause
