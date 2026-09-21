"""AIレシート履歴確定Lambda。"""

from src.api.kakeibo.receipt.ai_receipt.history_update.aiReceiptHistoryFinal import AiReceiptHistoryFinal

def lambda_handler(event, context):
    return AiReceiptHistoryFinal().lambda_handler(event, context)
