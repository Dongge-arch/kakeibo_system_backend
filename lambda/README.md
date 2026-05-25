# Lambda handlers

- `api_handler.py`: API Gateway / Lambda Function URL から FastAPI アプリ全体を Mangum 経由で呼び出す入口です。
- `receipt_ai_handler.py`: AI レシート解析だけを直接 invoke するための Lambda handler です。
- `requirements-layer.txt`: Lambda Layer に入れる Python 依存関係です。

関数 zip には `backend/`、`src/`、`lambda/` を含めます。依存ライブラリは Layer zip として分離します。
