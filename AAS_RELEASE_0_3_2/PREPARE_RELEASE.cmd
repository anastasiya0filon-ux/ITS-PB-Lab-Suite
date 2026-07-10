@echo off
chcp 65001 >nul
cd /d "%~dp0\.."

echo [1/4] Checking repository...
git status --short
if errorlevel 1 goto :error

echo [2/4] Building application...
if exist build rmdir /S /Q build
if exist dist rmdir /S /Q dist
call BUILD_EXE_ONCE.bat
if errorlevel 1 goto :error

echo [3/4] Creating tag...
git tag -a v0.3.2 -m "AAS 0.3.2: Al Ag Zn Cu Ni Co and unique measurement timestamps"
if errorlevel 1 goto :error
git push origin main
if errorlevel 1 goto :error
git push origin v0.3.2
if errorlevel 1 goto :error

echo [4/4] Done.
echo Create GitHub Release v0.3.2 and attach the fresh file from dist.
pause
exit /b 0

:error
echo RELEASE PREPARATION FAILED.
pause
exit /b 1
