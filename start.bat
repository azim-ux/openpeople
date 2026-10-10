@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Install Python 3.12+ and follow README.md to create .venv first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" server.py --profile core-hr --db "%LOCALAPPDATA%\OpenPeople\openpeople.db" %*
