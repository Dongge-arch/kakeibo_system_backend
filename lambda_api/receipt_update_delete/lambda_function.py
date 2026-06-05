from src.api.receipt.receipt_update_delete.receiptUpdateDelete import ReceiptUpdateDelete

def lambda_handler(event, context):
    return ReceiptUpdateDelete().lambda_handler(event, context)
