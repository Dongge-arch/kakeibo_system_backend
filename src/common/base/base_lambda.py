# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""
REST API とバッチに共通する Lambda 処理を提供する。
"""

import datetime
import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional
from zoneinfo import ZoneInfo

from src.common.base.base import Base
from src.common.const.datetime import TIME_ZONE_JST
from src.common.const.logger import REQUEST_BODY, REQUEST_HEADER, RESULT
from src.common.database.factory import create_database
from src.common.exception import Error
from src.common.log_sanitizer import (
    summarize_request_body,
    summarize_request_headers,
    summarize_response,
)


class BaseLambda(Base, ABC):
    """
    REST API とバッチの共通処理を提供する抽象クラス。
    """

    def __init__(
        self,
        class_name,
        validate_h=False,
        validate_b=False,
        database_readonly=False,
        db_path: Optional[str] = None,
        db_schema: str = "kakeibo",
    ):
        """
        クラスを初期化する。

        Args:
            class_name (Any): class_nameの値。
            validate_h (Any): validate_hの値。
            validate_b (Any): validate_bの値。
            database_readonly (Any): database_readonlyの値。
            db_path (Optional[str]): 旧呼び出し互換のためのDB指定。
            db_schema (str): db_schemaの値。

        Returns:
            None: 戻り値なし。
        """
        if not getattr(self, "_initialized", False):
            super().__init__(class_name)
            self._validate_body_functions = {}
            self._validate_headers_functions = []
            self.config = {}
            self._initialized = True

        self.database = create_database(db_path=db_path, schema=db_schema)

    def get_request_system(self) -> dict:
        """
        API呼び出しごとの共通システム情報を作成する。

        Args:
            None

        Returns:
            dict: system情報を含む辞書。local_dt（現在日時）、cache（キャッシュ用辞書）= Noneを含む。
        """

        return {
            "system": {
                "local_dt": datetime.datetime.now(ZoneInfo(TIME_ZONE_JST)),
                "cache": {},
            }
        }

    def append_cache(self, request_dict: dict, key, value):
        """
        同一リクエスト内で再利用する値をキャッシュへ保存する。

        Args:
            request_dict (dict): API呼び出し時のリクエスト情報を含む辞書。
            key: キャッシュに保存するキー。
            value: キャッシュに保存する値。

        Returns:
            None
        """
        if request_dict:
            request_dict.setdefault("system", {}).setdefault("cache", {})[key] = value

    def is_cache(self, request_dict: dict, key) -> bool:
        """
        同一リクエスト内キャッシュに指定キーが存在するか判定する。

        Args:
            request_dict (dict): API呼び出し時のリクエスト情報を含む辞書。
            key: キャッシュに存在するか判定するキー。

        Returns:
            bool: キャッシュに指定キーが存在する場合はTrue、存在しない場合はFalseを返す。
        """
        return bool(
            request_dict
            and key in request_dict.get("system", {}).get("cache", {})
        )

    def get_cache(self, request_dict: dict, key):
        """
        同一リクエスト内キャッシュから指定キーの値を取得する。
        
        Args:
            request_dict (dict): API呼び出し時のリクエスト情報を含む辞書。
            key: キャッシュから取得するキー。

        Returns:
            値: キャッシュに指定キーが存在する場合はその値を返す。存在しない場合はNoneを返す。
        """
        if not request_dict:
            return None
        return request_dict.get("system", {}).get("cache", {}).get(key)

    def call(
        self,
        body: Optional[dict] = None,
        headers: Optional[dict] = None,
        validate_h=False,
        validate_b=True,
        **kwargs,
    ) -> dict:
        """
        API呼び出しの共通処理を実行する。
        
        Args:
            body (dict, optional): API呼び出し時のリクエストボディ。デフォルトはNone。
            headers (dict, optional): API呼び出し時のリクエストヘッダ。デフォルトはNone。
            validate_h (bool, optional): ヘッダのバリデーションを行うかどうかのフラグ。デフォルトはFalse。
            validate_b (bool, optional): ボディのバリデーションを行うかどうかのフラグ。デフォルトはTrue。
            **kwargs: その他の任意のキーワード引数。
            
        Returns:
            dict: API呼び出しの結果を含む辞書。
        
        Raises:
            Exception: API呼び出し中に発生した例外を再スローする。
        """
        normalized_headers = self.normalize_headers(headers or {})
        request_dict = {
            "headers": normalized_headers,
            "body": body or {},
            **self.get_request_system(),
            **kwargs,
        }
        request_id = kwargs.get("request_id") or uuid.uuid4().hex
        try:
            self.logger.set_request_id(request_id)
            self.logger.info(
                "%s: %s",
                REQUEST_HEADER,
                json.dumps(summarize_request_headers(request_dict["headers"]), ensure_ascii=False),
            )
            self.logger.info(
                "%s: %s",
                REQUEST_BODY,
                json.dumps(
                    summarize_request_body(request_dict["body"]),
                    ensure_ascii=False,
                    default=str,
                ),
            )

            if validate_h:
                self.validate_headers(request_dict)
            if validate_b:
                self.validate_body(request_dict)

            response = self.main(request_dict)
            if self.database:
                self.database.commit()

            self.logger.info(
                "%s: %s",
                RESULT,
                json.dumps(
                    summarize_response(response),
                    ensure_ascii=False,
                    default=str,
                ),
            )
            return response

        except Exception as e:
            if self.database:
                self.database.rollback()

            response = self.exception(e)
            self.logger.info(
                "%s: %s",
                RESULT,
                json.dumps(
                    summarize_response(response),
                    ensure_ascii=False,
                    default=str,
                ),
            )
            return response
        finally:
            self.logger.reset_request_id()

    def normalize_headers(self, headers: dict) -> dict:
        """
        ヘッダのキーを小文字に変換する。

        Args:
            headers (dict): API呼び出し時のリクエストヘッダ。

        Returns:
            dict: ヘッダのキーが小文字に変換された辞書。
        """
        return {str(key).lower(): value for key, value in dict(headers or {}).items()}

    def require_user_id(self, request_dict: dict) -> str:
        """
        リクエストからユーザーIDを取得する。

        Args:
            request_dict (dict): API呼び出し時のリクエスト情報。

        Returns:
            str: ユーザーID。

        Raises:
            Error: ユーザーIDがリクエストに含まれていない場合。
        """
        user_id = ""
        if request_dict:
            user_id = request_dict.get("headers", {}).get("x-kakeibo-user-id", "")
        if not user_id:
            raise Error(status_code=401, error_code="1000062", message="userId is required.")
        return user_id

    def require_verified_user_id(self, request_dict: dict) -> str:
        """
        署名済みJWTを検証してユーザーIDを取得する。

        Args:
            request_dict (dict): Authorizationヘッダーを含むリクエスト。

        Returns:
            str: JWTのsubjectに設定されたユーザーID。
        """
        from src.common.auth_token import verify_token

        headers = request_dict.get("headers") or {}
        authorization = str(headers.get("authorization") or "")
        token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
        user_id = verify_token(token).get("userId") if token else None
        if not user_id:
            raise Error(status_code=401, error_code="1000062", message="ログインしてください。")
        return str(user_id)
    
    def validate_headers(self, request_dict: dict):
        """
        ヘッダをバリデーションする。

        Args:
            request_dict (dict): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。

        Raises:
            Exception: バリデーションに失敗した場合。
        """
        start = time.perf_counter()
        list(
            map(
                lambda f: f.call(**request_dict["headers"]),
                self._validate_headers_functions,
            )
        )
        end = time.perf_counter()
        self.logger.info(f"validate_headers elapsed(ms): {(end - start) * 1000:.4f}")

    def validate_body(self, request_dict: dict):
        """
        ボディをバリデーションする。

        Args:
            request_dict (dict): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。

        Raises:
            Exception: バリデーションに失敗した場合。
        """
        self._validate_body(request_dict["body"])

    def _validate_body(self, param):
        """
        辞書・配列を再帰的にたどり、登録済みバリデータを実行する。

        Args:
            param: バリデーション対象の辞書または配列。

        Returns:
            Any: 処理結果。

        Raises:
            Exception: バリデーションに失敗した場合。
        """
        if isinstance(param, list):
            list(map(self._validate_body, param))
        elif isinstance(param, dict):
            for key, value in param.items():
                funcs = self._validate_body_functions.get(key)
                if funcs is not None:
                    list(map(lambda f: f.call(**{key: value}), funcs))
                else:
                    self._validate_body(value)

    @abstractmethod
    def main(self, request_dict: dict) -> dict:
        """
        処理概要: APIまたはバッチ固有の主処理を定義する。
        処理内容:
          1. 共通のリクエスト情報を受け取る。
          2. 実装クラスで固有処理を実行する。
          3. 標準レスポンスを返す。

        Args:
            request_dict (dict): API呼び出し時のリクエスト情報。

        Returns:
            dict: API呼び出しの結果を含む辞書。
        """
        pass
    def exception(self, e: Exception) -> dict:
        """
        例外処理を実装する。

        Args:
            e (Exception): 発生した例外。

        Returns:
            dict: 例外処理の結果を含む辞書。
        """
        if isinstance(e, Error):
            self.logger.info(e)
            return e.response()

        self.logger.error(e)
        import traceback

        traceback.print_exc()
        return Error(510, "1000062").response()

    def flatten_dict(self, nested_dict, parent_key="", sep="."):
        """
        ネストした辞書をログや比較で扱いやすいフラットな辞書へ変換する。

        Args:
            nested_dict (dict): ネストした辞書。
            parent_key (str, optional): 親キーのプレフィックス。デフォルトは空文字。
            sep (str, optional): キーの結合に使用するセパレータ。デフォルトはドット（"."）。

        Returns:
            dict: フラットな辞書。
        """
        flattened = {}
        for key, value in nested_dict.items():
            if isinstance(value, dict):
                flattened.update(self.flatten_dict(value, key, sep=sep))
            else:
                flattened[key] = value
        return flattened
    
    def lambda_handler(self, event, context):
        """
        AWS Lambdaのハンドラ関数。
        
        Args:
            event: Lambdaイベント。
            context: Lambdaコンテキスト。
            
        Returns:
            dict: Lambda関数のレスポンス。
            
        """
        if isinstance(event.get("body"), str):
                body = json.loads(event.get("body") or "{}")
        else:
                body = event.get("body") or {}

        result = self.call(
            body=body,
            headers=event.get("headers") or {},
            request_id=getattr(context, "aws_request_id", None),
        )
        from src.common.api_utils import normalize_api_body

        return {
            "statusCode": result.get("statusCode", 200),
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(normalize_api_body(result.get("body")), ensure_ascii=False, default=str),
        }
