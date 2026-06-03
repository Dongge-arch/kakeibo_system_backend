# Lambda API 全テストスクリプト

## 説明

`run_all_tests_simple.bat` はすべての Lambda API テストをワンクリックで実行します。

## 使用方法

### Windows コマンドライン
```cmd
cd C:\Users\董 昊哲\Desktop\home_kakeibo_lambda_backend\unit_test
run_all_tests_simple.bat
```

### または run_all_tests_simple.bat ファイルを直接ダブルクリック

## 機能特性

✓ すべての lambda フォルダを自動走査  
✓ 各 API の lambda_function.bat を実行  
✓ テスト結果を統計（成功/失敗）  
✓ タイムスタンプ付きの詳細ログファイル生成（test_results_YYYYMMDD_HHMMSS.log）  
✓ リアルタイムでテスト進度を表示  

## テスト結果

テスト完了後、以下が表示されます：
- 総テスト数
- 成功数
- 失敗数
- ログファイル位置

## ログファイル

ログファイル形式：`test_results_YYYYMMDD_HHMMSS.log`

詳細情報を含みます：
- 各 API のテスト結果
- エラーメッセージ（ある場合）
- 開始時刻と終了時刻

## 前置条件

- python-lambda-local がインストールされていること
- すべての API フォルダに lambda_function.bat が含まれていること
- すべての API フォルダに event.json（テストデータ）が含まれていること

## 注意事項

- スクリプトは unit_test フォルダから実行する必要があります
- 環境変数 PYTHONPATH が正しく設定されていることを確認してください
- Python 仮想環境をアクティベート後の実行をお勧めします
