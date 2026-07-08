@echo off
cd /d "%~dp0"
title ICP OS CLI test
python icp_os_generator.py --cli-test
if errorlevel 1 py -3 icp_os_generator.py --cli-test
pause
