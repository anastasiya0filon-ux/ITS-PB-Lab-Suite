@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Installing packages for build...
python -m pip install --upgrade pip
python -m pip install pillow pyinstaller
echo Building EXE...
pyinstaller --noconfirm --onefile --windowed --name "Токсичность" --add-data "tox_template.docx;." --add-data "plot_background.png;." toxicity_generator.py
echo.
echo Ready file: dist\Токсичность.exe
pause
