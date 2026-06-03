@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM すべての Lambda API をテストするスクリプト
REM パス設定
cd /d "%~dp0"
set LAMBDA_DIR=..\lambda
set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~10,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set LOG_FILE=test_results_%TIMESTAMP%.log
set TOTAL=0
set PASSED=0
set FAILED=0

REM ログを初期化
(
    echo.
    echo =====================================================
    echo ホーム家計簿システム Lambda API 全テスト
    echo 開始時刻: %date% %time%
    echo =====================================================
    echo.
) > %LOG_FILE%

echo.
echo =====================================================
echo ホーム家計簿システム Lambda API 全テスト
echo 開始時刻: %date% %time%
echo =====================================================
echo.

REM 各 API をテスト
for /d %%D in (%LAMBDA_DIR%\*) do (
    set API_NAME=%%~nxD
    
    if exist "%%D\lambda_function.bat" (
        set /a TOTAL+=1
        
        echo [!TOTAL!] テスト中 !API_NAME!...
        echo [!TOTAL!] テスト中 !API_NAME! >> %LOG_FILE%
        
        REM Lambda テストを実行
        pushd "%%D"
        call lambda_function.bat > ..\output.txt 2>&1
        set ERRORCODE=!ERRORLEVEL!
        popd
        
        REM 出力にstatusCodeが含まれているか確認
        findstr /C:"statusCode" "..\output.txt" >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set /a PASSED+=1
            echo      ✓ 成功
            echo      ✓ 成功 >> %LOG_FILE%
        ) else (
            set /a FAILED+=1
            echo      ✗ 失敗
            echo      ✗ 失敗 >> %LOG_FILE%
            REM エラーの詳細をログに追加
            echo ---- 出力詳細 ---- >> %LOG_FILE%
            type ..\output.txt >> %LOG_FILE%
            echo ---- 出力終了 ---- >> %LOG_FILE%
        )
        del ..\output.txt 2>nul
    )
)

REM 失敗数を計算
set /a FAILED=TOTAL-PASSED

REM 摘要を出力
echo.
echo =====================================================
echo テスト結果
echo =====================================================
echo 合計: %TOTAL%
echo 成功: %PASSED%
echo 失敗: %FAILED%
echo 終了時刻: %date% %time%
echo =====================================================
echo ログファイル: %LOG_FILE%
echo.

REM ログに摘要を追加
(
    echo.
    echo =====================================================
    echo テスト結果
    echo =====================================================
    echo 合計: %TOTAL%
    echo 成功: %PASSED%
    echo 失敗: %FAILED%
    echo 終了時刻: %date% %time%
    echo =====================================================
) >> %LOG_FILE%

pause
