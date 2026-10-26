@echo off
rem Starts the Vite dev server on port 5173.
cd /d "%~dp0..\frontend" || (echo Could not open the frontend folder. & pause & exit /b 1)
if not exist "node_modules" (
  echo Installing frontend packages first...
  call npm install || (pause & exit /b 1)
)
title EventPilot Frontend - http://127.0.0.1:5173
echo Frontend logs. Open: http://127.0.0.1:5173
call npm run dev -- --host 127.0.0.1 --port 5173
echo.
echo Frontend stopped.
pause
