@echo off
rem Windows one-click build. Double-click this file. Needs 64-bit Python 3.12 (python.org) with "Add python.exe to PATH" ticked.
cd /d "%~dp0"
python --version || (echo Python not found. Install Python 3.12 64-bit from python.org first. & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || (echo pip install failed & pause & exit /b 1)
python -m pytest -q tests || (echo tests failed & pause & exit /b 1)
pyinstaller --noconfirm --clean --windowed --name PhoneTool --collect-all phonenumbers --collect-all python_calamine --hidden-import xlsxwriter app.py || (echo build failed & pause & exit /b 1)
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\PhoneTool -DestinationPath PhoneTool-windows.zip"
echo.
echo DONE. Program: dist\PhoneTool\PhoneTool.exe   Zip to send to client: PhoneTool-windows.zip
pause
