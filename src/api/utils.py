# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json
import re
from datetime import datetime

from src.common.auth_context import get_current_request_headers


def now_ymd_hms():
    """既存DB形式に合わせた現在日付・時刻を返す。"""
    return datetime.now().strftime("%Y%m%d"), datetime.now().strftime("%H%M%S")


def parse_json_object(raw):
    """設定テーブルなどに保存したJSON文字列を辞書として読み込む。"""
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def normalize_invoice_number(value):
    """インボイス登録番号を T + 13桁 の形式へ正規化する。"""
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    if raw.upper().startswith("T"):
        raw = raw[1:]

    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 13 or digits != raw:
        return None

    return f"T{digits}"


def normalize_receipt_number(value):
    """レシート番号を T/A + 13桁 の形式へ正規化する。"""
    if value is None:
        return None

    raw = str(value).strip().upper()
    if not raw:
        return None

    prefix = raw[0] if raw[0] in ("T", "A") else "T"
    digits = raw[1:] if raw[0] in ("T", "A") else raw
    if not digits.isdigit() or len(digits) != 13:
        return None
    return f"{prefix}{digits}"


def normalize_tax_flag(value):
    """画面から渡された税区分を既存DBの 0 / 1 形式へ変換する。"""
    return 1 if str(value).strip() in ("1", "true", "True", "on") else 0


def json_response(status_code, body):
    """BaseRestApi と FastAPI で共通利用するレスポンス形式を作る。"""
    return {"statusCode": status_code, "body": body}


CAMEL_KEY_ALIASES = {
    "CAT1": "category1",
    "CAT2": "category2",
    "CRE_DT": "createdDate",
    "CRE_TM": "createdTime",
    "CRE_USER_ID": "createdUserId",
    "INV_REG_NUM": "invoiceRegistrationNumber",
    "RET_DT": "receiptDate",
    "RET_DET_CNT": "receiptDetailCount",
    "RET_ID": "receiptId",
    "RET_TM": "receiptTime",
    "SAL_CAT": "salaryCategoryName",
    "SUP_NAME": "supplierName",
    "TOA_PRICE": "totalPrice",
    "TO_PRE": "totalPrice",
    "TO_TAX_EXCLUDED": "taxExcludedTotalPrice",
    "TO_TAX_INCLUDED": "taxIncludedTotalPrice",
    "UPD_DT": "updatedDate",
    "UPD_TM": "updatedTime",
    "UPD_USER_ID": "updatedUserId",
    "UT_PRE": "unitPrice",
    "UT_TAX_EXCLUDED": "taxExcludedUnitPrice",
    "UT_TAX_INCLUDED": "taxIncludedUnitPrice",
}


def to_camel_key(key):
    """DB列名やsnake_caseをAPI用camelCaseへ変換する。"""
    if not isinstance(key, str):
        return key
    if key in CAMEL_KEY_ALIASES:
        return CAMEL_KEY_ALIASES[key]
    upper_key = key.upper()
    if upper_key in CAMEL_KEY_ALIASES:
        return CAMEL_KEY_ALIASES[upper_key]
    if "_" not in key and not key.isupper():
        return key[:1].lower() + key[1:]
    parts = [part for part in re.split(r"[_\s]+", key.lower()) if part]
    if not parts:
        return key
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def to_camel_payload(value):
    """APIレスポンス本文を再帰的にcamelCaseキーへ寄せる。"""
    if isinstance(value, list):
        return [to_camel_payload(item) for item in value]
    if isinstance(value, dict):
        converted = {}
        for key, item in value.items():
            converted[to_camel_key(key)] = to_camel_payload(item)
        return converted
    return value


def normalize_api_body(body):
    """BaseRestApi の body がJSON文字列の場合はPythonオブジェクトへ戻し、キーをcamelCaseへ寄せる。"""
    if isinstance(body, str):
        try:
            return to_camel_payload(json.loads(body))
        except Exception:
            return {}
    return to_camel_payload(body)


def call_api(api, request_body, default_status_code=200):
    """FastAPIルートからBaseRestApi実装を呼び出す薄いアダプタ。"""
    body = request_body.get("body", {})
    if "headers" in request_body:
        headers = request_body["headers"]
    else:
        headers = get_current_request_headers()

    result = api.call(request_body=request_body or {}, body=body, headers=headers)
    return {
        "statusCode": result.get("statusCode", default_status_code),
        "body": normalize_api_body(result.get("body")),
    }


def service_body(payload):
    """外部サービス風レスポンスの body を、必要に応じてJSONとして展開する。"""
    if not isinstance(payload, dict):
        return payload

    body = payload.get("body", payload)
    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            return body
    return body


def int_token(value):
    """AI利用量などの数値項目を安全に整数へ変換する。"""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
