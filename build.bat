@echo off
cd /d "%~dp0"
if not exist .venv ( echo Run setup.bat first. & pause & exit /b 1 )
call .venv\Scripts\activate.bat
pip install pyinstaller || exit /b 1
python tools_dev\make_icon.py || exit /b 1
pyinstaller vega.spec --noconfirm --clean || (echo BUILD FAILED & pause & exit /b 1)
echo.
echo Built: dist\Vega\Vega.exe   (copy the whole dist\Vega folder wherever you like)
echo Open Vega, then Settings ^> Startup ^& data ^> "Create desktop shortcut" / "Start with Windows".
pause
