# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""Lambda直接呼び出し用のAIレシート解析入口。"""

import os

from src.api.receipt.ai_receipt.aiReceiptApi import AiReceiptApi
from src.api.utils import call_api
from src.common.config import APP_CONFIG


AI_RECEIPT_CONFIG = APP_CONFIG.get("ai_receipt", {})


def handler(event, _context):
    """画像解析payloadを受け取り、AiReceiptApiを直接実行する。"""
    body = event.get("body") if isinstance(event, dict) else {}
    if not isinstance(body, dict):
        body = event if isinstance(event, dict) else {}

    api = AiReceiptApi(
        service_url=os.environ.get("AI_RECEIPT_API_URL") or AI_RECEIPT_CONFIG.get("url", ""),
        api_key=os.environ.get("AI_RECEIPT_API_KEY") or AI_RECEIPT_CONFIG.get("api_key", ""),
    )
    return call_api(api, {"action": "analyze", **body})
