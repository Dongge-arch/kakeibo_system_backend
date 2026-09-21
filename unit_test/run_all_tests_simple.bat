@echo off
setlocal
cd /d "%~dp0.."
python -m pytest -q unit_test
exit /b %ERRORLEVEL%
