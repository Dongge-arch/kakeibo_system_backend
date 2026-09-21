"""AIレシート解析Lambda。"""

from src.api.kakeibo.receipt.ai_receipt.analyze.aiReceiptAnalyze import AiReceiptAnalyze
import os

from src.common.config import APP_CONFIG

AI_RECEIPT_CONFIG = APP_CONFIG.get("ai_receipt", {})
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or AI_RECEIPT_CONFIG.get("gemini_api_key", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or AI_RECEIPT_CONFIG.get("gemini_model", "gemini-2.5-flash-lite")

def lambda_handler(event, context):
    return AiReceiptAnalyze(gemini_api_key=GEMINI_API_KEY, gemini_model=GEMINI_MODEL).lambda_handler(event, context)
