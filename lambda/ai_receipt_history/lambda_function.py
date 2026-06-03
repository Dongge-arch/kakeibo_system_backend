from src.api.receipt.ai_receipt.aiReceiptApi import AiReceiptApi
import os

from src.common.config import APP_CONFIG
import json

AI_RECEIPT_CONFIG = APP_CONFIG.get("ai_receipt", {})
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or AI_RECEIPT_CONFIG.get("gemini_api_key", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or AI_RECEIPT_CONFIG.get("gemini_model", "gemini-2.5-flash-lite")

def _body(event):
    if isinstance(event.get("body"), str):
        return json.loads(event.get("body") or "{}")
    return event.get("body") or {}

def _set_body(event, body):
    event["body"] = body
    return event

def lambda_handler(event, context):
    body = _body(event)
    query = event.get("queryStringParameters") or {}
    path = event.get("pathParameters") or {}
    body["action"] = "list_history"
    event = _set_body(event, body)
    return AiReceiptApi(gemini_api_key=GEMINI_API_KEY, gemini_model=GEMINI_MODEL).lambda_handler(event, context)
