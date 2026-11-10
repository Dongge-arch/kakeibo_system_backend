# -*- coding: utf-8 -*-

from tools.reclassify_receipt_history import (
    build_change,
    immutable_metrics_equal,
    transition_summary,
)


VALID_CATEGORIES = {
    ("食費", "野菜"),
    ("食費", "その他食品"),
    ("日用品", "生活雑貨"),
    ("その他", "未分類"),
}


def test_build_change_moves_legacy_category_without_changing_price_fields():
    detail = {
        "id": 10,
        "ret_id": "receipt-1",
        "item_name": "北海道産たまねぎ",
        "cat1": "食費",
        "cat2": "野菜・果物",
        "tax_rate": 0.08,
        "to_tax_included": 108,
    }

    change = build_change(detail, VALID_CATEGORIES)

    assert change == {
        "id": 10,
        "ret_id": "receipt-1",
        "item_name": "北海道産たまねぎ",
        "old_cat1": "食費",
        "old_cat2": "野菜・果物",
        "old_tax_rate": 0.08,
        "new_cat1": "食費",
        "new_cat2": "野菜",
        "tax_rate": 0.08,
    }
    assert "to_tax_included" not in change


def test_build_change_uses_unclassified_when_target_is_not_in_master():
    detail = {
        "id": 11,
        "ret_id": "receipt-2",
        "item_name": "北海道産たまねぎ",
        "cat1": "食費",
        "cat2": "野菜・果物",
        "tax_rate": 0.08,
    }

    change = build_change(detail, {("その他", "未分類")})

    assert change["new_cat1"] == "その他"
    assert change["new_cat2"] == "未分類"
    assert change["tax_rate"] == 0.08


def test_build_change_keeps_current_category_and_historical_tax_rate():
    detail = {
        "id": 12,
        "ret_id": "receipt-3",
        "item_name": "テリヤキチキンとたまご",
        "cat1": "食費",
        "cat2": "惣菜・弁当",
        "tax_rate": 0.10,
    }

    assert build_change(detail, VALID_CATEGORIES | {("食費", "惣菜・弁当")}) is None


def test_transition_summary_orders_by_count():
    changes = [
        {"old_cat1": "食費", "old_cat2": "野菜・果物", "new_cat1": "食費", "new_cat2": "野菜"},
        {"old_cat1": "食費", "old_cat2": "野菜・果物", "new_cat1": "食費", "new_cat2": "野菜"},
        {"old_cat1": "日用品", "old_cat2": "小型雑貨", "new_cat1": "日用品", "new_cat2": "生活雑貨"},
    ]

    assert list(transition_summary(changes).values()) == [2, 1]


def test_immutable_metrics_allow_only_floating_point_rounding_noise():
    before = {"detail_count": "10", **{column: "100.0" for column in (
        "qty", "ut_pre", "to_pre", "ut_tax_excluded", "to_tax_excluded",
        "ut_tax_included", "to_tax_included",
    )}}
    after = {**before, "to_tax_included": "100.000000001"}

    assert immutable_metrics_equal(before, after)
    assert not immutable_metrics_equal(before, {**after, "detail_count": "11"})
    assert not immutable_metrics_equal(before, {**after, "to_tax_included": "100.01"})
