# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""出費自動連携先と会員アカウントを管理するAPI。"""

from src.api.utils import now_ymd_hms
from src.common.base import BaseRestApi
from src.common.exception.error import Error
from src.common.functions.response import response
from src.batch.auto_csv_input_suica.autoCsvInput_Suica import AutoCsvInput_Suica


SUPPORTED_PLACES = (
    {
        "connectionType": "BELC",
        "supplierName": "ベルク",
        "invoiceRegistrationNumber": "T8030001085963",
    },
    {
        "connectionType": "SUICA",
        "supplierName": "東日本旅客鉄道株式会社",
        "invoiceRegistrationNumber": "T9011001029597",
    },
)


class AutoLinkageApi(BaseRestApi):
    """自動連携設定の参照、更新、ログイン確認、論理削除を行う。"""

    _schema_ready = False

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        action = body.get("action")
        # action に応じて処理を振り分ける。リクエストの妥当性は各処理内で確認する。
        # リスト取得
        if action == "list":
            result = self.list_places(user_id)
            return response(200, result)
        
        # 単一取得
        if action == "get":
            result = self.get_place(body, user_id)
            return response(200, result)
        
        # 更新（会員ID、パスワード、連携の有効/無効）
        if action == "update":
            result = self.update_place(body, user_id)
            return response(200, result)
        
        # ログイン確認（会員ID、パスワードの妥当性確認。外部サイトの追加認証は考慮しない）
        if action == "login":
            result = self.login_place(body, user_id)
            return response(200, result)
        
        # 手動実行
        if action == "run":
            result = self.run_place(body, user_id, request_dict)
            return response(200, result)
        
        # 自動連携削除
        if action == "delete":
            result = self.delete_place(body, user_id)
            return response(200, result)
        
        return response(400, {"errorMessage": "自動連携の操作が不正です。"})


    def list_places(self, user_id):
        """
        すべての連携先の設定情報を取得する。
        args:
            - user_id (str): ユーザーID
        returns:
            - list: 連携先の設定情報のリスト。
        """
        result = []
        for place in SUPPORTED_PLACES:
            row = self.find_row(place["connectionType"], user_id)
            result.append(self.public_row(place, row))
        return result

    def get_place(self, body, user_id):
        """
        指定した連携先の設定情報を取得する。
        args:
            - body (dict): リクエストボディ。connectionType を含む必要がある。
            - user_id (str): ユーザーID
        returns:
            - dict: 連携先の設定情報。
        """
        place = self.require_place(body)
        return self.public_row(place, self.find_row(place["connectionType"], user_id), include_account=True)

    def update_place(self, body, user_id):
        """
        連携先の設定を更新する。会員ID、パスワード、連携の有効/無効を更新できる。存在しない場合は新規作成する。
        args:
            - body (dict): リクエストボディ。connectionType、accountId、password、enabled を含む必要がある。
            - user_id (str): ユーザーID
        returns:
            - dict: 処理結果。成功時は {"ok": True, "message": "自動連携設定を保存しました。"} を返す。
        """
        place = self.require_place(body)
        account_id = str(body.get("accountId") or "").strip()
        password = str(body.get("password") or "")
        enabled = 1 if body.get("enabled") else 0
        current = self.find_row(place["connectionType"], user_id)
        if current and not password:
            password = self.value(current, "LOGIN_PW_1", "login_pw_1") or ""
        if enabled and (not account_id or not password):
            return response(400, {"errorMessage": "連携を有効にするには会員IDとパスワードが必要です。"})

        ymd, hms = now_ymd_hms()
        if current:
            where={
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
                }
            
            self.database.update(self.database.read_sql("UPDATE_AUTO_CSV_INPUT_INFO",location="__file__"), where)
        else:
            urls = self.default_urls(place["connectionType"])

            where={
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
                }
            self.database.insert(self.database.read_sql("INSERT_AUTO_CSV_INPUT_INFO",location="__file__"),where)
        return response(200, {"ok": True, "message": "自動連携設定を保存しました。"})

    def login_place(self, body, user_id):
        """
        会員IDとパスワードの妥当性を確認する。外部サイトの追加認証は考慮しない。
        
        args:
            - body (dict): リクエストボディ。connectionType、accountId、password を含む必要がある。
            - user_id (str): ユーザーID
        returns:
            - dict: 処理結果。成功時は {"ok": True, "status": "READY", "message": "認証情報を確認しました。次回の自動連携実行時に公式サイトへログインします。"} を返す。
        """
        place = self.require_place(body)
        row = self.find_row(place["connectionType"], user_id)
        account_id = str(body.get("accountId") or self.value(row, "LOGIN_ID_1", "login_id_1") or "").strip()
        password = str(body.get("password") or self.value(row, "LOGIN_PW_1", "login_pw_1") or "")
        if not account_id or not password:
            return response(400, {"errorMessage": "会員IDとパスワードを入力してください。"})

        # 外部サイトの追加認証を考慮し、ここでは保存済み認証情報の利用可否を確認する。
        self.update_login_status(row, user_id, "READY")
        return response(200, {
            "ok": True,
            "status": "READY",
            "message": "認証情報を確認しました。次回の自動連携実行時に公式サイトへログインします。",
        })

    def delete_place(self, body, user_id):
        """
        自動連携設定を削除する。
        args:
            - body (dict): リクエストボディ。connectionType を含む必要がある。
            - user_id (str): ユーザーID
        returns:
            - dict: 処理結果。成功時は {"ok": True, "message": "会員アカウントを削除しました。"} を返す。
        """
        place = self.require_place(body)
        row = self.find_row(place["connectionType"], user_id)
        if row:
            ymd, hms = now_ymd_hms()
            where={
                "id": self.value(row, "id", "ID"),
                "DEL_FLAG": 1,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
            }
            self.database.update(self.database.read_sql("DELETE_AUTO_CSV_INPUT_INFO",location="__file__"),where)
        return response(200, {"ok": True, "message": "会員アカウントを削除しました。"})

    def find_row(self, connection_type, user_id):
        """
        指定した連携先の設定情報を取得する。複数件存在する場合は最新の1件を返す。
        args:
            - connection_type (str): 連携先の識別子（例: "SUICA"、"BELC"）
            - user_id (str): ユーザーID
        returns:
         - dict: 設定情報の辞書。存在しない場合は空辞書。
        """
        where={
            "USER_ID": user_id,
            "CONNECTION_TYPE": connection_type,
        }
        rows = self.database.select(self.database.read_sql("SELECT_AUTO_CSV_INPUT_INFO",location="__file__"), where)
        return rows[0] if rows else {}

    def run_place(self, body, user_id, request_dict):
        """
        手動実行。現在は Suica のみ対応。
        args:
            - body (dict): リクエストボディ。connectionType を含む必要がある。
            - user_id (str): ユーザーID
            - request_dict (dict): リクエストの辞書。
        returns:
            - dict: 処理結果。
        """
        place = self.require_place(body)
        if place["connectionType"] != "SUICA":
            return response(400, {"errorMessage": "手動実行は現在 Suica のみ対応しています。"})

        # Suicaの自動連携を手動で実行する。
        result = AutoCsvInput_Suica().call(
            body={
                "action": body.get("runAction") or "start",
                "captcha": body.get("captcha") or "",
                "challengeId": body.get("challengeId") or "",
            },
            headers=request_dict.get("headers") or {},
        )
        return response(result.get("statusCode", 200), result.get("body") or {})

    def update_login_status(self, row, user_id, status):
        """
        ログイン状態を更新する。ログイン確認の結果や、実際の自動連携実行時のログイン成功/失敗に応じて呼び出す。
        args:
        - row (dict): 対象の設定情報の辞書。存在しない場合は空辞書。
        - user_id (str): ユーザーID
        - status (str): 更新するログイン状態

        """
        if not row:
            return
        ymd, hms = now_ymd_hms()
        where={
            "id": self.value(row, "id", "ID"), 
            "LAST_LOGIN_STATUS": status,
            "LAST_LOGIN_DT": ymd,
            "LAST_LOGIN_TM": hms,
            "USER_ID": user_id,
        }
        self.database.update(self.database.read_sql("UPDATE_LOGIN_STATUS_AUTO_CSV_INPUT_INFO",location="__file__"), where)

    def public_row(self, place, row, include_account=False):
        """
        設定情報の内部表現から、APIレスポンス用の表現に変換する。
        args:
            - place (dict): 対象の連携先の基本情報。connectionType、supplierName、invoiceRegistrationNumber を含む必要がある。
            - row (dict): 設定情報の辞書。存在しない場合は空辞書。
            - include_account (bool): 会員IDとパスワード登録の有無を含めるかどうか。デフォルトは False。
        returns:
            - dict: APIレスポンス用の設定情報の辞書。
        """
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
        """
        リクエストボディから connectionType を取得し、対応する連携先の基本情報を返す。存在しない場合は例外をスローする。
        args:
            - body (dict): リクエストボディ。connectionType を含む必要がある。
        returns:
            - dict: 対応する連携先の基本情報。
        raises:
            - Error: 対応していない自動連携先の場合。
        """
        connection_type = str(body.get("connectionType") or "").upper()
        for place in SUPPORTED_PLACES:
            if place["connectionType"] == connection_type:
                return place
        raise Error(400, {"errorMessage": "対応していない自動連携先です。"})

    def default_urls(self, connection_type):
        if connection_type == "SUICA":
            return {
                "loginName": "会員メニューサイト",
                "loginUrl": "https://www.mobilesuica.com/",
                "historyName": "SF（電子マネー）利用履歴",
                "historyUrl": "https://www.mobilesuica.com/",
            }
        if connection_type == "BELC":
            return {
                "loginName": "ベルク会員ログイン",
                "loginUrl": "https://cust-bf.belc.jp/mypage/Login",
                "historyName": "お買い物履歴",
                "historyUrl": "https://cust-bf.belc.jp/mypage/PurchaseHistory",
            }
        raise Error(400, {"errorMessage": "対応していない自動連携先です。"})

    @staticmethod
    def value(row, *keys):
        """
        辞書からキーを大文字小文字を区別せずに検索して値を返す。複数のキーを指定した場合は、最初に見つかったキーの値を返す。
        args:
            - row (dict): 検索対象の辞書。存在しない場合は空辞書。
            - keys (str): 検索するキー。複数指定可能。
        returns:
            - any: 見つかった値。見つからない場合は None。
        """
        lower = {str(key).lower(): value for key, value in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None
