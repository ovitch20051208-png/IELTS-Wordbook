@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call install_windows.bat
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean IELTSWordbook.spec
if errorlevel 1 goto failed
echo Build complete: dist\IELTSWordbook\IELTSWordbook.exe
echo Distribute the ENTIRE dist\IELTSWordbook folder, not just the exe.
pause
exit /b 0
:failed
echo Build failed. See the error above.
pause
exit /b 1
