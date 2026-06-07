# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""出費自動連携先と会員アカウントを管理するAPI。"""

from src.api.utils import json_response, now_ymd_hms
from src.common.base import BaseRestApi


SUPPORTED_PLACES = (
    {
        "connectionType": "BELC",
        "supplierName": "ベルク",
        "invoiceRegistrationNumber": "T8030001085963",
    },
    {
        "connectionType": "SUICA",
        "supplierName": "Suica",
        "invoiceRegistrationNumber": "SUICA",
    },
)


class AutoLinkageApi(BaseRestApi):
    """自動連携設定の参照、更新、ログイン確認、論理削除を行う。"""

    _schema_ready = False

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.ensure_schema()

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        action = body.get("action")
        if action == "list":
            return json_response(200, self.list_places(user_id))
        if action == "get":
            return json_response(200, self.get_place(body, user_id))
        if action == "update":
            return self.update_place(body, user_id)
        if action == "login":
            return self.login_place(body, user_id)
        if action == "delete":
            return self.delete_place(body, user_id)
        return json_response(400, {"errorMessage": "自動連携の操作が不正です。"})

    def ensure_schema(self):
        if self.__class__._schema_ready:
            return
        for statement in (
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS ENABLED INTEGER DEFAULT 0",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS CONNECTION_TYPE TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS LAST_LOGIN_STATUS TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS LAST_LOGIN_DT TEXT",
            "ALTER TABLE auto_csv_input_info ADD COLUMN IF NOT EXISTS LAST_LOGIN_TM TEXT",
        ):
            self.database.execute(statement)
        self.__class__._schema_ready = True

    def list_places(self, user_id):
        result = []
        for place in SUPPORTED_PLACES:
            row = self.find_row(place["connectionType"], user_id)
            result.append(self.public_row(place, row))
        return result

    def get_place(self, body, user_id):
        place = self.require_place(body)
        return self.public_row(place, self.find_row(place["connectionType"], user_id), include_account=True)

    def update_place(self, body, user_id):
        place = self.require_place(body)
        account_id = str(body.get("accountId") or "").strip()
        password = str(body.get("password") or "")
        enabled = 1 if body.get("enabled") else 0
        current = self.find_row(place["connectionType"], user_id)
        if current and not password:
            password = self.value(current, "LOGIN_PW_1", "login_pw_1") or ""
        if enabled and (not account_id or not password):
            return json_response(400, {"errorMessage": "連携を有効にするには会員IDとパスワードが必要です。"})

        ymd, hms = now_ymd_hms()
        if current:
            self.database.update(
                """
                UPDATE auto_csv_input_info
                SET UPD_PROG = 'AutoLinkageApi',
                    SUP_NAME = %(SUP_NAME)s,
                    INV_REG_NUM = %(INV_REG_NUM)s,
                    LOGIN_ID_1 = %(LOGIN_ID_1)s,
                    LOGIN_PW_1 = %(LOGIN_PW_1)s,
                    ENABLED = %(ENABLED)s,
                    CONNECTION_TYPE = %(CONNECTION_TYPE)s,
                    UPD_DT = %(UPD_DT)s,
                    UPD_TM = %(UPD_TM)s,
                    UPD_USER_ID = %(USER_ID)s
                WHERE id = %(id)s
                  AND CRE_USER_ID = %(USER_ID)s
                  AND DEL_FLAG = 0
                """,
                {
                    "id": self.value(current, "id", "ID"),
                    "SUP_NAME": place["supplierName"],
                    "INV_REG_NUM": place["invoiceRegistrationNumber"],
                    "LOGIN_ID_1": account_id,
                    "LOGIN_PW_1": password,
                    "ENABLED": enabled,
                    "CONNECTION_TYPE": place["connectionType"],
                    "UPD_DT": ymd,
                    "UPD_TM": hms,
                    "USER_ID": user_id,
                },
            )
        else:
            urls = self.default_urls(place["connectionType"])
            self.database.insert(
                """
                INSERT INTO auto_csv_input_info (
                    CRE_PROG, UPD_PROG, INV_REG_NUM, SUP_NAME,
                    PAGE_NAME_1, PAGE_URL_1, PAGE_NAME_2, PAGE_URL_2,
                    LOGIN_ID_1, LOGIN_PW_1, ENABLED, CONNECTION_TYPE,
                    CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
                ) VALUES (
                    'AutoLinkageApi', 'AutoLinkageApi', %(INV_REG_NUM)s, %(SUP_NAME)s,
                    %(PAGE_NAME_1)s, %(PAGE_URL_1)s, %(PAGE_NAME_2)s, %(PAGE_URL_2)s,
                    %(LOGIN_ID_1)s, %(LOGIN_PW_1)s, %(ENABLED)s, %(CONNECTION_TYPE)s,
                    %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, %(USER_ID)s, %(USER_ID)s, 0
                )
                """,
                {
                    "INV_REG_NUM": place["invoiceRegistrationNumber"],
                    "SUP_NAME": place["supplierName"],
                    "PAGE_NAME_1": urls["historyName"],
                    "PAGE_URL_1": urls["historyUrl"],
                    "PAGE_NAME_2": urls["loginName"],
                    "PAGE_URL_2": urls["loginUrl"],
                    "LOGIN_ID_1": account_id,
                    "LOGIN_PW_1": password,
                    "ENABLED": enabled,
                    "CONNECTION_TYPE": place["connectionType"],
                    "CRE_DT": ymd,
                    "CRE_TM": hms,
                    "UPD_DT": ymd,
                    "UPD_TM": hms,
                    "USER_ID": user_id,
                },
            )
        return json_response(200, {"ok": True, "message": "自動連携設定を保存しました。"})

    def login_place(self, body, user_id):
        place = self.require_place(body)
        row = self.find_row(place["connectionType"], user_id)
        account_id = str(body.get("accountId") or self.value(row, "LOGIN_ID_1", "login_id_1") or "").strip()
        password = str(body.get("password") or self.value(row, "LOGIN_PW_1", "login_pw_1") or "")
        if not account_id or not password:
            return json_response(400, {"errorMessage": "会員IDとパスワードを入力してください。"})

        # 外部サイトの追加認証を考慮し、ここでは保存済み認証情報の利用可否を確認する。
        self.update_login_status(row, user_id, "READY")
        return json_response(200, {
            "ok": True,
            "status": "READY",
            "message": "認証情報を確認しました。次回の自動連携実行時に公式サイトへログインします。",
        })

    def delete_place(self, body, user_id):
        place = self.require_place(body)
        row = self.find_row(place["connectionType"], user_id)
        if row:
            ymd, hms = now_ymd_hms()
            self.database.update(
                """
                UPDATE auto_csv_input_info
                SET DEL_FLAG = 1, ENABLED = 0, UPD_PROG = 'AutoLinkageApi',
                    UPD_DT = %(UPD_DT)s, UPD_TM = %(UPD_TM)s, UPD_USER_ID = %(USER_ID)s
                WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
                """,
                {"id": self.value(row, "id", "ID"), "UPD_DT": ymd, "UPD_TM": hms, "USER_ID": user_id},
            )
        return json_response(200, {"ok": True, "message": "会員アカウントを削除しました。"})

    def find_row(self, connection_type, user_id):
        rows = self.database.select(
            """
            SELECT * FROM auto_csv_input_info
            WHERE CRE_USER_ID = %(USER_ID)s
              AND DEL_FLAG = 0
              AND (CONNECTION_TYPE = %(CONNECTION_TYPE)s OR UPPER(SUP_NAME) = %(CONNECTION_TYPE)s)
            ORDER BY id DESC
            LIMIT 1
            """,
            {"USER_ID": user_id, "CONNECTION_TYPE": connection_type},
        )
        return rows[0] if rows else {}

    def update_login_status(self, row, user_id, status):
        if not row:
            return
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE auto_csv_input_info
            SET LAST_LOGIN_STATUS = %(STATUS)s, LAST_LOGIN_DT = %(DT)s, LAST_LOGIN_TM = %(TM)s
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {"STATUS": status, "DT": ymd, "TM": hms, "id": self.value(row, "id", "ID"), "USER_ID": user_id},
        )

    def public_row(self, place, row, include_account=False):
        result = {
            **place,
            "configured": bool(row),
            "enabled": bool(int(self.value(row, "ENABLED", "enabled") or 0)),
            "lastLoginStatus": self.value(row, "LAST_LOGIN_STATUS", "last_login_status") or "",
            "lastLoginDate": self.value(row, "LAST_LOGIN_DT", "last_login_dt") or "",
            "lastLoginTime": self.value(row, "LAST_LOGIN_TM", "last_login_tm") or "",
        }
        if include_account:
            result["accountId"] = self.value(row, "LOGIN_ID_1", "login_id_1") or ""
            result["passwordRegistered"] = bool(self.value(row, "LOGIN_PW_1", "login_pw_1"))
        return result

    def require_place(self, body):
        connection_type = str(body.get("connectionType") or "").upper()
        for place in SUPPORTED_PLACES:
            if place["connectionType"] == connection_type:
                return place
        raise ValueError("対応していない自動連携先です。")

    def default_urls(self, connection_type):
        if connection_type == "SUICA":
            return {
                "loginName": "会員メニューサイト",
                "loginUrl": "https://www.mobilesuica.com/",
                "historyName": "SF（電子マネー）利用履歴",
                "historyUrl": "https://www.mobilesuica.com/",
            }
        return {
            "loginName": "ベルク会員ログイン",
            "loginUrl": "https://cust-bf.belc.jp/mypage/Login",
            "historyName": "お買い物履歴",
            "historyUrl": "https://cust-bf.belc.jp/mypage/PurchaseHistory",
        }

    @staticmethod
    def value(row, *keys):
        lower = {str(key).lower(): value for key, value in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None
