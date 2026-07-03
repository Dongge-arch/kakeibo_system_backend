# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""Receipt validation before insert/update."""

from src.api.receipt.taxPrice import receipt_details_tax_included_total, to_number
from src.common.exception import Error


def validate_receipt_for_save(receipt_info: dict) -> None:
    """2026-06-28 Codex: Prevent empty AI/manual receipt rows from being saved."""
    if not isinstance(receipt_info, dict) or not receipt_info:
        raise Error(status_code=400, error_code="1000062", message="receiptInfo is required.")

    receipt_details = receipt_info.get("receiptDetails") or []
    if not isinstance(receipt_details, list) or not receipt_details:
        raise Error(status_code=400, error_code="1000062", message="At least one receipt detail is required.")

    for index, detail in enumerate(receipt_details, start=1):
        validate_receipt_detail_for_save(detail, index)

    validate_receipt_total_for_save(receipt_info, receipt_details)


def validate_receipt_detail_for_save(detail: dict, index: int) -> None:
    """Validate item/category/quantity while allowing negative and decimal prices."""
    if not isinstance(detail, dict):
        raise Error(status_code=400, error_code="1000062", message=f"Detail {index} format is invalid.")

    if not str(detail.get("itemName") or "").strip():
        raise Error(status_code=400, error_code="1000062", message=f"Detail {index} itemName is required.")
    if not str(detail.get("category1") or "").strip():
        raise Error(status_code=400, error_code="1000062", message=f"Detail {index} category1 is required.")
    if not str(detail.get("category2") or "").strip():
        raise Error(status_code=400, error_code="1000062", message=f"Detail {index} category2 is required.")
    if to_number(detail.get("quantity"), 1) <= 0:
        raise Error(status_code=400, error_code="1000062", message=f"Detail {index} quantity must be greater than 0.")

    # 2026-07-03 Codex: Prices may be negative and may use two decimal places for refunds/adjustments.
    to_number(detail.get("unitPrice"))
    to_number(detail.get("totalPrice"))


def validate_receipt_total_for_save(receipt_info: dict, receipt_details: list) -> None:
    """Validate numeric shape without rejecting receipt/detail total differences."""
    # 2026-07-03 Codex: Do not block save when printed receipt total differs from calculated item total.
    to_number(receipt_info.get("totalPrice"))
    receipt_details_tax_included_total(receipt_details, receipt_info.get("taxFlag"))
