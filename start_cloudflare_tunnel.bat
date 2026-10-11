@echo off
title HyperHub Cloudflare Tunnel
echo ========================================================
echo   HYPERHUB CLOUDFLARE TUNNEL (Khong Gioi Han Bang Thong)
echo ========================================================
echo.
echo Dang khoi tao tunnel ket noi cong 8080 (Bot API)...
echo.
"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8080
pause
