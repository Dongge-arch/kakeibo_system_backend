# Lambda handlers

Each API has its own folder and `lambda_function.py`.

The handler should stay thin:

```python
from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration


def lambda_handler(event, context):
    return NewReceiptRegistration().lambda_handler(event, context)
```

When an API class still uses an internal `action` switch, the corresponding
handler only adds that `action` or API Gateway path/query parameters to
`event["body"]`, then calls the class directly.
