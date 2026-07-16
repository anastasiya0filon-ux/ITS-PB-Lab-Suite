@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -u BUILD_WIN64_TEST_RELEASE_RC2_PORTABLE_1G.py
echo.
pause
