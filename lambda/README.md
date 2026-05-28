# Lambda handlers

- `api_handler.py`: API Gateway / Lambda Function URL から FastAPI アプリ全体を Mangum 経由で呼び出す入口です。
- `requirements-layer.txt`: Lambda Layer に入れる Python 依存関係です。

関数 zip には `lambda/*.py` の薄い handler だけを含めます。`backend/`、`src/`、依存ライブラリ、AI レシート解析クラスは Layer zip に分離します。
