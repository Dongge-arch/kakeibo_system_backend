@echo off
setlocal EnableExtensions DisableDelayedExpansion

REM SPDX-License-Identifier: MIT
REM Copyright (c) 2026 Home Kakeibo System Contributors

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "ROOT_DIR=%%~fI\"
set "DIST_DIR=%ROOT_DIR%dist_lambda"
set "LAYER_DIR=%DIST_DIR%\layer"
set "FUNCTION_DIR=%DIST_DIR%\function"
set "LAYER_ZIP=%DIST_DIR%\home-kakeibo-layer.zip"
set "FUNCTION_ZIP=%DIST_DIR%\home-kakeibo-api-function.zip"
set "LAMBDA_CONFIG_TEMPLATE=%SCRIPT_DIR%application.lambda.yaml"

if exist "%SCRIPT_DIR%deploy_aws.env.bat" call "%SCRIPT_DIR%deploy_aws.env.bat"

if not defined AWS_REGION set "AWS_REGION=ap-northeast-1"
if not defined STACK_NAME set "STACK_NAME=home-kakeibo-api"
if not defined LAYER_NAME set "LAYER_NAME=home-kakeibo-layer"
if not defined PYTHON_RUNTIME set "PYTHON_RUNTIME=python3.12"
if not defined PYTHON_VERSION set "PYTHON_VERSION=3.12"
if not defined ARCHITECTURE set "ARCHITECTURE=arm64"
if not defined LAYER_PLATFORM set "LAYER_PLATFORM=manylinux2014_aarch64"
if not defined KAKEIBO_DATABASE_INITIALIZE set "KAKEIBO_DATABASE_INITIALIZE=false"
if not defined SUPPLIER_LOGO_S3_BUCKET set "SUPPLIER_LOGO_S3_BUCKET=inv-logos"
if not defined FRONTEND_BUILD_DRIVE set "FRONTEND_BUILD_DRIVE=K:"

if not defined KAKEIBO_PYTHON (
    if exist "C:\Miniforge\envs\HOME_KICHEN_SYSTEM_ENV\python.exe" (
        set "KAKEIBO_PYTHON=C:\Miniforge\envs\HOME_KICHEN_SYSTEM_ENV\python.exe"
    ) else (
        set "KAKEIBO_PYTHON=python"
    )
)

where aws >nul 2>nul
if errorlevel 1 (
    echo [ERROR] AWS CLI was not found. Install AWS CLI and run aws configure first.
    exit /b 1
)

if defined AWS_PROFILE (
    echo [CHECK] AWS profile: %AWS_PROFILE%
    aws configure list-profiles | findstr /I /X /C:"%AWS_PROFILE%" >nul
    if errorlevel 1 (
        echo [ERROR] AWS_PROFILE "%AWS_PROFILE%" was not found.
        echo [INFO] Existing AWS CLI profiles:
        aws configure list-profiles
        echo [INFO] Update deploy\aws\deploy_aws.env.bat or run aws configure --profile %AWS_PROFILE%.
        exit /b 1
    )
) else (
    echo [CHECK] AWS profile: default credential chain
)

echo [CHECK] Checking AWS credentials...
aws sts get-caller-identity --region "%AWS_REGION%" >nul
if errorlevel 1 (
    echo [ERROR] AWS credentials are not available or are not valid.
    echo [INFO] Run aws configure --profile your-profile-name, then set AWS_PROFILE in deploy\aws\deploy_aws.env.bat.
    exit /b 1
)

where sam >nul 2>nul
if errorlevel 1 (
    echo [ERROR] AWS SAM CLI was not found. Install AWS SAM CLI first.
    exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
    if defined FRONTEND_S3_URI (
        echo [ERROR] npm was not found. It is required when FRONTEND_S3_URI is set.
        exit /b 1
    )
)

if not defined KAKEIBO_DATABASE_URL (
    set /p "KAKEIBO_DATABASE_URL=PostgreSQL connection string: "
)
if not defined KAKEIBO_DATABASE_URL (
    echo [ERROR] KAKEIBO_DATABASE_URL is required.
    exit /b 1
)

if not defined KAKEIBO_JWT_SECRET (
    set /p "KAKEIBO_JWT_SECRET=JWT secret, or press Enter to auto-generate: "
)
if not defined KAKEIBO_JWT_SECRET (
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"') do set "KAKEIBO_JWT_SECRET=%%S"
    echo [INFO] JWT secret was auto-generated.
)

