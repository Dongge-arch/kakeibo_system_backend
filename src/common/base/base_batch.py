# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""Shared base class for local API classes."""

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


class BaseBatch(Base, ABC):
    """Provide the common local API execution flow."""

    def __init__(
        self,
        class_name,
        validate_h=False,
        validate_b=False,
        database_readonly=False,
        db_path: Optional[str] = None,
    ):
        if not getattr(self, "_initialized", False):
            super().__init__(class_name)
            self._validate_body_functions = {}
            self._validate_headers_functions = []
            self.config = {}
            self._initialized = True

        self.database = create_database(db_path=db_path)


    def append_cache(self, request_dict: dict, key, value):
        """同一リクエスト内で再利用する値をキャッシュへ保存する。"""
        if request_dict:
            request_dict.setdefault("system", {}).setdefault("cache", {})[key] = value

    def is_cache(self, request_dict: dict, key) -> bool:
        """同一リクエスト内キャッシュに指定キーが存在するか判定する。"""
        return bool(
            request_dict
            and key in request_dict.get("system", {}).get("cache", {})
        )

    def get_cache(self, request_dict: dict, key):
        """同一リクエスト内キャッシュから指定キーの値を取得する。"""
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
        """Run an API class directly from app.py."""
        normalized_headers = self.normalize_headers(headers or {})
        request_dict = {
            "headers": normalized_headers,
            "body": body or {},
            **kwargs,
        }
        request_id = kwargs.get("request_id") or uuid.uuid4().hex

        try:
            self.logger.set_request_id(request_id)
            self.logger.info(
                "%s: %s",
                REQUEST_HEADER,
                json.dumps(request_dict["headers"], ensure_ascii=False),
            )
            self.logger.info(
                "%s: %s",
                REQUEST_BODY,
                json.dumps(request_dict["body"], ensure_ascii=False, default=str),
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
                json.dumps(response, ensure_ascii=False, default=str),
            )
            return response

        except Exception as e:
            if self.database:
                self.database.rollback()

            response = self.exception(e)
            self.logger.info(
                "%s: %s",
                RESULT,
                json.dumps(response, ensure_ascii=False, default=str),
            )
            return response
        finally:
            self.logger.reset_request_id()

    def normalize_headers(self, headers: dict) -> dict:
        return {str(key).lower(): value for key, value in dict(headers or {}).items()}

    def require_user_id(self, request_dict: dict) -> str:
        user_id = ""
        if request_dict:
            user_id = request_dict.get("headers", {}).get("x-kakeibo-user-id", "")
        if not user_id:
            raise Error(status_code=401, error_code="1000062", message="userId is required.")
        return user_id

    def validate_headers(self, request_dict: dict):
        start = time.perf_counter()
        list(
            map(
                lambda f: f.call(**request_dict["headers"]),
                self._validate_headers_functions,
            )
        )
        end = time.perf_counter()
        self.logger.info(f"validate_headers elapsed(ms): {(end - start) * 1000:.4f}")

    @abstractmethod
    def validate_body(self, request_dict: dict):
        self._validate_body(request_dict["body"])

    def _validate_body(self, param):
        """辞書・配列を再帰的にたどり、登録済みバリデータを実行する。"""
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
        pass

    def exception(self, e: Exception) -> dict:
        if isinstance(e, Error):
            self.logger.info(e)
            return e.response()

        self.logger.error(e)
        import traceback

        traceback.print_exc()
        return Error(510, "1000062").response()

    def flatten_dict(self, nested_dict, parent_key="", sep="."):
        """ネストした辞書をログや比較で扱いやすいフラットな辞書へ変換する。"""
        flattened = {}
        for key, value in nested_dict.items():
            if isinstance(value, dict):
                flattened.update(self.flatten_dict(value, key, sep=sep))
            else:
                flattened[key] = value
        return flattened
    
    def lambda_handler(self, event, context):
        if isinstance(event.get("body"), str):
                body = json.loads(event.get("body") or "{}")
        else:
                body = event.get("body") or {}

        result = self.call(
            body=body,
            headers=event.get("headers") or {},
            request_id=getattr(context, "aws_request_id", None),
        )
        from src.api.utils import normalize_api_body

        return {
            "statusCode": result.get("statusCode", 200),
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(normalize_api_body(result.get("body")), ensure_ascii=False, default=str),
        }
