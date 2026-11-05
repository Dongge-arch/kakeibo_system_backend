# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""Belc自動連携の金額と商品別分類を検証する。"""

import json
import sys
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

# ローカルテストではLambda層の旧psycopg2互換モジュールを読み込まない。
try:
    import psycopg2  # noqa: F401
except ModuleNotFoundError:
    sys.modules["psycopg2"] = SimpleNamespace(IntegrityError=RuntimeError)

from src.batch.kakeibo.auto_input_targets.auto_input_belc.autoInput_Belc import AutoInput_Belc
from src.api.kakeibo.receipt.taxPrice import enrich_detail_prices


class ItemCategoryAnalyzer:
    """2026-09-18 Codex: 商品別AI分類を再現するテスト用アナライザー。"""

    def analyze_json_with_prompt(self, text, prompt, label):
        payload = json.loads(text)
        assert label == "Belc商品一覧"
        assert [item["itemName"] for item in payload["items"]] == ["コチュジャン", "おいももなか"]
        assert "個別の商品名を優先" in prompt
        return {
            "statusCode": 200,
            "body": {
                "mappings": [
                    {"detailIndex": 0, "category1": "食費", "category2": "調味料"},
                    {"detailIndex": 1, "category1": "食費", "category2": "菓子・デザート"},
                ]
            },
        }


def create_service():
    """DB初期化を行わず、解析ロジックだけをテストする。"""
    return AutoInput_Belc.__new__(AutoInput_Belc)


def test_belc_tax_excluded_price_builds_both_price_types():
    """Belcの税抜単価を税込金額と混同しない。"""
    html = """
    <div class="mod-confirm__itemlist-block">
      <span class="mod-confirm__itemlist-detail-name">*07 コチュジャン</span>
      <span>259円</span>
      <span class="mod-confirm__itemlist-detail-number">1点</span>
    </div>
    """

    details = create_service().extract_receipt_details(BeautifulSoup(html, "html.parser"))

    assert len(details) == 1
    detail = details[0]
    assert detail["taxRate"] == pytest.approx(0.08)
    assert detail["unitPrice"] == 259
    assert detail["taxExcludedUnitPrice"] == 259
    assert detail["taxExcludedTotalPrice"] == 259
    assert detail["taxIncludedUnitPrice"] == 280
    assert detail["taxIncludedTotalPrice"] == 280
    assert detail["totalPrice"] == 280
    assert enrich_detail_prices(detail, "0") == {
        "unitPrice": 280,
        "totalPrice": 280,
        "taxExcludedUnitPrice": 259,
        "taxExcludedTotalPrice": 259,
        "taxIncludedUnitPrice": 280,
        "taxIncludedTotalPrice": 280,
    }


def test_belc_ai_mapping_classifies_each_item_in_same_department():
    """Belc部門が同じでも、商品名ごとに異なる分類を反映する。"""
    receipt_info = {
        "taxFlag": 0,
        "receiptDetails": [
            {
                "itemName": "コチュジャン",
                "category1": "その他",
                "category2": "その他",
                "taxRate": 0.08,
                "unitPrice": 259,
                "totalPrice": 280,
                "belcCategoryCode": "07",
                "belcCategoryName": "一般食品",
            },
            {
                "itemName": "おいももなか",
                "category1": "その他",
                "category2": "その他",
                "taxRate": 0.08,
                "unitPrice": 99,
                "totalPrice": 106.92,
                "belcCategoryCode": "07",
                "belcCategoryName": "一般食品",
            },
        ],
    }
    categories = {
        "category1": [{"CATEGORY1_NAME": "食費"}],
        "category2": [
            {"CATEGORY1_NAME": "食費", "CATEGORY2_NAME": "調味料", "TAX_RATE": 0.08},
            {"CATEGORY1_NAME": "食費", "CATEGORY2_NAME": "菓子・デザート", "TAX_RATE": 0.08},
        ],
    }

    mapped = create_service().map_receipt_categories(
        receipt_info=receipt_info,
        categories=categories,
        analyzer=ItemCategoryAnalyzer(),
    )

    assert mapped["receiptDetailCount"] == 2
    assert mapped["receiptDetails"][0]["category2"] == "調味料"
    assert mapped["receiptDetails"][1]["category2"] == "菓子・デザート"
    assert mapped["receiptDetails"][0]["taxRate"] == pytest.approx(0.08)
    assert mapped["receiptDetails"][0]["totalPrice"] == 280


def test_belc_ai_mapping_rejects_missing_item():
    """AIが商品を漏らした場合は誤登録せず再実行対象に残す。"""
    receipt_info = {
        "receiptDetails": [
            {"itemName": "商品A", "taxRate": 0.08},
            {"itemName": "商品B", "taxRate": 0.08},
        ]
    }
    categories = {
        "category2": [
            {"CATEGORY1_NAME": "食費", "CATEGORY2_NAME": "その他", "TAX_RATE": 0.08},
        ]
    }

    with pytest.raises(RuntimeError, match="count mismatch"):
        create_service().apply_belc_item_category_mappings(
            receipt_info,
            [{"detailIndex": 0, "category1": "食費", "category2": "その他"}],
            categories,
        )
