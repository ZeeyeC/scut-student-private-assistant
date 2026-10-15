@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\initialize-windows.ps1" %*
set "CAMPUS_EXIT_CODE=%ERRORLEVEL%"
if "%CAMPUS_EXIT_CODE%"=="0" exit /b 0
echo.
echo Startup or initialization failed. Check the message above.
echo Build logs, when available: .tools\initialize.log
pause
exit /b %CAMPUS_EXIT_CODE%
