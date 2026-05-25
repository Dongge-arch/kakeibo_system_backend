# Home Kakeibo Lambda Backend

このフォルダーは Lambda / API Gateway 用のバックエンド専用コードです。

- `lambda/`: Lambda の起動入口だけを置きます。関数 zip にはこの handler だけが入ります。
- `backend/`: FastAPI アプリ本体です。Lambda Layer に入ります。
- `src/`: 業務 API、DB、認証、共通ロジックです。Lambda Layer に入ります。
- `template.yaml`: AWS SAM テンプレートです。
- `deploy/aws/deploy_aws.bat`: layer 作成、handler zip 作成、`sam deploy` を実行します。

## デプロイ前の設定

`deploy\aws\deploy_aws.env.bat` を作成し、AWS / DB / API key を設定します。

```bat
set "AWS_PROFILE=receipt-dev"
set "AWS_REGION=ap-northeast-1"
set "STACK_NAME=home-kakeibo-api"
set "LAYER_NAME=home-kakeibo-layer"
set "KAKEIBO_DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require"
set "KAKEIBO_DATABASE_INITIALIZE=false"
set "KAKEIBO_JWT_SECRET=replace-with-a-long-random-secret"
set "KAKEIBO_API_KEY=replace-with-a-long-random-api-key"
set "FRONTEND_CORS_ORIGIN=*"
```

## デプロイ

```bat
deploy_backend.bat
```

デプロイ後、CloudFormation output の `ApiUrl` をフロントエンド側の `frontend-config.json` に設定します。

## Lambda Layer と関数 zip

現在の構成では、Lambda 関数本体は起動 handler だけです。

- 関数 zip: `lambda/__init__.py`, `lambda/api_handler.py`, `lambda/receipt_ai_handler.py`
- Layer: Python 依存ライブラリ、`backend/`, `src/`

バックエンドの処理を更新した場合は、再度 `deploy_backend.bat` を実行してください。新しい layer version が発行され、固定名の Lambda 関数へ反映されます。

## 固定 Lambda 関数名

SAM テンプレートでは次の固定名を使います。

- API: `home-kakeibo-api-function`
- Receipt AI: `home-kakeibo-receipt-ai-function`

CloudFormation のランダムな物理名ではなく、AWS コンソール上でも見つけやすい名前になります。

## S3 / CloudFront について

デスクトップ EXE で使う場合、S3 と CloudFront は不要です。EXE はローカルで React の静的ファイルを配信し、Lambda API を直接呼びます。

Web 版として公開したい場合だけ、S3 には `frontend-react/dist` の中身を保存します。

- `index.html`
- `config.js`
- `assets/*.js`
- `assets/*.css`

CloudFront はその S3 静的サイトを配信するための CDN です。バックエンドの Lambda コードや DB データを S3 に置くものではありません。
