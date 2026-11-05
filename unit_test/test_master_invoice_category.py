from unittest.mock import MagicMock

from src.api.kakeibo.master.invoice.invoiceReference import InvoiceReference


def create_api():
    api = InvoiceReference.__new__(InvoiceReference)
    api.database = MagicMock()
    api.logo_storage = MagicMock()
    api.logo_storage.url_for.return_value = "https://example.test/store.png"
    return api


def test_invoice_response_contains_supplier_category():
    api = create_api()

    result = api.invoice_response({
        "INV_REG_NUM": "T1234567890123",
        "SUP_NAME": "セブン-イレブン",
        "SUP_CATEGORY": "コンビニ",
        "TAX_FLAG": 1,
    })

    assert result["supplierCategory"] == "コンビニ"


def test_invoice_response_defaults_empty_category_to_other():
    api = create_api()

    result = api.invoice_response({
        "INV_REG_NUM": "T1234567890123",
        "SUP_NAME": "店舗",
        "SUP_CATEGORY": None,
        "TAX_FLAG": 0,
    })

    assert result["supplierCategory"] == "その他"


def test_update_invoice_saves_supplier_category():
    api = create_api()
    api.database.read_sql.side_effect = lambda name, location=None: name
    api.database.select.return_value = [{
        "INV_REG_NUM": "T1234567890123",
        "SUP_NAME": "店舗",
        "SUP_CATEGORY": "スーパー",
        "TAX_FLAG": 1,
    }]

    api.update_invoice({
        "invoiceRegistrationNumber": "T1234567890123",
        "supplierName": "店舗",
        "supplierCategory": "スーパー",
        "taxFlag": "1",
    }, "user-1")

    params = api.database.execute.call_args.args[1]
    assert params["SUP_CATEGORY"] == "スーパー"
