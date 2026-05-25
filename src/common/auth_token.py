# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional


def jwt_secret() -> str:
    """
    JWT署名に利用するシークレットを環境変数から取得する。

    Returns:
        str: JWT署名用シークレット。
    """
    return os.environ.get("KAKEIBO_JWT_SECRET") or "home-kakeibo-local-dev-secret"


def b64url_encode(raw: bytes) -> str:
    """
    JWT用のBase64URL文字列へ変換する。

    Args:
        raw (bytes): エンコード対象のバイト列。

    Returns:
        str: paddingを除去したBase64URL文字列。
    """
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    """
    Base64URL文字列をbytesへ戻す。

    Args:
        value (str): Base64URL文字列。

    Returns:
        bytes: デコードしたバイト列。
    """
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def issue_token(user: dict, ttl_seconds: Optional[int] = None) -> str:
    """
    ユーザー情報から署名付きJWTを発行する。

    Args:
        user (dict): userId、username、email、nicknameを含むユーザー情報。
        ttl_seconds (Optional[int]): 有効期限秒数。Noneの場合は期限を設定しない。

    Returns:
        str: 署名付きJWT。
    """
    # iatはトークンの発行時刻。ttl_seconds未指定ならログアウトまで有効にする。
    now = int(time.time())
    # HS256固定のシンプルなJWTヘッダー。
    header = {"alg": "HS256", "typ": "JWT"}
    # ReactとDBスコープ付与で必要な最小限のユーザー情報だけを入れる。
    payload = {
        "sub": user.get("userId"),
        "username": user.get("username"),
        "email": user.get("email") or user.get("username"),
        "nickname": user.get("nickname"),
        "iat": now,
    }
    if ttl_seconds is not None:
        payload["exp"] = now + ttl_seconds
    encoded_header = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    # 署名対象はJWT標準どおり header.payload。
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = hmac.new(
        jwt_secret().encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{b64url_encode(signature)}"


def verify_token(token: str) -> dict:
    """
    JWTを検証し、有効な場合だけユーザー情報を返す。

    Args:
        token (str): 検証対象のJWT。

    Returns:
        dict: 有効な場合はユーザー情報、無効な場合は空辞書。
    """
    if not token:
        return {}

    try:
        # JWTを3パートへ分解し、署名の改ざん有無を確認する。
        encoded_header, encoded_payload, encoded_signature = token.split(".", 2)
        signing_input = f"{encoded_header}.{encoded_payload}"
        expected = hmac.new(
            jwt_secret().encode("utf-8"),
            signing_input.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual = b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected, actual):
            return {}

        payload = json.loads(b64url_decode(encoded_payload).decode("utf-8"))
        # 旧トークンなどexpがある場合だけ期限切れ判定を行う。
        if payload.get("exp") is not None and int(payload.get("exp") or 0) < int(time.time()):
            return {}

        return {
            "userId": payload.get("sub"),
            "username": payload.get("username"),
            "email": payload.get("email") or payload.get("username"),
            "nickname": payload.get("nickname") or payload.get("username"),
        }
    except Exception:
        return {}