if not defined KAKEIBO_API_KEY (
    set /p "KAKEIBO_API_KEY=Application API key, or press Enter to auto-generate: "
)
if not defined KAKEIBO_API_KEY (
    for /f "delims=" %%S in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N')"') do set "KAKEIBO_API_KEY=%%S"
    echo [INFO] Application API key was auto-generated.
)

if not defined FRONTEND_CORS_ORIGIN (
    set /p "FRONTEND_CORS_ORIGIN=Frontend CORS origin, or press Enter for *: "
)
if not defined FRONTEND_CORS_ORIGIN (
    set "FRONTEND_CORS_ORIGIN=*"
    echo [WARN] FRONTEND_CORS_ORIGIN is *. Set your CloudFront origin for production.
)

echo.
echo [INFO] Root:   %ROOT_DIR%
if defined AWS_PROFILE echo [INFO] Profile: %AWS_PROFILE%
echo [INFO] Region: %AWS_REGION%
echo [INFO] Stack:  %STACK_NAME%
echo [INFO] Layer:  %LAYER_NAME%
echo [INFO] Target: %PYTHON_RUNTIME% / %ARCHITECTURE%
echo.

if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%LAYER_DIR%\python"
if errorlevel 1 exit /b 1
mkdir "%FUNCTION_DIR%"
if errorlevel 1 exit /b 1

echo [1/8] Installing Lambda layer packages...
"%KAKEIBO_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

"%KAKEIBO_PYTHON%" -m pip install -r "%ROOT_DIR%lambda_api\requirements-layer.txt" -t "%LAYER_DIR%\python" --platform "%LAYER_PLATFORM%" --implementation cp --python-version "%PYTHON_VERSION%" --only-binary=:all: --upgrade
if errorlevel 1 exit /b 1

echo [2/9] Staging application code into Lambda layer...
call :copy_tree "%ROOT_DIR%src" "%LAYER_DIR%\python\src"
if errorlevel 1 exit /b 1

echo [3/9] Replacing layered application.yaml with Lambda-safe config...
if not exist "%LAMBDA_CONFIG_TEMPLATE%" (
    echo [ERROR] Missing config template: %LAMBDA_CONFIG_TEMPLATE%
    exit /b 1
)
copy /Y "%LAMBDA_CONFIG_TEMPLATE%" "%LAYER_DIR%\python\src\common\config\application.yaml" >nul
if errorlevel 1 exit /b 1

echo [4/9] Creating Lambda layer zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%LAYER_DIR%\python' -DestinationPath '%LAYER_ZIP%' -Force"
if errorlevel 1 exit /b 1

echo [5/9] Publishing Lambda layer...
for /f "delims=" %%A in ('aws lambda publish-layer-version --region "%AWS_REGION%" --layer-name "%LAYER_NAME%" --zip-file "fileb://%LAYER_ZIP%" --compatible-runtimes "%PYTHON_RUNTIME%" --compatible-architectures "%ARCHITECTURE%" --query LayerVersionArn --output text') do set "HOME_KAKEIBO_LAYER_ARN=%%A"
if not defined HOME_KAKEIBO_LAYER_ARN (
    echo [ERROR] Failed to publish Lambda layer.
    exit /b 1
)
echo [INFO] Layer ARN: %HOME_KAKEIBO_LAYER_ARN%

echo [6/9] Staging Lambda handler source only...
call :copy_tree "%ROOT_DIR%lambda_api" "%FUNCTION_DIR%\lambda_api"
if errorlevel 1 exit /b 1
call :copy_tree "%ROOT_DIR%lambda_batch" "%FUNCTION_DIR%\lambda_batch"
if errorlevel 1 exit /b 1

echo [7/9] Creating Lambda handler zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%FUNCTION_DIR%\*' -DestinationPath '%FUNCTION_ZIP%' -Force"
if errorlevel 1 exit /b 1

echo [8/9] Deploying SAM stack...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$params = @('HomeKakeiboLayerArn=' + $env:HOME_KAKEIBO_LAYER_ARN, 'KakeiboDatabaseUrl=' + $env:KAKEIBO_DATABASE_URL, 'KakeiboDatabaseInitialize=' + $env:KAKEIBO_DATABASE_INITIALIZE, 'KakeiboJwtSecret=' + $env:KAKEIBO_JWT_SECRET, 'KakeiboApiKey=' + $env:KAKEIBO_API_KEY, 'FrontendCorsOrigin=' + $env:FRONTEND_CORS_ORIGIN); if ($env:SUPPLIER_LOGO_S3_BUCKET) { $params += 'SupplierLogoBucketName=' + $env:SUPPLIER_LOGO_S3_BUCKET }; & sam deploy --template-file ($env:ROOT_DIR + 'template.yaml') --stack-name $env:STACK_NAME --region $env:AWS_REGION --resolve-s3 --capabilities CAPABILITY_IAM --no-confirm-changeset --no-fail-on-empty-changeset --parameter-overrides $params; exit $LASTEXITCODE"
if errorlevel 1 exit /b 1

