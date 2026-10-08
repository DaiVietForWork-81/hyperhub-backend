@echo off
title HyperHub Launcher (hidden)
echo [HyperHub] Dang khoi chay Bot + Ngrok (che do an, khong cua so)...
wscript.exe "%~dp0start_hidden.vbs"
echo [HyperHub] Da gui lenh khoi chay. Kiem tra sau 30-60 giay:
echo   - API: http://127.0.0.1:8080/api/status
echo   - Log: Bot\logs\bot.log
echo   - Tat he thong: chay stop_hyperhub.bat
