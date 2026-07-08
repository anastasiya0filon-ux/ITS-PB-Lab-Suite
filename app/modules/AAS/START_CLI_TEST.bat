@echo off
cd /d "%~dp0"
echo Testing Excel generation...
(py -3 aas_report_generator.py --excel AAS_template.xlsx 07.07.2026 normal) || (python aas_report_generator.py --excel AAS_template.xlsx 07.07.2026 normal)
pause
