@echo off
cd /d "%~dp0"
title ICP OS generator
python icp_os_generator.py
if errorlevel 1 py -3 icp_os_generator.py
pause
