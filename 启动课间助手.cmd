@echo off
cd /d "%~dp0"
if exist "dist\desktop\CampusCompanion\CampusCompanion.exe" (
  start "" "dist\desktop\CampusCompanion\CampusCompanion.exe" --data-dir "%CD%" --project
  exit /b
)
if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" scripts\start-local.py
  exit /b %ERRORLEVEL%
)
echo Please build the desktop package first. See README.md.
pause
