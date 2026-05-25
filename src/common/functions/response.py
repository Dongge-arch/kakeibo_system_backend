# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""Helpers for the local API response envelope."""


def response(status_code: int, body: dict) -> dict:
    """Create the response envelope shared by app.py and API classes."""
    return {
        "statusCode": status_code,
        "body": body
    }


def error_response(status_code: int, error_code: str,
                   error_message: str) -> dict:
    """エラー情報を標準レスポンス形式へ包む。"""
    return response(status_code=status_code,
                    body=error_response_body(error_code=error_code,
                                             error_message=error_message))


def error_response_body(error_code: str, error_message: str) -> dict:
    """エラーコードとメッセージをレスポンス本文として作成する。"""
    return {"errorCode": error_code, "errorMessage": error_message}
