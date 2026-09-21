"""AI利用量参照Lambda。"""

from src.api.kakeibo.receipt.ai_receipt.usage_reference.aiReceiptUsageReference import AiReceiptUsageReference

def lambda_handler(event, context):
    return AiReceiptUsageReference().lambda_handler(event, context)
