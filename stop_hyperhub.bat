@echo off
title HyperHub Stopper
echo [HyperHub] Dang tat Bot + Ngrok (ca tien trinh an)...

taskkill /f /im cloudflared.exe >nul 2>&1
taskkill /f /im ngrok.exe >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq HyperHub Discord Bot*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq HyperHub Cloudflare Tunnel*" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq HyperHub Ngrok Tunnel*" >nul 2>&1

powershell -noprofile -command "Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' or name='python.exe'\" | Where-Object { $_.CommandLine -like '*bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

echo [HyperHub] Da tat xong. Bot se khong tu chay lai tru khi mo may (Startup) hoac chay start_hyperhub.bat
