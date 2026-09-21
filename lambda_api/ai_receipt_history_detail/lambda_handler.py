"""AIレシート履歴詳細Lambda。"""

import json

from src.api.kakeibo.receipt.ai_receipt.history_reference.aiReceiptHistoryDetail import AiReceiptHistoryDetail

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else dict(event.get("body") or {})
    path = event.get("pathParameters") or {}
    body["analysisId"] = path.get("analysis_id")
    return AiReceiptHistoryDetail().lambda_handler({**event, "body": body}, context)
