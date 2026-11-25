@echo off
REM ZINNOV | PE Intelligence Command Center: one-time setup (no administrator rights needed)
setlocal
cd /d "%~dp0"
echo.
echo === ZINNOV PE Intelligence Command Center: setup ===
echo.

set "PY="
where py >nul 2>nul && (py -3.13 --version >nul 2>nul && set "PY=py -3.13")
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python was not found on PATH.
  echo Install Python 3.13 from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  echo Then run SETUP.bat again.
  pause
  exit /b 1
)
%PY% --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create the virtual environment.
    pause
    exit /b 1
  )
)

echo Installing dependencies from requirements.txt ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed. Check your internet connection and try again.
  echo If a proxy blocks pip, ask your IT team for the pip proxy settings.
  pause
  exit /b 1
)

echo Checking the database ...
if not exist "data\intel.db" (
  echo [ERROR] data\intel.db is missing from this folder. Re-extract the ZIP file in full.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -I -c "import sqlite3,sys; c=sqlite3.connect('data/intel.db'); n=c.execute('select count(*) from companies').fetchone()[0]; sys.exit(0 if n>0 else 1)"
if errorlevel 1 (
  echo [ERROR] The database is empty or unreadable.
  pause
  exit /b 1
)

echo.
echo Setup complete. Double-click START.bat to launch the platform.
pause
endlocal
