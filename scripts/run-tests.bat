@echo off
rem Runs the backend test suite with verbose output, so each test's result is visible.
title EventPilot Tests
pushd "%~dp0..\backend"
".venv\Scripts\python.exe" -m pytest -v
set RESULT=%ERRORLEVEL%
popd
echo.
if "%RESULT%"=="0" (
  echo ALL TESTS PASSED
) else (
  echo TESTS FAILED - see the failures above
)
pause
