# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json
from datetime import datetime


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


def normalize_tax_flag(value):
    """画面から渡された税区分を既存DBの 0 / 1 形式へ変換する。"""
    return 1 if str(value).strip() in ("1", "true", "True", "on") else 0


def json_response(status_code, body):
    """BaseRestApi と FastAPI で共通利用するレスポンス形式を作る。"""
    return {"statusCode": status_code, "body": body}


def normalize_api_body(body):
    """BaseRestApi の body がJSON文字列の場合はPythonオブジェクトへ戻す。"""
    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            return {}
    return body


def call_api(api, body, default_status_code=200):
    """FastAPIルートからBaseRestApi実装を呼び出す薄いアダプタ。"""
    result = api.call(body=body or {}, headers={})
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
