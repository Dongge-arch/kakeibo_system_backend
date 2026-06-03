@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM Deploys the AWS Lambda functions and API Gateway stack for Home Kakeibo.
REM Configure deploy\aws\deploy_aws.env.bat before running this file.

set "ROOT_DIR=%~dp0"
set "DEPLOY_SCRIPT=%ROOT_DIR%deploy\aws\deploy_aws.bat"
set "KAKEIBO_SKIP_FRONTEND_DEPLOY=true"

if not exist "%DEPLOY_SCRIPT%" (
    echo [ERROR] Deploy script was not found: %DEPLOY_SCRIPT%
    exit /b 1
)

echo [INFO] Deploying Lambda functions and API Gateway...
call "%DEPLOY_SCRIPT%"
set "DEPLOY_EXIT_CODE=%ERRORLEVEL%"

if not "%DEPLOY_EXIT_CODE%"=="0" (
    echo [ERROR] Lambda/API Gateway deploy failed. Exit code: %DEPLOY_EXIT_CODE%
    exit /b %DEPLOY_EXIT_CODE%
)

echo [DONE] Lambda/API Gateway deploy completed.
endlocal
exit /b 0
