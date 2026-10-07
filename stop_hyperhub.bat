@echo off
chcp 65001 >nul
title HyperHub Stopper
echo ========================================================
echo        🛑 HYPERHUB SYSTEM STOPPER (1-CLICK)
echo ========================================================
echo.
echo Đang tắt các tiến trình HyperHub đang chạy...

taskkill /f /im cloudflared.exe >nul 2>&1
taskkill /f /im ngrok.exe >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq HyperHub Discord Bot*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq HyperHub Cloudflare Tunnel*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq HyperHub Ngrok Tunnel*" >nul 2>&1

echo.
echo ========================================================
echo  ✅ Đã tắt toàn bộ Bot Discord và Ngrok Tunnel an toàn!
echo  - Bạn có thể yên tâm tắt máy hoặc nghỉ ngơi.
echo ========================================================
echo.
pause
