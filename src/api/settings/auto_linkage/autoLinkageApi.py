# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""出費自動連携先と会員アカウントを管理するAPI。"""

from src.api.utils import now_ymd_hms
from src.common.base import BaseRestApi
from src.common.exception.error import Error
from src.common.functions.response import response
from src.batch.auto_input_targets.auto_input_belc.autoInput_Belc import AutoInput_Belc
from src.batch.auto_input_targets.auto_input_suica.autoInput_Suica import (
    AutoInput_Suica,
    AutoInput_TransportIc,
    TRANSPORT_IC_CONNECTIONS,
    TRANSPORT_IC_SERVICE_CONFIG,
)
from src.batch.auto_input_targets.auto_input_etc.autoInput_Etc import AutoInput_Etc
from src.batch.auto_input_targets.auto_input_amazon.autoInput_Amazon import AutoInput_Amazon


SUPPORTED_PLACES = (
    {
        "connectionType": "BELC",
        "supplierName": "ベルク",
        "invoiceRegistrationNumber": "T8030001085963",
        "group": "shopping",
        "displayName": "ベルク",
        "historyName": "ベルク購入履歴",
        "supportStatus": "supported",
        "automationMode": "automatic",
    },
    {
        "connectionType": "SUICA",
        "supplierName": "東日本旅客鉄道株式会社",
        "invoiceRegistrationNumber": "T9011001029597",
        "group": "transport",
        "displayName": "Mobile Suica",
        "historyName": "Mobile Suica利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "ETC",
        "supplierName": "東日本高速道路株式会社",
        "invoiceRegistrationNumber": "T9010001095716",
        "group": "other",
        "displayName": "ETC利用照会サービス",
        "historyName": "ETC利用明細",
        "supportStatus": "supported",
        "automationMode": "automatic",
    },
    {
        "connectionType": "PASMO",
        "supplierName": "株式会社パスモ",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "PASMO",
        "historyName": "PASMO利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "ICOCA",
        "supplierName": "西日本旅客鉄道株式会社",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "ICOCA",
        "historyName": "ICOCA利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "PITAPA",
        "supplierName": "株式会社スルッとKANSAI",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "PiTaPa",
        "historyName": "PiTaPa利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "TOICA",
        "supplierName": "東海旅客鉄道株式会社",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "TOICA",
        "historyName": "TOICA利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "MANACA",
        "supplierName": "株式会社エムアイシー",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "manaca",
        "historyName": "manaca利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "SUGOCA",
        "supplierName": "九州旅客鉄道株式会社",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "SUGOCA",
        "historyName": "SUGOCA利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "NIMOCA",
        "supplierName": "株式会社ニモカ",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "nimoca",
        "historyName": "nimoca利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "HAYAKAKEN",
        "supplierName": "福岡市交通局",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "はやかけん",
        "historyName": "はやかけん利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "KITACA",
        "supplierName": "北海道旅客鉄道株式会社",
        "invoiceRegistrationNumber": "",
        "group": "transport",
        "displayName": "Kitaca",
        "historyName": "Kitaca利用履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "AMAZON",
        "supplierName": "Amazon",
        "invoiceRegistrationNumber": "",
        "group": "shopping",
        "displayName": "Amazon",
        "historyName": "Amazon注文履歴",
        "supportStatus": "supported",
        "automationMode": "manual",
    },
    {
        "connectionType": "RAKUTEN",
        "supplierName": "楽天グループ株式会社",
        "invoiceRegistrationNumber": "",
        "group": "shopping",
        "displayName": "楽天市場",
        "historyName": "楽天購入履歴",
        "supportStatus": "planned",
        "automationMode": "planned",
    },
    {
        "connectionType": "NITORI",
        "supplierName": "株式会社ニトリ",
        "invoiceRegistrationNumber": "",
        "group": "shopping",
        "displayName": "Nitori",
        "historyName": "Nitori購入履歴",
        "supportStatus": "planned",
        "automationMode": "planned",
    },
    {
        "connectionType": "YAHOO_SHOPPING",
        "supplierName": "LINEヤフー株式会社",
        "invoiceRegistrationNumber": "",
        "group": "shopping",
        "displayName": "Yahoo!ショッピング",
        "historyName": "Yahoo!ショッピング購入履歴",
        "supportStatus": "planned",
        "automationMode": "planned",
    },
    {
        "connectionType": "YODOBASHI",
        "supplierName": "株式会社ヨドバシカメラ",
        "invoiceRegistrationNumber": "",
        "group": "shopping",
        "displayName": "ヨドバシ.com",
        "historyName": "ヨドバシ.com購入履歴",
        "supportStatus": "planned",
        "automationMode": "planned",
    },
)

