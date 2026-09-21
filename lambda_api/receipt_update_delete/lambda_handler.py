from src.api.kakeibo.receipt.receipt_update_delete.receiptUpdateDelete import ReceiptUpdateDelete

def lambda_handler(event, context):
    return ReceiptUpdateDelete().lambda_handler(event, context)
