@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "import PySide6; import win32com.client" >nul 2>&1
if errorlevel 1 goto setup
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
exit /b
:setup
echo Dependencies are missing. Starting local setup...
call install_windows.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
