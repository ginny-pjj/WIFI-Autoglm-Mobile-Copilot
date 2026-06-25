@echo off
set ROOT=%~dp0..
cd /d "%ROOT%"
set ADB=%ROOT%\platform-tools\adb.exe
if not exist "%ADB%" set ADB=adb

echo ========================================
echo AutoGLM WiFi mode (same WiFi, no cloud)
echo ========================================
echo.

if "%PHONE_IP%"=="" (
    echo Usage:
    echo   set PHONE_IP=192.168.x.x
    echo   connect_phone_wifi.bat
    echo.
    echo Or edit PHONE_IP below in this file.
    set PHONE_IP=192.168.1.100
)

echo Phone IP: %PHONE_IP%
echo.

echo [1/4] Backend health
curl.exe -s -m 5 http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 (
    echo   FAIL - run start_server.bat first
    goto end
)
echo   OK
echo.

echo [2/4] adb connect %PHONE_IP%:5555
%ADB% connect %PHONE_IP%:5555
%ADB% devices
%ADB% devices 2>nul | findstr /r "%PHONE_IP%:5555.*device" >nul
if errorlevel 1 (
    echo   FAIL - wireless ADB not connected
    echo   Fix: USB once, run: adb tcpip 5555
    echo   Or use Developer options - Wireless debugging - Pair
    goto end
)
echo   OK
echo.

echo [3/4] Your PC LAN IP for the App
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set PC_IP=%%a
    goto gotip
)
:gotip
set PC_IP=%PC_IP: =%
echo   App base URL: http://%PC_IP%:8000
echo   (Do NOT use 127.0.0.1 in WiFi mode)
echo.

echo [4/4] Server sees device
curl.exe -s http://127.0.0.1:8000/devices
echo.
echo.
echo ========================================
echo WiFi ready. On phone App:
echo   Base URL = http://%PC_IP%:8000
echo   Tap Connect Test
echo ========================================

:end
pause
