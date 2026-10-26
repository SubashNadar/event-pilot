@echo off
rem Lint checks: TypeScript typecheck for the frontend, and a compile check for the backend.
rem (The backend has no linter configured, so it is checked for syntax errors only.)
set FAILED=0
title EventPilot Lint

echo === Frontend typecheck (tsc --noEmit) ===
pushd "%~dp0..\frontend"
call npm run typecheck || set FAILED=1
popd

echo.
echo === Backend compile check (python -m compileall) ===
pushd "%~dp0..\backend"
".venv\Scripts\python.exe" -m compileall -q app tests || set FAILED=1
popd

echo.
if "%FAILED%"=="0" (
  echo LINT PASSED
) else (
  echo LINT FAILED - see the errors above
)
pause
