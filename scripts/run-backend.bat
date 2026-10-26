@echo off
rem Starts the FastAPI backend on port 8001 using the project's venv (Python 3.11).
cd /d "%~dp0..\backend" || (echo Could not open the backend folder. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
  echo The backend venv is missing. Create it with:
  echo   cd backend
  echo   uv venv --python 3.11 .venv
  echo   uv pip install --python .venv\Scripts\python.exe -r requirements.txt
  pause
  exit /b 1
)
rem Port 8001 must be free: uvicorn fails with WinError 10013 if another process already holds it.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":8001 .*LISTENING"') do set BUSY_PID=%%P
if defined BUSY_PID (
  echo Port 8001 is already in use by process %BUSY_PID%, probably an earlier backend.
  echo Stop it first, then run this again:
  echo   taskkill /PID %BUSY_PID% /F
  pause
  exit /b 1
)
title EventPilot Backend - http://127.0.0.1:8001
echo Backend logs. API docs: http://127.0.0.1:8001/docs
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8001
echo.
echo Backend stopped.
pause
