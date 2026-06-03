@echo off
setlocal

set "EXCEL_PATH=C:\Users\董 昊哲\Desktop\kakeibo_2026.xlsx"
set "TARGET_URL=%TARGET_URL%"
if "%TARGET_URL%"=="" set "TARGET_URL=http://localhost:8000/receipt/newReceiptRegistration"
set "API_KEY=%API_KEY%"

py -3 "%~dp0run_excel_curl.py" --excel "%EXCEL_PATH%" --target-url "%TARGET_URL%" --api-key "%API_KEY%"

endlocal
