# Home Kakeibo Lambda バックエンド

このフォルダは、家計簿アプリのバックエンドだけを独立して更新・ビルド・デプロイするためのフォルダです。API Gateway + Lambda + PostgreSQL を前提にしています。SQLite 用の運用は行いません。

## 役割

- フロントエンドから呼ばれる REST API を提供します。
- ユーザー登録、ログイン、パスワード再設定、レシート、入金、カテゴリ、予算、設定、AI 利用状況を処理します。
- データは PostgreSQL に保存します。
- Lambda の起動関数は薄く保ち、共通コードや API 実装は Layer に含めます。

## フォルダ構成

```text
home_kakeibo_lambda_backend/
  backend/                       Lambda 起動関数
  src/                           API 実装、共通処理、DB 接続
  lambda/                        Layer 作成用ファイル
  deploy/aws/                    AWS デプロイ用スクリプトと設定例
  template.yaml                  SAM/CloudFormation テンプレート
  deploy_backend.bat             バックエンド一括デプロイ
  README_LAMBDA_BACKEND.md       この説明書
```

## 必要な環境

- AWS CLI
- AWS SAM CLI
- Python
- PostgreSQL
- デプロイ先 AWS アカウントの認証情報

AWS 認証情報はこのフォルダに直接置かず、AWS CLI の profile、環境変数、または安全な秘密情報管理で扱ってください。

## 環境設定

`deploy/aws/deploy_aws.env.example.bat` を参考にして、ローカル用の `deploy/aws/deploy_aws.env.bat` を作成します。

設定する主な値は以下です。

- AWS region
- スタック名
- Lambda 関数名
- Layer 名
- API Gateway 設定
- PostgreSQL 接続情報
- CORS 許可オリジン
- 認証・API key 関連設定

`deploy_aws.env.bat` は秘密情報を含むため Git 管理対象外です。

## デプロイ

```powershell
cd C:\Users\董 昊哲\Desktop\home_kakeibo_lambda_backend
.\deploy_backend.bat
```

デプロイ後、API Gateway の URL をフロントエンド設定に反映します。

## Lambda と Layer の考え方

この構成では、Lambda 起動関数にはリクエストを受けてアプリ本体へ渡す最小限のコードだけを置きます。API 実装、共通処理、DB 接続、業務ロジックは Layer 側に入れます。

更新時の基本方針は以下です。

- 起動関数だけ変更した場合: Lambda 関数を更新
- API 実装や共通処理を変更した場合: Layer を作成し直して Lambda に紐づけ
- `template.yaml` を変更した場合: スタックを再デプロイ

## データベース

バックエンドは PostgreSQL 前提です。テーブル定義、SQL、DB 接続は PostgreSQL 用に統一します。SQLite の DB ファイルや SQLite 専用 SQL は使用しません。

レシート更新 API は、レシート本体だけでなく、場所・店舗情報を持つ `invoice_registration` も更新します。未登録のインボイス番号が来た場合は新規登録します。

## フロントエンドとの接続

フロントエンド側では以下を設定します。

- `apiBaseUrl`: API Gateway の URL
- `apiKey`: API Gateway で必要な場合のみ
- CloudFront ドメインを使う場合: CORS 許可オリジンに CloudFront ドメインを追加

未ログイン時は API 操作を制限するため、フロントエンドとバックエンドの両方でユーザー情報・認証状態を確認します。

## セキュリティ

次のファイルは Git に入れないでください。

- `deploy/aws/deploy_aws.env.bat`
- `.env`、`.env.*`
- AWS 認証情報
- API key、DB パスワード、JWT secret を含むファイル
- 秘密鍵、証明書、pem/key/pfx/p12
- ローカル DB、ログ、ビルド成果物

`.gitignore` に登録済みですが、デプロイ前後に `git status` で必ず確認してください。

## 動作確認

構文確認:

```powershell
python -m py_compile backend\app.py src\api\receipt\receipt_update_delete\receiptUpdateDelete.py
```

主な確認観点:

- ログインできる
- 未ログイン時に操作できない
- レシート登録・更新・削除ができる
- レシート更新時に店舗名、インボイス番号、税区分が更新される
- 入金登録ができる
- カテゴリと予算が取得・保存できる
- CloudFront から API を呼べる

## よくある問題

### fetch failed または API error

- Lambda が最新デプロイになっているか確認してください。
- API Gateway の URL がフロントエンド設定と一致しているか確認してください。
- CORS に CloudFront ドメインが入っているか確認してください。
- API key が必要な API で key が不足していないか確認してください。

### DB に書けるが画面に出ない

- 登録時のユーザー ID と取得時のユーザー ID が一致しているか確認してください。
- フロントエンドが headers にユーザー情報を付与しているか確認してください。
- PostgreSQL の `del_flag`、日付形式、カテゴリ ID/名称の整合性を確認してください。

### 更新したのに Lambda の挙動が変わらない

Layer の更新漏れ、Lambda への Layer 紐づけ漏れ、または CloudFormation スタック未更新の可能性があります。`deploy_backend.bat` を再実行し、AWS Console で Lambda の最終更新日時を確認してください。
