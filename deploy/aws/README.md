# AWS デプロイ手順

このフォルダーには、Home Kakeibo の Lambda バックエンドを AWS へデプロイするための補助ファイルがあります。

## ファイル

- `deploy_aws.bat`: layer 作成、handler zip 作成、SAM デプロイを実行します。
- `deploy_aws.sh`: macOS / Linux 用のデプロイスクリプトです。
- `deploy_aws.env.example.bat`: 設定ファイルのひな形です。
- `deploy_aws.env.example.sh`: macOS / Linux 用設定ファイルのひな形です。
- `deploy_aws.env.bat`: 自分の AWS / DB / API key を入れるローカル専用ファイルです。Git へ含めないでください。
- `application.lambda.yaml`: Lambda 用の安全なアプリ設定です。

## 実行

```bat
deploy_backend.bat
```

または、このフォルダーから直接実行します。

```bat
deploy\aws\deploy_aws.bat
```

macOS では設定ファイルを作成してから実行します。

```bash
cp deploy/aws/deploy_aws.env.example.sh deploy/aws/deploy_aws.env.sh
./deploy/aws/deploy_aws.sh
```

## 処理内容

1. `lambda/requirements-layer.txt` の依存ライブラリを `dist_lambda/layer/python` へインストールします。
2. `backend/` と `src/` を layer にコピーします。
3. `application.lambda.yaml` を layer 内の `src/common/config/application.yaml` に置き換えます。
4. layer zip を作成し、`aws lambda publish-layer-version` で公開します。
5. 関数 zip には `lambda/*.py` の handler だけを入れます。
6. `sam deploy` で API Gateway と固定名 Lambda 関数を更新します。

AI レシート解析は外部 AI 用 API Gateway を呼び出さず、Layer に含まれる `GeminiReceiptAnalyzer` を API 関数から直接呼び出します。Gemini 設定は Layer にコピーされる `deploy/aws/application.lambda.yaml` の `ai_receipt` に設定します。

## S3 / CloudFront

この分割版で EXE を使う場合、通常 `FRONTEND_S3_URI` と `FRONTEND_CLOUDFRONT_DISTRIBUTION_ID` は空で構いません。

```bat
set "FRONTEND_S3_URI="
set "FRONTEND_CLOUDFRONT_DISTRIBUTION_ID="
```

Web 版として公開する場合だけ、S3 へアップロードされるのは `frontend-react/dist` の静的ファイルです。CloudFront はその S3 ファイルを配信します。Lambda handler、layer、DB データは S3/CloudFront の配信対象ではありません。
