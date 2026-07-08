@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconsole --clean --name "ITS-PB Lab Suite" --add-data "app\assets;assets" --add-data "app\modules;modules" app\main.pyw
pause
