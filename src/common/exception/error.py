# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import json
from src.common.functions.response import error_response
from src.common.exception.constants import ERROR_DICT


class Error(Exception):
    """アプリ共通のエラーレスポンスを保持する例外クラス。"""

    def __init__(self,
                 status_code: int,
                 error_code: str,
                 replacement: dict = None,
                 message: str = None):
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = message or ERROR_DICT[self.error_code]['errorMessage']

        if replacement:
            for k, v in replacement.items():
                self.error_message = self.error_message.replace(k, v)

    def __call__(self) -> dict:
        return self.response()

    def __str__(self) -> str:
        return json.dumps(self.response(), ensure_ascii=False)

    def response(self) -> dict:
        """例外内容をAPIレスポンス形式へ変換する。"""
        return error_response(status_code=self.status_code,
                              error_code=self.error_code,
                              error_message=self.error_message)
