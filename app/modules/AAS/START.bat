@echo off
cd /d "%~dp0"
echo Starting AAS generator...
(py -3 aas_report_generator.py) || (python aas_report_generator.py)
if errorlevel 1 (
  echo.
  echo [ERROR] Generator stopped with an error.
  pause
)
