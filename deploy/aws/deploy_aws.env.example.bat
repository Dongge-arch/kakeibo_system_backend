@echo off
REM Copy this file to deploy_aws.env.bat and fill in your own values.
REM Do not commit deploy_aws.env.bat.

REM Optional: set this if you use a named AWS CLI profile.
REM Run "aws configure list-profiles" to see available profile names.
set "AWS_PROFILE="
set "AWS_REGION=ap-northeast-1"
set "STACK_NAME=home-kakeibo-api"
set "LAYER_NAME=home-kakeibo-layer"

REM Lambda target. Keep these aligned with template.yaml.
set "PYTHON_RUNTIME=python3.12"
set "PYTHON_VERSION=3.12"
set "ARCHITECTURE=arm64"
set "LAYER_PLATFORM=manylinux2014_aarch64"

REM Optional: set this if the project Python is not on PATH.
REM set "KAKEIBO_PYTHON=C:\Miniforge\envs\HOME_KICHEN_SYSTEM_ENV\python.exe"

REM Required for cloud deployment.
set "KAKEIBO_DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require"
set "KAKEIBO_DATABASE_INITIALIZE=false"
set "KAKEIBO_JWT_SECRET=replace-with-a-long-random-secret"
set "KAKEIBO_API_KEY=replace-with-a-long-random-api-key"
set "FRONTEND_CORS_ORIGIN=https://your-cloudfront-domain.example.com"

REM Optional frontend deployment.
REM If FRONTEND_S3_URI is set, deploy_aws.bat builds frontend-react/dist
REM with the deployed API URL and syncs it to S3.
set "FRONTEND_S3_URI="

REM Optional CloudFront invalidation after S3 upload.
set "FRONTEND_CLOUDFRONT_DISTRIBUTION_ID="

REM Optional temporary drive for npm build when the project path contains non-ASCII characters.
set "FRONTEND_BUILD_DRIVE=K:"
