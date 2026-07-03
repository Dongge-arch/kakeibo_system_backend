from src.api.receipt.ai_receipt.aiReceiptApi import AiReceiptApi
from src.api.receipt.receiptValidation import validate_receipt_for_save
from src.api.receipt.taxPrice import enrich_detail_prices, receipt_details_tax_included_total
from src.common.exception import Error
from src.common.log_sanitizer import sanitize_log_value


def test_validate_receipt_rejects_empty_item_detail():
    try:
        validate_receipt_for_save(
            {
                "taxFlag": "1",
                "totalPrice": 1,
                "receiptDetails": [
                    {
                        "itemName": "",
                        "category1": "",
                        "category2": "",
                        "quantity": 1,
                        "totalPrice": 0,
                    }
                ],
            }
        )
        assert False
    except Error as exc:
        assert exc.status_code == 400


def test_tax_detail_total_uses_tax_included_total_first():
    detail = {
        "unitPrice": 100,
        "totalPrice": 100,
        "taxRate": 0.1,
        "quantity": 1,
        "taxIncludedTotalPrice": 108,
    }

    prices = enrich_detail_prices(detail, "0")

    assert prices["totalPrice"] == 108
    assert receipt_details_tax_included_total([detail], "0") == 108


def test_ai_reconcile_single_detail_to_header_total():
    api = AiReceiptApi.__new__(AiReceiptApi)
    body = {
        "receiptInfo": {
            "taxFlag": "1",
            "totalPrice": 230,
            "receiptDetails": [
                {
                    "itemName": "drink",
                    "category1": "食費",
                    "category2": "飲料",
                    "taxRate": 0.08,
                    "quantity": 1,
                    "unitPrice": 248,
                    "totalPrice": 248,
                }
            ],
        }
    }

    result = api.reconcile_ai_receipt_totals(body)

    detail = result["receiptInfo"]["receiptDetails"][0]
    assert result["receiptInfo"]["totalPrice"] == 230
    assert detail["totalPrice"] == 230
    assert result["reviewWarnings"]


def test_sanitize_log_value_redacts_bearer_and_large_image_text():
    value = sanitize_log_value(
        {
            "authorization": "Bearer abc.def.ghi",
            "note": "data:image/png;base64," + "a" * 300,
        }
    )

    assert value["authorization"] == "[REDACTED]"
    assert value["note"].startswith("[OMITTED length=")
