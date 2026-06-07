# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""モバイルSuica会員メニューの利用履歴を取り込むバッチ。"""

import requests

from src.common.base.base_batch import BaseBatch


class AutoCsvInput_Suica(BaseBatch):
    """保存済み会員情報を使用してSuica公式サイトとの連携を開始する。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}

    def validate_headers(self, request_dict):
        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        user_id = (request_dict.get("headers") or {}).get("x-kakeibo-user-id")
        config = self.get_config(user_id)
        if not config:
            raise RuntimeError("Suicaの自動連携設定が見つかりません。")
        if not int(self.value(config, "ENABLED", "enabled") or 0):
            return {"statusCode": 200, "body": {"ok": True, "skipped": True, "message": "Suica自動連携は無効です。"}}

        account_id = self.value(config, "LOGIN_ID_1", "login_id_1")
        password = self.value(config, "LOGIN_PW_1", "login_pw_1")
        login_url = self.value(config, "PAGE_URL_2", "page_url_2")
        if not account_id or not password or not login_url:
            raise RuntimeError("Suicaの会員情報が不足しています。")

        # 公式サイト側の追加認証や画面変更を検知できるよう、到達確認を先に行う。
        response = requests.get(login_url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/148 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.8",
        })
        response.raise_for_status()
        return {
            "statusCode": 200,
            "body": {
                "ok": True,
                "status": "LOGIN_PAGE_CONFIRMED",
                "message": "Suica会員メニューへの到達を確認しました。利用履歴取得処理を開始できます。",
            },
        }

    def get_config(self, user_id):
        rows = self.database.select(
            """
            SELECT * FROM auto_csv_input_info
            WHERE CRE_USER_ID = %(USER_ID)s
              AND DEL_FLAG = 0
              AND (CONNECTION_TYPE = 'SUICA' OR UPPER(SUP_NAME) = 'SUICA')
            ORDER BY id DESC
            LIMIT 1
            """,
            {"USER_ID": user_id},
        )
        return rows[0] if rows else {}

    @staticmethod
    def value(row, *keys):
        lower = {str(key).lower(): value for key, value in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None
