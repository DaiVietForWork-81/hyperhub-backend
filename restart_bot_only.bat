@echo off
title HyperHub Bot Restarter (giu nguyen tunnel)
echo [HyperHub] Dang restart Bot (giua nguyen Ngrok tunnel)...

taskkill /f /fi "WINDOWTITLE eq HyperHub Discord Bot*" >nul 2>&1
powershell -noprofile -command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 3 /nobreak >nul

wscript.exe "%~dp0start_hidden.vbs" botonly
echo [HyperHub] Da restart Bot (an). Ngrok giu nguyen. Kiem tra API sau 30-60 giay.
