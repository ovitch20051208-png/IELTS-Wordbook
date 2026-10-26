@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 goto python_fallback
py -3 -c "import sys; sys.exit(sys.version_info < (3,11))"
if errorlevel 1 goto missing
py -3 -m venv .venv
goto install
:python_fallback
python -c "import sys; sys.exit(sys.version_info < (3,11))"
if errorlevel 1 goto missing
python -m venv .venv
:install
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Installation complete. Double-click run_windows.bat to start.
exit /b 0
:missing
echo Please install 64-bit Python 3.11 or later from https://www.python.org/downloads/windows/
pause
exit /b 1
:failed
echo Setup failed. Check the network and the error above, then try again.
pause
exit /b 1
