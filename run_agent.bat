@echo off
title AI Newsletter Agent
echo Starting AI Newsletter Agent...
cd /d "%~dp0"
start http://localhost:5000
.\venv\Scripts\python.exe app.py
pause
