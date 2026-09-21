from src.api.kakeibo.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration

def lambda_handler(event, context):
    return NewReceiptRegistration().lambda_handler(event, context)
