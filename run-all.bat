@echo off
rem Opens four terminal windows: backend logs, frontend logs, lint, and the test run.
rem Stop any servers already running on ports 8001 and 5173 first, or those windows will fail to start.
set SCRIPTS=%~dp0scripts

start "EventPilot Backend" cmd /k call "%SCRIPTS%\run-backend.bat"
start "EventPilot Frontend" cmd /k call "%SCRIPTS%\run-frontend.bat"
start "EventPilot Lint" cmd /k call "%SCRIPTS%\run-lint.bat"
start "EventPilot Tests" cmd /k call "%SCRIPTS%\run-tests.bat"

echo Started the backend, frontend, lint and test windows.
echo Backend: http://127.0.0.1:8001/docs   Frontend: http://127.0.0.1:5173
