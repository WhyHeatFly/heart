@echo off
rem Build heart.exe on Windows. Requires Python 3.9+ from python.org (check "Add python.exe to PATH").
cd /d "%~dp0"

where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% --version || (echo Python not found. Install it from https://www.python.org/downloads/ & pause & exit /b 1)

%PY% -m pip install --upgrade pygame pyinstaller || (pause & exit /b 1)
%PY% -m PyInstaller --onefile --windowed --clean --name heart heart.py || (pause & exit /b 1)

copy /y dist\heart.exe heart.exe >nul
echo.
echo Done: %~dp0heart.exe
pause
