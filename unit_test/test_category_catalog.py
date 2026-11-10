# -*- coding: utf-8 -*-

from src.common.category_catalog import (
    DEFAULT_EXPENSE_CATEGORIES,
    category_for_new_detail,
    classify_supplier_category,
    refine_item_category,
    suggest_item_category,
)


def test_catalog_contains_expanded_household_categories():
    assert "育児・子ども" in DEFAULT_EXPENSE_CATEGORIES
    assert "自動車" in DEFAULT_EXPENSE_CATEGORIES
    assert "趣味" in DEFAULT_EXPENSE_CATEGORIES
    assert ("魚介類", 0.08) in DEFAULT_EXPENSE_CATEGORIES["食費"]


def test_unclassified_baby_product_is_classified():
    assert suggest_item_category("パンパース肌いち 60枚") == (
        "育児・子ども",
        "おむつ・おしりふき",
        0.10,
    )


def test_existing_cafe_category_is_not_overwritten_by_drink_keyword():
    result = refine_item_category("アイスコーヒー", "食費", "カフェ", 0.10)
    assert result == ("食費", "カフェ", 0.10)


def test_legacy_car_cost_moves_out_of_public_transport():
    result = refine_item_category("ETC高速道路料金", "交通", "高速料金", 0.10)
    assert result == ("自動車", "高速道路", 0.10)


def test_new_unclassified_detail_uses_product_rule():
    detail = category_for_new_detail({
        "itemName": "レギュラーガソリン",
        "category1": "その他",
        "category2": "未分類",
        "taxRate": 0.10,
    })
    assert detail["category1"] == "自動車"
    assert detail["category2"] == "ガソリン"


def test_supplier_name_has_priority_over_mixed_products():
    category = classify_supplier_category(
        "ウェルシア薬局株式会社",
        [("食費", "飲料", 10), ("日用品", "衛生用品", 5)],
    )
    assert category == "ドラッグストア"


def test_unknown_supplier_uses_dominant_registered_category():
    category = classify_supplier_category(
        "名称だけでは判断できない店舗",
        [("自動車", "駐車場", 8), ("食費", "飲料", 1)],
    )
    assert category == "駐車場"


def test_nishimatsuya_is_baby_store():
    assert classify_supplier_category("西松屋") == "ベビー・子ども"


def test_flavour_words_do_not_turn_snacks_into_dairy_products():
    assert refine_item_category("じゃがりこチーズ", "食費", "米・パン・麺", 0.08) == (
        "食費",
        "菓子",
        0.08,
    )


def test_known_legacy_products_are_moved_to_specific_categories():
    assert suggest_item_category("スパ王喫茶店のナポリタン大盛り")[:2] == ("食費", "麺類")
    assert suggest_item_category("Ｂｅ．Ｌ．Ｔローラー")[:2] == ("日用品", "洗剤・掃除用品")
    assert suggest_item_category("ロボタイム イチゴミルクパック")[:2] == ("趣味", "模型・工作")


def test_explicit_miscellaneous_history_is_not_left_unclassified():
    assert suggest_item_category("雑費") == ("その他", "雑費・不明", 0.10)


def test_registered_supplier_variants_use_the_expected_place_category():
    assert classify_supplier_category("株式会社ヤマダデンキ") == "家電・PC"
    assert classify_supplier_category("株式会社マツモトキヨシ") == "ドラッグストア"
    assert classify_supplier_category("HANDS") == "総合小売・サービス"
    assert classify_supplier_category("場所登録不要") == "登録不要"


def test_legacy_merged_food_category_uses_item_name_first():
    assert refine_item_category("北海道産たまねぎ", "食費", "野菜・果物", 0.08) == (
        "食費",
        "野菜",
        0.08,
    )
    assert refine_item_category("バニラモナカジャンボ", "食費", "菓子・デザート", 0.08) == (
        "食費",
        "アイス・デザート",
        0.08,
    )


def test_legacy_merged_category_uses_safe_fallback_when_item_is_ambiguous():
    assert refine_item_category("青果", "食費", "野菜・果物", 0.08) == (
        "食費",
        "その他食品",
        0.08,
    )
    assert refine_item_category("判別できない雑貨", "日用品", "小型雑貨", 0.10) == (
        "日用品",
        "生活雑貨",
        0.10,
    )


def test_legacy_phone_category_separates_subscription_and_device_accessory():
    assert refine_item_category("YouTube プレミアム会員", "通信", "携帯電話", 0.10)[:2] == (
        "通信",
        "サブスク",
    )
    assert refine_item_category("Type C Micro USB ケーブル", "通信", "携帯電話", 0.10)[:2] == (
        "通信",
        "端末・周辺機器",
    )


def test_partial_word_matches_do_not_misclassify_historical_items():
    assert refine_item_category("ワイドパンツ", "日用品", "小型雑貨", 0.10)[:2] == (
        "日用品",
        "生活雑貨",
    )
    assert refine_item_category("液体ムヒちいかわ", "日用品", "小型雑貨", 0.10)[:2] == (
        "医療",
        "薬・処方箋",
    )
    assert refine_item_category("アートプライス ぷるぷる", "食費", "菓子・デザート", 0.08)[:2] == (
        "食費",
        "菓子",
    )


def test_known_snack_names_override_ingredient_words():
    assert refine_item_category("やおきん でかにんじん", "食費", "菓子・デザート", 0.08)[:2] == (
        "食費",
        "菓子",
    )
    assert refine_item_category("ガリガリ君 梨", "食費", "菓子・デザート", 0.08)[:2] == (
        "食費",
        "アイス・デザート",
    )
