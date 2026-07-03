"""EventBridgeから自動入力スケジューラを起動するLambdaハンドラ。"""

from src.batch.auto_input_scheduler.autoInputScheduler import AutoInputScheduler
import os

from src.common.config import APP_CONFIG
AI_RECEIPT_CONFIG = APP_CONFIG.get("ai_receipt", {})
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or AI_RECEIPT_CONFIG.get("gemini_api_key", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or AI_RECEIPT_CONFIG.get("gemini_model", "gemini-2.5-flash-lite")

    
def lambda_handler(event, context):
    """
    有効化されたBELC/ETC自動入力を実行する。

    Args:
        event (dict): EventBridgeから渡されるスケジュールイベント。
        context (LambdaContext): AWS Lambda実行コンテキスト。

    Returns:
        dict: スケジューラの標準Lambdaレスポンス。
    """
    return AutoInputScheduler().lambda_handler(event, context)
