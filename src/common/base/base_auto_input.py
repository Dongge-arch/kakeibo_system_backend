# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""自動入力バッチで利用する共通処理を提供する。"""

import hashlib
import json
import time
from datetime import datetime

import requests

from src.api.kakeibo.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.common.api_utils import now_ymd_hms
from src.common.auth_context import reset_current_user_id, set_current_user_id
from src.common.base.base_batch import BaseBatch
from src.common.exception import Error


class BaseAutoInput(BaseBatch):
    """外部サービス連携、自動入力管理、領収書登録の共通処理を提供する。"""

    RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, class_name, db_path=None):
        """
        自動入力バッチを初期化する。

        Args:
            class_name (str): ログへ出力するクラス名。
            db_path (Optional[str]): ローカル実行時に使用するDBパス。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=class_name, db_path=db_path or None)
        self._validate_headers_functions = {}
        self._validate_body_functions = {}

    def validate_headers(self, request_dict):
        """
        リクエストヘッダーの共通バリデーションを実行する。

        Args:
            request_dict (dict): リクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        """
        リクエスト本文の共通バリデーションを実行する。

        Args:
            request_dict (dict): リクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def new_session(self, user_agent=None):
        """
        外部サイト接続用HTTPセッションを作成する。

        Args:
            user_agent (Optional[str]): 接続先へ通知するUser-Agent。

        Returns:
            requests.Session: 共通ヘッダー設定済みセッション。
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja-JP,ja;q=0.9",
        })
        return session

    def request_external(
        self,
        session,
        method,
        url,
        operation_name,
        service_name,
        retry_count=3,
        backoff_seconds=1,
        **kwargs,
    ):
        """
        外部サイトへ接続し、一時エラーの場合のみ再試行する。

        Args:
            session (requests.Session): HTTPセッション。
            method (str): HTTPメソッド。
            url (str): 接続先URL。
            operation_name (str): ログへ出力する操作名。
            service_name (str): 連携サービス名。
            retry_count (int): 最大試行回数。
            backoff_seconds (int): 再試行間隔の基準秒数。

        Returns:
            requests.Response: 正常終了したHTTPレスポンス。
        """
        kwargs.setdefault("timeout", 30)
        last_error = None
        for attempt in range(1, retry_count + 1):
            try:
                result = session.request(method=method, url=url, **kwargs)
                if result.status_code not in self.RETRY_STATUS_CODES:
                    result.raise_for_status()
                    return result
                last_error = requests.HTTPError(
                    f"{result.status_code} Server Error for url: {url}",
                    response=result,
                )
            except requests.RequestException as error:
                last_error = error
                status_code = error.response.status_code if error.response is not None else None
                if status_code is not None and status_code not in self.RETRY_STATUS_CODES:
                    raise
            self.logger.warning(
                "%s通信失敗 operation=%s attempt=%s/%s error=%s",
                service_name,
                operation_name,
                attempt,
                retry_count,
                last_error,
            )
            if attempt < retry_count:
                time.sleep(backoff_seconds * attempt)
        raise Error(
            status_code=503,
            error_code="1000062",
            message=f"{service_name}のサービスが一時的に利用できません。時間をおいて再実行してください。",
        )

    def get_auto_input_config(self, user_id, connection_type):
        """
        ユーザーと連携種別に対応する自動入力設定を取得する。

        Args:
            user_id (str): ユーザーID。
            connection_type (str): 連携種別。

        Returns:
            dict: 最新の自動入力設定。未登録の場合は空の辞書。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_AUTO_INPUT_INFO", location=__file__),
            {"USER_ID": user_id, "CONNECTION_TYPE": connection_type},
        )
        return rows[0] if rows else {}

    def register_receipt(self, receipt_info, user_id):
        """
        自動取得した情報を領収書として登録する。

        Args:
            receipt_info (dict): 領収書登録情報。
            user_id (str): ユーザーID。

        Returns:
            dict: 領収書登録APIの実行結果。
        """
        token = set_current_user_id(user_id)
        try:
            return NewReceiptRegistration().call(
                headers={"x-kakeibo-user-id": user_id, "Content-Type": "application/json"},
                body={"receiptInfo": receipt_info},
            )
        finally:
            reset_current_user_id(token)

    def insert_auto_input_content(
        self,
        user_id,
        connection_type,
        invoice_number,
        receipt_date,
        receipt_time,
        content,
        status="3",
        source_key="",
    ):
        """
        自動入力済みデータを管理テーブルへ登録する。

        Args:
            user_id (str): ユーザーID。
            connection_type (str): 連携種別。
            invoice_number (str): 適格請求書発行事業者登録番号。
            receipt_date (str): YYYYMMDD形式の日付。
            receipt_time (str): HHMMSS形式の時刻。
            content (Any): 重複判定および監査用の取得内容。
            status (str): 自動入力状態。
            source_key (str): 外部サービス側データの一意キー。

        Returns:
            int: DB登録結果。
        """
        ymd, hms = now_ymd_hms()
        serialized = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
        resolved_key = source_key or hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return self.database.insert(
            self.database.read_sql("INSERT_KAKEIBO_AUTO_INPUT_CONT", location=__file__),
            {
                "PROGRAM": self.__class__.__name__,
                "INV_REG_NUM": invoice_number,
                "RET_CONT": serialized,
                "RET_DT": receipt_date,
                "RET_TM": receipt_time,
                "STATUS": status,
                "CONNECTION_TYPE": connection_type,
                "SOURCE_KEY": resolved_key,
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "USER_ID": user_id,
            },
        )

    @staticmethod
    def value(row, *keys):
        """
        辞書から大文字小文字を区別せず値を取得する。

        Args:
            row (dict): 検索対象。
            keys (str): 候補キー。

        Returns:
            Any: 最初に見つかった値。
        """
        lower = {str(key).lower(): value for key, value in (row or {}).items()}
        for key in keys:
            if key in (row or {}):
                return row.get(key)
            if str(key).lower() in lower:
                return lower[str(key).lower()]
        return None

    @staticmethod
    def normalize_auto_input_date(value):
        """
        日付をYYYYMMDD形式へ変換する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        text = str(value or "").strip()
        digits = "".join(character for character in text if character.isdigit())
        if len(digits) == 6:
            digits = f"20{digits}"
        return digits[:8]

    @staticmethod
    def normalize_auto_input_time(value):
        """
        時刻をHHMMSS形式へ変換する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        digits = "".join(character for character in str(value or "") if character.isdigit())
        return (digits + "000000")[:6]
