@echo off
setlocal EnableExtensions

REM SPDX-License-Identifier: MIT

cd /d "%~dp0"
call "%~dp0deploy\aws\deploy_aws.bat"
exit /b %ERRORLEVEL%
