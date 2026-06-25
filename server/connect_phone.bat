@echo off
cd /d D:\autoglm-mobile-work
set ADB=D:\autoglm-mobile-work\platform-tools\adb.exe

echo ========================================
echo AutoGLM connect check (USB + reverse)
echo ========================================
echo.

echo [1/4] Backend health http://127.0.0.1:8000/health
curl.exe -s -m 5 http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    echo   FAIL - run start_server.bat first
    goto end
)
echo   OK - server running
echo.

echo [2/4] ADB devices
%ADB% devices
%ADB% devices 2>nul | findstr /r "device$" >nul
if errorlevel 1 (
    echo   FAIL - phone not connected or USB debug not authorized
    goto end
)
echo   OK - device found
echo.

echo [3/4] adb reverse tcp:8000 tcp:8000
%ADB% reverse tcp:8000 tcp:8000
%ADB% reverse --list
echo.

echo [4/4] Test from phone via 127.0.0.1:8000
%ADB% shell curl -s --connect-timeout 3 http://127.0.0.1:8000/health
echo.
echo.

echo ========================================
echo If you see status ok above:
echo 1. Open AutoGLM App on phone
echo 2. Base URL: http://127.0.0.1:8000
echo 3. Tap Connect Test
echo ========================================

:end
pause
