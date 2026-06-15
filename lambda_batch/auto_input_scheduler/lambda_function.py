"""EventBridgeから自動入力スケジューラを起動するLambdaハンドラ。"""

from src.batch.auto_input_scheduler.autoInputScheduler import AutoInputScheduler


def lambda_handler(event, context):
    """
    有効化されたBELC/ETC自動入力を実行する。

    Args:
        event (dict): EventBridgeから渡されるスケジュールイベント。
        context (LambdaContext): AWS Lambda実行コンテキスト。

    Returns:
        dict: スケジューラの標準Lambdaレスポンス。
    """
    normalized_event = dict(event or {})
    normalized_event.setdefault("headers", {})
    normalized_event.setdefault("body", {"action": "scheduled"})
    return AutoInputScheduler().lambda_handler(normalized_event, context)
