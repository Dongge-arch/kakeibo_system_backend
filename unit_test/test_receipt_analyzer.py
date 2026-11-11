from src.api.kakeibo.receipt.ai_receipt.receiptAnalyzer import (
    APP_CONFIG,
    GeminiReceiptAnalyzer,
    build_receipt_prompt,
    is_non_item_detail,
    loads_ai_json,
)


class FakeGeminiResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        self.ok = 200 <= status_code < 300

    def json(self):
        return self.body


def categories():
    return {
        "category1": [
            {"CATEGORY1_NAME": "日用品"},
            {"CATEGORY1_NAME": "交通"},
            {"CATEGORY1_NAME": "食費"},
            {"CATEGORY1_NAME": "その他"},
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
            {
                "CATEGORY1_NAME": "その他",
                "CATEGORY2_NAME": "未分類",
                "TAX_RATE": 0.1,
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


def test_unknown_item_is_kept_in_other_unclassified():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "supplierName": "不明店舗",
                "totalPrice": 100,
                "receiptDetails": [{
                    "itemName": "判別不能商品",
                    "category1": "存在しない分類",
                    "category2": "存在しない小分類",
                    "quantity": 1,
                    "unitPrice": 100,
                    "totalPrice": 100,
                }],
            }
        },
        categories(),
    )

    detail = result["receiptInfo"]["receiptDetails"][0]
    assert (detail["category1"], detail["category2"]) == ("その他", "未分類")


def test_prompt_allows_other_unclassified_when_category_is_unknown():
    prompt = build_receipt_prompt(categories())

    assert "合理的に判断できない場合は「その他 > 未分類」" in prompt
    assert "「未分類」にせず" not in prompt


def test_prompt_prioritizes_amount_after_currency_symbol_and_requires_quantity_evidence():
    prompt = build_receipt_prompt(categories())

    assert "通貨記号の直後に印字された最初の金額" in prompt
    assert "quantityEvidence" in prompt


def test_quantity_without_printed_evidence_is_reset_to_one():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "totalPrice": 208,
                "receiptDetails": [{
                    "itemName": "じゃがりこチーズL",
                    "category1": "食費",
                    "category2": "米・パン・麺",
                    "quantity": 6,
                    "unitPrice": 34.67,
                    "totalPrice": 208,
                }],
            }
        },
        categories(),
    )

    detail = result["receiptInfo"]["receiptDetails"][0]
    assert detail["quantity"] == 1
    assert detail["unitPrice"] == 208


def test_quantity_with_printed_evidence_is_preserved():
    analyzer = GeminiReceiptAnalyzer(api_key="test")
    result = analyzer.normalize_ai_receipt(
        {
            "receiptInfo": {
                "totalPrice": 396,
                "receiptDetails": [{
                    "itemName": "缶ビール",
                    "category1": "その他",
                    "category2": "未分類",
                    "quantity": 2,
                    "quantityEvidence": "2点 × ￥198",
                    "unitPrice": 198,
                    "totalPrice": 396,
                }],
            }
        },
        categories(),
    )

    assert result["receiptInfo"]["receiptDetails"][0]["quantity"] == 2


def test_gemini_api_key_can_be_loaded_from_gemini_api_key_config(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setitem(APP_CONFIG, "ai_receipt", {"gemini_api_key": "from-config"})

    analyzer = GeminiReceiptAnalyzer()

    assert analyzer.api_key == "from-config"


def test_gemini_bad_request_returns_safe_detail_without_retry(monkeypatch):
    analyzer = GeminiReceiptAnalyzer(api_key="secret-key")
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return FakeGeminiResponse(400, {"error": {"message": "Invalid image data."}})

    monkeypatch.setattr("requests.post", fake_post)

    try:
        analyzer.generate_content([{"text": "test"}])
        assert False, "Gemini 400 must raise an error."
    except RuntimeError as error:
        assert str(error) == "Gemini API error (400): Invalid image data."
        assert "secret-key" not in str(error)

    assert len(calls) == 1


def test_loads_ai_json_repairs_trailing_commas():
    parsed = loads_ai_json('{"mappings":[{"category1":"food","category2":"rice",},],}')

    assert parsed == {"mappings": [{"category1": "food", "category2": "rice"}]}


def test_loads_ai_json_extracts_json_from_wrapped_text():
    parsed = loads_ai_json('Here is the JSON:\n```json\n{"ok": true,}\n```\nThanks')

    assert parsed == {"ok": True}
