from src.api.kakeibo.receipt.receipt_reference.receiptReference import ReceiptReference

def lambda_handler(event, context):
    return ReceiptReference().lambda_handler(event, context)
