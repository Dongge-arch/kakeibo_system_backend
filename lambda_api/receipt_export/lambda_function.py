import base64
import json

from src.api.receipt.receipt_export.receiptExport import ReceiptExportService


def lambda_handler(event, context):
    """Generate an Excel or PDF export in one stateless Lambda request."""
    try:
        body = event.get("body") if isinstance(event, dict) else {}
        if isinstance(body, str):
            body = json.loads(body or "{}")
        result = ReceiptExportService().prepare_file(body or {})
        return {
            "statusCode": result["statusCode"],
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps(result["body"], ensure_ascii=False),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps({"errorMessage": str(exc)}, ensure_ascii=False),
        }

