"""AIレシート履歴一覧Lambda。"""

from src.api.kakeibo.receipt.ai_receipt.history_reference.aiReceiptHistoryReference import AiReceiptHistoryReference

def lambda_handler(event, context):
    return AiReceiptHistoryReference().lambda_handler(event, context)
