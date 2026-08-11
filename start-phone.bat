@echo off
cd /d "%~dp0"

for /f "tokens=*" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.InterfaceAlias -notmatch 'Loopback' } | Select-Object -First 1).IPAddress"') do set PHONE_IP=%%i

echo.
echo  ============================================
echo   Dynasty Analyst - open on your phone
echo  ============================================
echo.
echo   Same WiFi:  http://%PHONE_IP%:8501
echo   This PC:    http://localhost:8501
echo.
echo   Keep this window open. Press Ctrl+C to stop.
echo  ============================================
echo.

.venv\Scripts\streamlit.exe run app.py
