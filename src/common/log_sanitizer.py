# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""ログ出力前に認証情報や大容量データをマスクする共通処理。"""

import re


SENSITIVE_KEYS = {
    "authorization",
    "x-api-key",
    "api_key",
    "apikey",
    "password",
    "login_pw_1",
    "captcha",
    "cookie",
    "set-cookie",
    "token",
    "jwt",
}

LARGE_DATA_KEYS = {
    "captchaimage",
    "imagebase64",
    "supplierimage",
    "aiimage",
    "image",
}

NORMALIZED_SENSITIVE_KEYS = {
    item.replace("_", "").replace("-", "").lower()
    for item in SENSITIVE_KEYS
}


def sanitize_log_value(value, key: str = ""):
    """元データを変更せず、ログ用の安全な値へ再帰的に変換する。"""
    normalized_key = str(key or "").replace("_", "").replace("-", "").lower()

    if normalized_key in NORMALIZED_SENSITIVE_KEYS:
        return "[REDACTED]"

    if normalized_key in LARGE_DATA_KEYS:
        text = str(value or "")
        return f"[OMITTED length={len(text)}]"

    if isinstance(value, dict):
        return {
            item_key: sanitize_log_value(item_value, item_key)
            for item_key, item_value in value.items()
        }

    if isinstance(value, list):
        return [sanitize_log_value(item) for item in value]

    # 2026-06-28 Codex: キー名で拾えないBearer/JWTや長いdata URLもログ直前でマスクする。
    if isinstance(value, str):
        if value.lower().startswith("bearer "):
            return "[REDACTED]"
        if re.fullmatch(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value):
            return "[REDACTED]"
        if value.startswith("data:image/") and len(value) > 200:
            return f"[OMITTED length={len(value)}]"
        if len(value) > 4000:
            return f"[OMITTED length={len(value)}]"

    return value
