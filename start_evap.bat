@echo off
:: ============================================================
:: start_evap.bat — Start EVAP backend + frontend
:: Logs go to logs\backend.log and logs\frontend.log
:: ============================================================

set ROOT=c:\Users\user\Downloads\cctv_phase1
set VENV=%ROOT%\.venv\Scripts
set BACKEND=%ROOT%\evap\backend
set FRONTEND=%ROOT%\evap\frontend
set LOGS=%ROOT%\logs

:: Create logs directory if it doesn't exist
if not exist "%LOGS%" mkdir "%LOGS%"

echo ============================================================
echo  EVAP Enterprise Video Analytics Platform
echo ============================================================
echo  Backend log : %LOGS%\backend.log
echo  Frontend log: %LOGS%\frontend.log
echo ============================================================
echo.

:: Kill any existing processes on port 8000 and 3000
echo [*] Freeing ports 8000 and 3000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 "') do taskkill /F /PID %%a >nul 2>&1

:: Clear Python bytecode cache so stale .pyc files never shadow edited source files
echo [*] Clearing Python __pycache__ ...
for /d /r "%ROOT%\evap\backend" %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d"

:: Start FastAPI backend in a new window, log to file
echo [*] Starting FastAPI backend on http://localhost:8000 ...
start "EVAP Backend" cmd /c ""%VENV%\uvicorn.exe" app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir "%BACKEND%" >> "%LOGS%\backend.log" 2>&1"

:: Wait 3 seconds for backend to initialize
timeout /t 3 /nobreak >nul

:: Start React frontend in a new window, log to file
echo [*] Starting React frontend on http://localhost:3000 ...
start "EVAP Frontend" cmd /c "cd /d "%FRONTEND%" && npm start >> "%LOGS%\frontend.log" 2>&1"

echo.
echo [OK] Both services started.
echo.
echo  Open browser : http://localhost:3000
echo  API docs     : http://localhost:8000/docs
echo  Health check : http://localhost:8000/health
echo.
echo  Logs are being written to:
echo    Backend  ^> %LOGS%\backend.log
echo    Frontend ^> %LOGS%\frontend.log
echo.
echo  To watch backend log live:
echo    powershell Get-Content -Wait "%LOGS%\backend.log"
echo.
echo  To watch frontend log live:
echo    powershell Get-Content -Wait "%LOGS%\frontend.log"
echo.
echo  Press any key to stop both services...
pause >nul

echo [*] Stopping services...
taskkill /FI "WINDOWTITLE eq EVAP Backend" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq EVAP Frontend" /T /F >nul 2>&1
echo [OK] Done.
