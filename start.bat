@echo off
setlocal
title J.A.R.V.I.S. Auto-Setup & Launcher
echo.
echo  ========================================
echo   J.A.R.V.I.S. - One-Click Setup & Start
echo  ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Jarvis exited with code %EXIT_CODE%.
    pause
)
endlocal
exit /b %EXIT_CODE%
