# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""税抜価格と税込価格を保存するための共通処理。"""


def to_number(value, default=0):
    if value in (None, ""):
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default


def to_display_number(value):
    number = to_number(value)
    if number == int(number):
        return int(number)
    return round(number, 2)


def normalize_tax_rate(value, default=0.1):
    rate = to_number(value, default)
    if rate > 1:
        return rate / 100
    if rate < 0:
        return default
    return rate


def round_price(value):
    # 2026-07-03 Codex: Support two decimal places and negative prices instead of integer-only yen rounding.
    return round(to_number(value), 2)


def detail_tax_included_total(detail: dict, tax_flag):
    """2026-06-28 Codex: 明細合計の比較では常に税込金額へ寄せる。"""
    if not isinstance(detail, dict):
        return 0
    # 2026-06-29 Codex: totalPriceを税込の表示金額として優先し、誤った税区分で作られた旧内訳に引きずられないようにする。
    if detail.get("totalPrice") not in (None, ""):
        return to_number(detail.get("totalPrice"))
    if detail.get("taxIncludedTotalPrice") not in (None, ""):
        return to_number(detail.get("taxIncludedTotalPrice"))
    return to_number(enrich_detail_prices(detail, tax_flag).get("taxIncludedTotalPrice"))


def receipt_details_tax_included_total(details: list, tax_flag):
    """2026-06-28 Codex: ヘッダー合計と明細合計の整合性確認用に税込合計を集計する。"""
    return sum(detail_tax_included_total(detail, tax_flag) for detail in details or [])


def enrich_detail_prices(detail: dict, tax_flag) -> dict:
    """
    明細の既存価格を優先し、不足している税抜・税込価格だけを補完する。

    args:
        - detail (dict): レシート明細。
        - tax_flag: 元のレシートが税抜か税込かを示す値。
    returns:
        - dict: 表示用、税抜保存用、税込保存用の価格。
    """
    if not isinstance(detail, dict):
        detail = {}

    tax_rate = normalize_tax_rate(detail.get("taxRate"))
    tax_multiplier = 1 + tax_rate
    is_tax_excluded = str(tax_flag if tax_flag is not None else "0") == "0"

    display_unit = to_number(detail.get("unitPrice"))
    display_total = to_number(detail.get("totalPrice"))
    quantity = to_number(detail.get("quantity"), 1) or 1
    discount = to_number(detail.get("discount"))
    # 2026-07-03 Codex: Keep negative prices/refunds valid and preserve decimal quantities.
    base_total = display_unit * quantity - discount

    if is_tax_excluded:
        tax_excluded_unit = display_unit
        tax_included_unit = round_price(display_unit * tax_multiplier)
        # 2026-06-28 Codex: 既存の税込合計がある場合はそれを最優先し、ヘッダー/明細合計のブレを抑える。
        tax_included_total = (
            display_total
            or to_number(detail.get("taxIncludedTotalPrice"))
            or round_price(base_total * tax_multiplier)
        )
        tax_excluded_total = (
            to_number(detail.get("taxExcludedTotalPrice"))
            or (
            round_price(tax_included_total / tax_multiplier)
            if tax_included_total
            else base_total
            )
        )
    else:
        tax_included_unit = display_unit
        tax_included_total = to_number(detail.get("taxIncludedTotalPrice")) or display_total or base_total
        tax_excluded_unit = round_price(display_unit / tax_multiplier) if display_unit else 0
        tax_excluded_total = (
            to_number(detail.get("taxExcludedTotalPrice"))
            or (
            round_price(tax_included_total / tax_multiplier)
            if tax_included_total
            else 0
            )
        )

    # 画面表示と家計簿集計では税込価格に統一する。
    display_unit = to_number(tax_included_unit)
    display_total = to_number(tax_included_total)

    return {
        "unitPrice": to_display_number(display_unit),
        "totalPrice": to_display_number(display_total),
        "taxExcludedUnitPrice": to_display_number(tax_excluded_unit),
        "taxExcludedTotalPrice": to_display_number(tax_excluded_total),
        "taxIncludedUnitPrice": to_display_number(tax_included_unit),
        "taxIncludedTotalPrice": to_display_number(tax_included_total),
    }
