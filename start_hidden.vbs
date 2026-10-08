' HyperHub headless launcher — chay Bot + Ngrok HOAN TOAN AN (khong cua so).
' Dung cho Task Scheduler (tu chay khi dang nhap) hoac chay tay: wscript.exe start_hidden.vbs
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"

' 1. Discord Bot (pythonw = khong console)
sh.CurrentDirectory = "D:\Project\Bot"
sh.Run """C:\Users\Mk2012\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"" bot.py", 0, False

' 2. Ngrok tunnel (an, giu URL co dinh cho Vercel) — bo qua neu goi voi "botonly"
If Not (WScript.Arguments.Count > 0 And LCase(WScript.Arguments(0)) = "botonly") Then
  WScript.Sleep 3000
  sh.CurrentDirectory = "D:\Project"
  sh.Run """D:\Project\ngrok.exe"" http 8080 --url=https://phantasmagorically-occupative-gladys.ngrok-free.dev", 0, False
End If
