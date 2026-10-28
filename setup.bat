@echo off
cd /d "%~dp0"
where py >nul 2>nul || (echo Python 3.10-3.12 is required: https://www.python.org/downloads/ ^(tick "Add to PATH"^) & pause & exit /b 1)
if not exist .venv ( py -3 -m venv .venv || (echo Could not create the virtual environment & pause & exit /b 1) )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Dependency install failed & pause & exit /b 1)
echo.
echo Setup complete. Start the assistant with run.bat
pause
