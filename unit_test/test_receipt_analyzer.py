from src.api.receipt.ai_receipt.receiptAnalyzer import (
    GeminiReceiptAnalyzer,
    is_non_item_detail,
)


def categories():
    return {
        "category1": [
            {"CATEGORY1_NAME": "日用品"},
            {"CATEGORY1_NAME": "交通"},
            {"CATEGORY1_NAME": "食費"},
        ],
        "category2": [
            {
                "CATEGORY1_NAME": "日用品",
                "CATEGORY2_NAME": "小型雑貨",
                "TAX_RATE": 0.1,
            },
            {
                "CATEGORY1_NAME": "交通",
                "CATEGORY2_NAME": "ガソリン",
                "TAX_RATE": 0.1,
            },
            {
                "CATEGORY1_NAME": "食費",
                "CATEGORY2_NAME": "外食",
                "TAX_RATE": 0.1,
            },
            {
                "CATEGORY1_NAME": "食費",
                "CATEGORY2_NAME": "米・パン・麺",
                "TAX_RATE": 0.08,
            },
        ],
    }


def test_master_tax_rate_overrides_ai_tax_rate_and_prices_are_rebuilt():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "taxFlag": "1",
                "totalPrice": 2215,
                "receiptDetails": [
                    {
                        "itemName": "CW晴雨兼用スリム折傘",
                        "category1": "日用品",
                        "category2": "小型雑貨",
                        "taxRate": 0.08,
                        "quantity": 1,
                        "unitPrice": 2215,
                        "totalPrice": 2215,
                        "taxExcludedUnitPrice": 0,
                    }
                ],
            }
        },
        categories(),
    )

    detail = result["receiptInfo"]["receiptDetails"][0]
    assert detail["taxRate"] == 0.1
    assert detail["taxExcludedUnitPrice"] == 2014
    assert detail["taxIncludedUnitPrice"] == 2215


def test_tax_and_summary_rows_are_not_saved_as_items():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "taxFlag": "1",
                "totalPrice": 2000,
                "receiptDetails": [
                    {
                        "itemName": "レギュラーガソリン",
                        "category1": "交通",
                        "category2": "ガソリン",
                        "quantity": 1,
                        "unitPrice": 2000,
                        "totalPrice": 2000,
                    },
                    {
                        "itemName": "ガソリン税",
                        "category1": "交通",
                        "category2": "ガソリン",
                        "quantity": 1,
                        "unitPrice": 538,
                        "totalPrice": 538,
                    },
                    {"itemName": "合計", "totalPrice": 2000},
                ],
            }
        },
        categories(),
    )

    details = result["receiptInfo"]["receiptDetails"]
    assert [detail["itemName"] for detail in details] == ["レギュラーガソリン"]
    assert result["receiptInfo"]["receiptDetailCount"] == 1


def test_non_item_name_detection_accepts_amount_suffixes():
    assert is_non_item_detail("消費税等 182円")
    assert is_non_item_detail("10.0%対象額：2,000")
    assert not is_non_item_detail("消毒用エタノール")


def test_restaurant_context_overrides_ramen_product_category():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "supplierName": "日高屋 本厚木一番街店",
                "taxFlag": "1",
                "totalPrice": 750,
                "receiptDetails": [
                    {
                        "itemName": "中華そば",
                        "category1": "食費",
                        "category2": "米・パン・麺",
                        "quantity": 1,
                        "unitPrice": 750,
                        "totalPrice": 750,
                    }
                ],
            }
        },
        categories(),
    )

    detail = result["receiptInfo"]["receiptDetails"][0]
    assert (detail["category1"], detail["category2"]) == ("食費", "外食")
    assert detail["taxRate"] == 0.1


def test_supermarket_ramen_keeps_product_category():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "supplierName": "ベルク 厚木店",
                "taxFlag": "1",
                "totalPrice": 200,
                "receiptDetails": [
                    {
                        "itemName": "カップラーメン",
                        "category1": "食費",
                        "category2": "米・パン・麺",
                        "quantity": 1,
                        "unitPrice": 200,
                        "totalPrice": 200,
                    }
                ],
            }
        },
        categories(),
    )

    detail = result["receiptInfo"]["receiptDetails"][0]
    assert (detail["category1"], detail["category2"]) == ("食費", "米・パン・麺")