SUPPORTED_RUN_CONNECTIONS = {"BELC", "ETC", "AMAZON"} | TRANSPORT_IC_CONNECTIONS


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
        
        # 保存済みログイン情報の入力有無を確認する。実サイトへの認証は取り込み時に行う。
        if action == "login":
            result = self.login_place(body, user_id)
            return response(200, result)
        
        # 手動実行
        if action == "run":
            return self.run_place(body, user_id, request_dict)
        
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
        # 新規ユーザーでも画面に連携先を表示できるよう、未作成の初期レコードを補完する。
        self.ensure_default_places(user_id)
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
        self.ensure_default_place(place, user_id)
        return self.public_row(place, self.find_row(place["connectionType"], user_id), include_account=True)

    def ensure_default_places(self, user_id):
        """
        対応している連携先の初期レコードをユーザー単位で作成する。
        """
        for place in SUPPORTED_PLACES:
            self.ensure_default_place(place, user_id)

    def ensure_default_place(self, place, user_id):
        """
        指定した連携先が未作成の場合、ログイン情報が空の初期レコードを作成する。
        """
        if self.find_row(place["connectionType"], user_id):
            return

        ymd, hms = now_ymd_hms()
        urls = self.default_urls(place["connectionType"])
        params = {
            "INV_REG_NUM": place["invoiceRegistrationNumber"],
            "SUP_NAME": place["supplierName"],
            "PAGE_NAME_1": urls["historyName"],
            "PAGE_URL_1": urls["historyUrl"],
            "PAGE_NAME_2": urls["loginName"],
            "PAGE_URL_2": urls["loginUrl"],
            "PAGE_NAME_3": urls.get("loginPostName"),
            "PAGE_URL_3": urls.get("loginPostUrl"),
            "PAGE_NAME_4": urls.get("historySearchName"),
            "PAGE_URL_4": urls.get("historySearchUrl"),
            "LOGIN_ID_1": "",
            "LOGIN_PW_1": "",
            "ENABLED": 0,
            "CONNECTION_TYPE": place["connectionType"],
            "CRE_DT": ymd,
            "CRE_TM": hms,
            "UPD_DT": ymd,
            "UPD_TM": hms,
            "USER_ID": user_id,
        }
        self.database.insert(
            self.database.read_sql("INSERT_AUTO_INPUT_INFO", location=__file__),
            params,
        )

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
        if place.get("automationMode") != "automatic":
            # 自動実行に未対応の連携先は、保存時に有効化されないようにする。
            enabled = 0
        current = self.find_row(place["connectionType"], user_id)
        if current and not password:
            password = self.value(current, "LOGIN_PW_1", "login_pw_1") or ""
        if enabled and (not account_id or not password):
            raise Error(
                status_code=400,
                error_code="1000062",
                message="連携を有効にするには会員IDとパスワードが必要です。",
            )

        ymd, hms = now_ymd_hms()
        urls = self.default_urls(place["connectionType"])
        if current:
            where={
                    "id": self.value(current, "id", "ID"),
                    "SUP_NAME": place["supplierName"],
                    "INV_REG_NUM": place["invoiceRegistrationNumber"],
                    "PAGE_NAME_1": urls["historyName"],
                    "PAGE_URL_1": urls["historyUrl"],
                    "PAGE_NAME_2": urls["loginName"],
                    "PAGE_URL_2": urls["loginUrl"],
                    "PAGE_NAME_3": urls.get("loginPostName"),
                    "PAGE_URL_3": urls.get("loginPostUrl"),
                    "PAGE_NAME_4": urls.get("historySearchName"),
                    "PAGE_URL_4": urls.get("historySearchUrl"),
                    "LOGIN_ID_1": account_id,
                    "LOGIN_PW_1": password,
                    "ENABLED": enabled,
                    "CONNECTION_TYPE": place["connectionType"],
                    "UPD_DT": ymd,
                    "UPD_TM": hms,
                    "USER_ID": user_id,
                }
            
            self.database.update(self.database.read_sql("UPDATE_AUTO_INPUT_INFO", location=__file__), where)
        else:
            where={
                    "INV_REG_NUM": place["invoiceRegistrationNumber"],
                    "SUP_NAME": place["supplierName"],
                    "PAGE_NAME_1": urls["historyName"],
                    "PAGE_URL_1": urls["historyUrl"],
                    "PAGE_NAME_2": urls["loginName"],
                    "PAGE_URL_2": urls["loginUrl"],
                    "PAGE_NAME_3": urls.get("loginPostName"),
                    "PAGE_URL_3": urls.get("loginPostUrl"),
                    "PAGE_NAME_4": urls.get("historySearchName"),
                    "PAGE_URL_4": urls.get("historySearchUrl"),
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
            self.database.insert(self.database.read_sql("INSERT_AUTO_INPUT_INFO", location=__file__), where)
        return {"ok": True, "message": "自動連携設定を保存しました。"}

    def login_place(self, body, user_id):
        """
        会員IDとパスワードが利用可能な状態か確認する。実サイトへの認証は行わない。
        
        args:
            - body (dict): リクエストボディ。connectionType、accountId、password を含む必要がある。
            - user_id (str): ユーザーID
        returns:
            - dict: 処理結果。入力済みの場合は保存情報を取り込み時に検証する旨を返す。
        """
        place = self.require_place(body)
        row = self.find_row(place["connectionType"], user_id)
        account_id = str(body.get("accountId") or self.value(row, "LOGIN_ID_1", "login_id_1") or "").strip()
        password = str(body.get("password") or self.value(row, "LOGIN_PW_1", "login_pw_1") or "")
        if not account_id or not password:
            raise Error(
                status_code=400,
                error_code="1000062",
                message="会員IDとパスワードを入力してください。",
            )

        # 外部サイトの追加認証を考慮し、ここでは保存済み認証情報の利用可否を確認する。
        self.update_login_status(row, user_id, "SAVED_UNVERIFIED")
        return {
            "ok": True,
            "status": "SAVED_UNVERIFIED",
            "message": "ログイン情報を確認しました。実際のログイン確認は取り込み時に行います。",
        }

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
        if place["connectionType"] not in SUPPORTED_RUN_CONNECTIONS:
            return self.not_implemented_response(place)
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
            self.database.update(self.database.read_sql("DELETE_AUTO_INPUT_INFO", location=__file__),where)
        return {"ok": True, "message": "会員アカウントを削除しました。"}

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
        rows = self.database.select(self.database.read_sql("SELECT_AUTO_INPUT_INFO", location=__file__), where)
        return rows[0] if rows else {}

    def run_place(self, body, user_id, request_dict):
        """
        指定した連携先のデータ連携を手動実行する。
        args:
            - body (dict): リクエストボディ。connectionType を含む必要がある。
            - user_id (str): ユーザーID
            - request_dict (dict): リクエストの辞書。
        returns:
            - dict: 処理結果。
        """
        place = self.require_place(body)
        if place["connectionType"] not in SUPPORTED_RUN_CONNECTIONS:
            return self.not_implemented_response(place)
        row = self.find_row(place["connectionType"], user_id)
        if not row or not self.value(row, "LOGIN_ID_1", "login_id_1") or not self.value(row, "LOGIN_PW_1", "login_pw_1"):
            raise Error(
                status_code=400,
                error_code="1000062",
                message="先にログイン情報を保存してください。",
            )

        if place["connectionType"] == "BELC":
            result = AutoInput_Belc().call(
                body={"action": "run"},
                headers={"x-kakeibo-user-id": user_id},
            )
            body_result = result.get("body") or {}
            if int(result.get("statusCode", 500)) >= 400:
                return response(result.get("statusCode", 500), body_result)
            registered_count = int(body_result.get("registered") or 0)
            fetched_count = int(body_result.get("totalFetched") or 0)
            duplicate_count = int(body_result.get("alreadyRegistered") or 0)
            need_to_register_count = int(body_result.get("needToRegister") or 0)
            failed_count = int(body_result.get("failed") or 0)
            return response(200, {
                "ok": True,
                "status": "COMPLETED",
                "message": (
                    f"ベルクのデータ連携が完了しました。{registered_count}件を登録しました。"
                    + (f"{failed_count}件は登録できませんでした。" if failed_count else "")
                ),
                "fetchedCount": fetched_count,
                "insertedCount": need_to_register_count,
                "duplicateCount": duplicate_count,
                "registeredCount": registered_count,
                "failedCount": failed_count,
            })

        if place["connectionType"] == "ETC":
            result = AutoInput_Etc().call(
                body={"action": "run"},
                headers={"x-kakeibo-user-id": user_id},
            )
            body_result = result.get("body") or {}
            if int(result.get("statusCode", 500)) >= 400:
                return response(result.get("statusCode", 500), body_result)
            return response(200, {
                "ok": True,
                "status": "COMPLETED",
                "message": f"ETC利用明細を{int(body_result.get('registered') or 0)}件登録しました。",
                "fetchedCount": int(body_result.get("totalFetched") or 0),
                "insertedCount": int(body_result.get("needToRegister") or 0),
                "duplicateCount": int(body_result.get("alreadyRegistered") or 0),
                "registeredCount": int(body_result.get("registered") or 0),
                "failedCount": int(body_result.get("failed") or 0),
            })

        # Suicaは画像認証を含む既存の手動実行フローを使用する。
        # 2026-07-13 Codex: Suica以外の交通系ICカードもカード種別を渡して同じ手動フローで実行する。
        if place["connectionType"] == "AMAZON":
            # 2026-07-13 Codex: AmazonはSMS等の確認コードを利用者入力で受け取る手動フローとして実行する。
            result = AutoInput_Amazon().call(
                body={
                    "action": body.get("runAction") or "start",
                    "captcha": body.get("captcha") or "",
                    "verificationCode": body.get("verificationCode") or "",
                    "challengeId": body.get("challengeId") or "",
                },
                headers=request_dict.get("headers") or {},
            )
            return response(result.get("statusCode", 200), result.get("body") or {})

        auto_input = (
            AutoInput_Suica()
            if place["connectionType"] == "SUICA"
            else AutoInput_TransportIc(place["connectionType"])
        )
        result = auto_input.call(
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
            "STATUS": status,
            "LAST_LOGIN_DT": ymd,
            "LAST_LOGIN_TM": hms,
            "USER_ID": user_id,
        }
        self.database.update(self.database.read_sql("UPDATE_AUTO_INPUT_INFO_STATUS", location=__file__), where)

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
        account_id = self.value(row, "LOGIN_ID_1", "login_id_1") or ""
        password_registered = bool(self.value(row, "LOGIN_PW_1", "login_pw_1"))
        enabled = bool(int(self.value(row, "ENABLED", "enabled") or 0))
        if place.get("automationMode") != "automatic":
            # 手動専用・準備中サービスはレスポンス上も自動連携OFFとして扱う。
            enabled = False
        result = {
            **place,
            # 初期レコードだけでは設定済みにせず、IDとパスワードがそろった場合だけ利用可能とする。
            "configured": bool(account_id and password_registered),
            "enabled": enabled,
            "lastLoginStatus": self.value(row, "LAST_LOGIN_STATUS", "last_login_status") or "",
            "lastLoginDate": self.value(row, "LAST_LOGIN_DT", "last_login_dt") or "",
            "lastLoginTime": self.value(row, "LAST_LOGIN_TM", "last_login_tm") or "",
        }
        if include_account:
            result["accountId"] = account_id
            result["passwordRegistered"] = password_registered
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
        raise Error(status_code=400, error_code="1000062", message="対応していない自動連携先です。")

    def default_urls(self, connection_type):
        """
        連携先ごとの初期ページ名とURLを返す。

        args:
            - connection_type (str): 連携先の識別子。
        returns:
            - dict: 自動連携設定へ保存するページ情報。
        raises:
            - Error: 対応していない自動連携先の場合。
        """
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
                "loginPostName": "ベルク会員ログイン送信",
                "loginPostUrl": "https://cust-bf.belc.jp/mypage/Login?handler=Login",
                "historyName": "お買い物履歴",
                "historyUrl": "https://cust-bf.belc.jp/mypage/PurchaseHistory",
                "historySearchName": "お買い物履歴検索",
                "historySearchUrl": "https://cust-bf.belc.jp/mypage/PurchaseHistory?handler=Search",
            }
        if connection_type == "ETC":
            return {
                "loginName": "ETC利用照会サービス ログイン",
                "loginUrl": "https://www2.etc-meisai.jp/etc/R?funccode=1013000000&nextfunc=1013000000",
                "loginPostName": "ETC利用照会サービス ログイン送信",
                "loginPostUrl": "https://www2.etc-meisai.jp/etc/R?funccode=1013000000&nextfunc=1013000000",
                "historyName": "ETC利用明細",
                "historyUrl": "https://www2.etc-meisai.jp/etc/R?funccode=1013000000&nextfunc=1013000000",
            }
        if connection_type in TRANSPORT_IC_SERVICE_CONFIG:
            config = TRANSPORT_IC_SERVICE_CONFIG[connection_type]
            return {
                "loginName": f"{config['displayName']} ログイン",
                "loginUrl": config["loginUrl"],
                "historyName": f"{config['displayName']}利用履歴",
                "historyUrl": config["loginUrl"],
            }
        if connection_type == "AMAZON":
            return {
                "loginName": "Amazon ログイン",
                "loginUrl": "https://www.amazon.co.jp/",
                "historyName": "Amazon注文履歴",
                "historyUrl": "https://www.amazon.co.jp/gp/css/order-history?ref_=nav_orders_first",
            }
        place = next((item for item in SUPPORTED_PLACES if item["connectionType"] == connection_type), None)
        if place:
            # 追加候補サービスは、実装前でも設定レコードを保持できるよう汎用URLを入れておく。
            return {
                "loginName": f"{place.get('displayName') or connection_type} ログイン",
                "loginUrl": "",
                "historyName": place.get("historyName") or f"{connection_type}利用履歴",
                "historyUrl": "",
            }
        raise Error(status_code=400, error_code="1000062", message="対応していない自動連携先です。")

    def not_implemented_response(self, place):
        """
        連携先としては表示するが、履歴取得バッチが未実装のサービス用レスポンスを返す。
        """
        return response(501, {
            "ok": False,
            "status": "NOT_IMPLEMENTED",
            "message": f"{place.get('displayName') or place['connectionType']}の連携処理は未実装です。",
            "connectionType": place["connectionType"],
            "supportStatus": place.get("supportStatus") or "planned",
        })

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
