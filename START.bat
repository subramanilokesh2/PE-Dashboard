@echo off
REM ZINNOV | PE Intelligence Command Center: start the local server and open the browser.
setlocal
cd /d "%~dp0"
title ZINNOV PE Intelligence Command Center

if not exist ".venv\Scripts\python.exe" (
  echo The environment is not set up yet. Running SETUP.bat first ...
  call "%~dp0SETUP.bat"
  if not exist ".venv\Scripts\python.exe" exit /b 1
)
if not exist "data\intel.db" (
  echo [ERROR] data\intel.db is missing. Re-extract the ZIP file in full.
  pause
  exit /b 1
)
if not exist "frontend\index.html" (
  echo [ERROR] frontend\index.html is missing. Re-extract the ZIP file in full.
  pause
  exit /b 1
)

for /f "usebackq delims=" %%P in (`".venv\Scripts\python.exe" scripts\find_port.py 5055`) do set "PORT=%%P"
set "URL=http://127.0.0.1:%PORT%/"
echo Starting the server on %URL%
echo Keep this window open while you use the platform. Close it to stop the server.
echo.

start "ZINNOV server" /min cmd /c ""%~dp0.venv\Scripts\python.exe" "%~dp0backend\app.py" %PORT%"
".venv\Scripts\python.exe" scripts\wait_ready.py "%URL%api/meta"
if errorlevel 1 (
  echo Check the "ZINNOV server" window for the error, then try again.
  pause
  exit /b 1
)
start "" "%URL%"
echo Browser opened. To stop, close the "ZINNOV server" window (minimised in the taskbar).
pause
endlocal
