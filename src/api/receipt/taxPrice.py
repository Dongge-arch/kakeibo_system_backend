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
    return number


def normalize_tax_rate(value, default=0.1):
    rate = to_number(value, default)
    if rate > 1:
        return rate / 100
    if rate < 0:
        return default
    return rate


def round_price(value):
    return int(to_number(value) + 0.5)


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
    base_total = max(0, display_unit * quantity - discount)

    tax_excluded_unit = detail.get("taxExcludedUnitPrice")
    tax_excluded_total = detail.get("taxExcludedTotalPrice")
    tax_included_unit = detail.get("taxIncludedUnitPrice")
    tax_included_total = detail.get("taxIncludedTotalPrice")

    if tax_excluded_unit in (None, ""):
        if is_tax_excluded:
            tax_excluded_unit = display_unit
        else:
            tax_excluded_unit = round_price(display_unit / tax_multiplier) if display_unit else 0

    if tax_excluded_total in (None, ""):
        if is_tax_excluded:
            # 税抜入力では、画面表示用の税込合計ではなく入力値から税抜合計を復元する。
            tax_excluded_total = base_total if base_total else (
                round_price(display_total / tax_multiplier) if display_total else 0
            )
        else:
            tax_excluded_total = round_price(display_total / tax_multiplier) if display_total else 0

    if tax_included_unit in (None, ""):
        if is_tax_excluded:
            tax_included_unit = round_price(to_number(tax_excluded_unit) * tax_multiplier)
        else:
            tax_included_unit = display_unit

    if tax_included_total in (None, ""):
        if is_tax_excluded:
            tax_included_total = round_price(to_number(tax_excluded_total) * tax_multiplier)
        else:
            tax_included_total = display_total

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