echo.
echo [DONE] Backend deploy completed.
echo [INFO] Stack outputs:
aws cloudformation describe-stacks --region "%AWS_REGION%" --stack-name "%STACK_NAME%" --query "Stacks[0].Outputs" --output table
if errorlevel 1 exit /b 1

echo [9/9] Frontend deploy check...
if /I "%KAKEIBO_SKIP_FRONTEND_DEPLOY%"=="true" (
    echo [FRONTEND] KAKEIBO_SKIP_FRONTEND_DEPLOY is true. Skipping frontend upload.
) else if defined FRONTEND_S3_URI (
    call :deploy_frontend
    if errorlevel 1 exit /b 1
) else (
    echo [FRONTEND] FRONTEND_S3_URI is not set. Skipping frontend upload.
    echo [FRONTEND] Set FRONTEND_S3_URI in deploy\aws\deploy_aws.env.bat to enable it.
)

endlocal
exit /b 0

:copy_tree
setlocal
set "COPY_SOURCE=%~1"
set "COPY_TARGET=%~2"
if not exist "%COPY_TARGET%" mkdir "%COPY_TARGET%"
robocopy "%COPY_SOURCE%" "%COPY_TARGET%" /E /XD __pycache__ /XF *.pyc .DS_Store account.db home-kakeibo.log /NFL /NDL /NJH /NJS /NP >nul
set "ROBOCOPY_EXIT=%ERRORLEVEL%"
if %ROBOCOPY_EXIT% GEQ 8 (
    echo [ERROR] Failed to copy %COPY_SOURCE% to %COPY_TARGET%. Robocopy exit code %ROBOCOPY_EXIT%.
    endlocal
    exit /b 1
)
endlocal
exit /b 0

:deploy_frontend
setlocal EnableDelayedExpansion
echo [FRONTEND] Reading API URL from CloudFormation outputs...
for /f "delims=" %%U in ('aws cloudformation describe-stacks --region "%AWS_REGION%" --stack-name "%STACK_NAME%" --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue | [0]" --output text') do set "DEPLOYED_API_URL=%%U"
if not defined DEPLOYED_API_URL (
    echo [ERROR] Could not read ApiUrl from stack outputs.
    endlocal
    exit /b 1
)
if "!DEPLOYED_API_URL!"=="None" (
    echo [ERROR] ApiUrl output is empty.
    endlocal
    exit /b 1
)

echo [FRONTEND] Building React with API URL: !DEPLOYED_API_URL!
set "VITE_API_BASE_URL=!DEPLOYED_API_URL!"
set "VITE_API_KEY=%KAKEIBO_API_KEY%"
if exist "%FRONTEND_BUILD_DRIVE%\" (
    echo [WARN] %FRONTEND_BUILD_DRIVE% already exists. Building from normal path.
    pushd "%ROOT_DIR%frontend-react"
    call npm run build
    if errorlevel 1 (
        popd
        endlocal
        exit /b 1
    )
    popd
) else (
    subst %FRONTEND_BUILD_DRIVE% "%ROOT_DIR%"
    pushd "%FRONTEND_BUILD_DRIVE%\frontend-react"
    call npm run build
    if errorlevel 1 (
        popd
        subst %FRONTEND_BUILD_DRIVE% /d
        endlocal
        exit /b 1
    )
    popd
    subst %FRONTEND_BUILD_DRIVE% /d
)

echo [FRONTEND] Uploading to S3: %FRONTEND_S3_URI%
aws s3 sync "%ROOT_DIR%frontend-react\dist" "%FRONTEND_S3_URI%" --region "%AWS_REGION%" --delete
if errorlevel 1 (
    endlocal
    exit /b 1
)

if defined FRONTEND_CLOUDFRONT_DISTRIBUTION_ID (
    echo [FRONTEND] Creating CloudFront invalidation...
    aws cloudfront create-invalidation --distribution-id "%FRONTEND_CLOUDFRONT_DISTRIBUTION_ID%" --paths "/*"
    if errorlevel 1 (
        endlocal
        exit /b 1
    )
)

echo [FRONTEND] Frontend deploy completed.
endlocal
exit /b 0
