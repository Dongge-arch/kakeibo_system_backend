from src.api.receipt.taxPrice import enrich_detail_prices


def test_tax_excluded_values_are_rebuilt_from_visible_fields():
    detail = {
        "quantity": 1,
        "unitPrice": 100,
        "totalPrice": 110,
        "taxRate": 0.1,
        "taxExcludedUnitPrice": 110,
        "taxExcludedTotalPrice": 110,
        "taxIncludedUnitPrice": 121,
        "taxIncludedTotalPrice": 121,
    }

    assert enrich_detail_prices(detail, "0") == {
        "unitPrice": 110,
        "totalPrice": 110,
        "taxExcludedUnitPrice": 100,
        "taxExcludedTotalPrice": 100,
        "taxIncludedUnitPrice": 110,
        "taxIncludedTotalPrice": 110,
    }


def test_tax_included_values_are_rebuilt_from_visible_fields():
    detail = {
        "quantity": 1,
        "unitPrice": 110,
        "totalPrice": 110,
        "taxRate": 0.1,
    }

    assert enrich_detail_prices(detail, "1") == {
        "unitPrice": 110,
        "totalPrice": 110,
        "taxExcludedUnitPrice": 100,
        "taxExcludedTotalPrice": 100,
        "taxIncludedUnitPrice": 110,
        "taxIncludedTotalPrice": 110,
    }
