# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""APIレスポンスを共通形式で作成する。"""

from typing import Any


def response(status_code: int, body: Any) -> dict:
    """
    APIとバッチで共通のレスポンス形式を作成する。

    Args:
        status_code: HTTPステータスコード。
        body: 辞書、配列または空のレスポンス本文。

    Returns:
        dict: statusCodeとbodyを持つレスポンス。
    """
    return {
        "statusCode": status_code,
        "body": body
    }


def error_response(status_code: int, error_code: str,
                   error_message: str) -> dict:
    """
    エラー情報を共通レスポンス形式へ包む。

    Args:
        status_code: HTTPステータスコード。
        error_code: アプリケーションエラーコード。
        error_message: 表示するエラーメッセージ。

    Returns:
        dict: エラー本文を含むレスポンス。
    """
    return response(status_code=status_code,
                    body=error_response_body(error_code=error_code,
                                             error_message=error_message))


def error_response_body(error_code: str, error_message: str) -> dict:
    """
    エラーコードとメッセージを本文として作成する。

    Args:
        error_code: アプリケーションエラーコード。
        error_message: 表示するエラーメッセージ。

    Returns:
        dict: エラー本文。
    """
    return {"errorCode": error_code, "errorMessage": error_message}
