# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""予算情報の参照API。"""
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error


class BudgetReference(BaseRestApi):
    """予算分類ごとの参照を扱うAPIクラス。"""

    def __init__(self ,db_path: Optional[str] = None):
        super().__init__(class_name=self.__class__.__name__,db_path = db_path or None)
        self._validate_body_functions = {}

    def validate_headers(self, request_dict):

        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        # 既存のBaseRestApiバリデーションフローへ委譲する。
        return super().validate_body(request_dict)

    def main(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        
        """
        Args:
            request_dict (Dict[str, Any]): 正規化済みのリクエストコンテキスト。

        Returns:
            Dict[str, Any]: 標準化されたAPIレスポンス。
        """
        self.logger.info(f"リクエストボディ: {request_dict.get('body')}")
        body = request_dict.get("body", {})
        if not body:
            raise Error(status_code=510,
                        error_code="1000062",
                        message="リクエストのボディが空です。")

        budget_list = body.get("budget_list") or body.get("budgets") or []
        response_list=[]
        for budget_info in budget_list:
            result = self.select_budget_record(budget_info=budget_info)
            response_list.extend(result or [])

        return response(status_code=200, body=response_list)

    def exception(self, e: Exception) -> dict:
        """
            例外処理を行う。

            Args:
                e(Exception): 発生した例外。

            Returns:
                dict: REST APIのレスポンスとしてエラーコードを返す。
            """
        return super().exception(e)
    

    def select_budget_record(self, budget_info: dict):
        """指定された大分類・小分類に一致する予算情報を取得する。"""
        params={
            "CAT1":budget_info.get("category1"),
            "CAT2":budget_info.get("category2"),
        }
        sql = self.database.read_sql("SELECT_BUDGET_INFO", location=__file__)
        result=self.database.select(sql,params=params)

        return result 

    
