@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 install.py) else (python install.py)
if not %errorlevel%==0 pause
