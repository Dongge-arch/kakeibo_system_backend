@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM パス設定
set LAMBDA_DIR=..\lambda
set LOG_FILE=test_results_%date:~0,4%%date:~5,2%%date:~10,2%_%time:~0,2%%time:~3,2%%time:~6,2%.log
set TOTAL=0
set PASSED=0
set FAILED=0

REM ログファイル作成
echo ========================================== > %LOG_FILE%
echo ホーム家計簿システム Lambda API 全テスト >> %LOG_FILE%
echo 開始時刻: %date% %time% >> %LOG_FILE%
echo ========================================== >> %LOG_FILE%

echo.
echo ========================================== 
echo   ホーム家計簿システム Lambda API 全テスト
echo   開始時刻: %date% %time%
echo ========================================== 
echo.

REM すべての lambda ディレクトリを列挙
for /d %%D in (%LAMBDA_DIR%\*) do (
    set FOLDER_NAME=%%~nxD
    set LAMBDA_FUNC_BAT=%%D\lambda_function.bat
    
    if exist "!LAMBDA_FUNC_BAT!" (
        set /a TOTAL+=1
        echo.
        echo [!TOTAL!] テスト中: !FOLDER_NAME!
        echo [!TOTAL!] テスト中: !FOLDER_NAME! >> %LOG_FILE%
        
        REM Lambda 関数実行
        cd "%%D"
        call lambda_function.bat >temp_output.txt 2>&1
        set EXIT_CODE=!ERRORLEVEL!
        cd %~dp0
        
        REM 成功確認
        findstr /C:"statusCode" "%%D\temp_output.txt" >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set /a PASSED+=1
            echo   ✓ 成功
            echo   ✓ 成功 >> %LOG_FILE%
        ) else (
            set /a FAILED+=1
            echo   ✗ 失敗 (終了コード: !EXIT_CODE!)
            echo   ✗ 失敗 (終了コード: !EXIT_CODE!) >> %LOG_FILE%
            REM エラー詳細を出力
            type "%%D\temp_output.txt" >> %LOG_FILE%
        )
        del "%%D\temp_output.txt" 2>nul
    )
)

REM テスト摘要を出力
echo.
echo.
echo ========================================== 
echo   テスト結果
echo   合計: %TOTAL%
echo   成功: %PASSED%
echo   失敗: %FAILED%
echo   終了時刻: %date% %time%
echo ========================================== 
echo.

echo. >> %LOG_FILE%
echo ========================================== >> %LOG_FILE%
echo   テスト結果 >> %LOG_FILE%
echo   合計: %TOTAL% >> %LOG_FILE%
echo   成功: %PASSED% >> %LOG_FILE%
echo   失敗: %FAILED% >> %LOG_FILE%
echo   終了時刻: %date% %time% >> %LOG_FILE%
echo ========================================== >> %LOG_FILE%

REM ログファイルを表示
echo.
echo 詳細ログはこちらに保存されました: %LOG_FILE%
echo.
pause
