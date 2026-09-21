# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""予算情報の登録・更新API。"""
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error
from datetime import datetime


class NewBudgetRegistration(BaseRestApi):
    """予算分類ごとの登録・更新を扱うAPIクラス。"""

    def __init__(self ,db_path: Optional[str] = None):
        """
        クラスを初期化する。

        Args:
            db_path (Optional[str]): 旧呼び出し互換のためのDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__,db_path = db_path or None)
        self._validate_body_functions = {}

    def validate_headers(self, request_dict):

        """
        リクエストヘッダーを検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        # 既存のBaseRestApiバリデーションフローへ委譲する。
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def main(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        処理概要: 予算情報を新規登録する。
        処理内容:
          1. 認証済みユーザーと入力値を取得する。
          2. 対象の予算設定と既存データを確認する。
          3. 予算を登録または更新して結果を返す。

        Args:
            request_dict (Dict[str, Any]): 正規化済みのリクエストコンテキスト。

        Returns:
            Dict[str, Any]: 標準化されたAPIレスポンス。
        """
        self.logger.info(f"リクエストボディ: {request_dict.get('body')}")
        body = request_dict.get("body", {})
        user_id = self.require_user_id(request_dict)
        if not body:
            raise Error(status_code=510,
                        error_code="1000062",
                        message="リクエストのボディが空です。")

        budget_info = body.get("budget_info", {})
        if budget_info.get("category1",None) and budget_info.get("category2",None):
            select_result = self.select_budget_record(budget_info=budget_info, user_id=user_id)
        else:
            raise Error(status_code=510,
                        error_code="1000062",
                        message="必要パラメータが未入力です") 
        if not select_result:
            self.insert_budget_info(budget_info=budget_info, user_id=user_id)
        else :
            self.update_budget_info(budget_info=budget_info, user_id=user_id)

        api_response = {"message": "予算の情報が正常に保存されました。"}

        return response(status_code=201, body=api_response)

    def exception(self, e: Exception) -> dict:
        """
            例外処理を行う。

            Args:
                e(Exception): 発生した例外。

            Returns:
                dict: REST APIのレスポンスとしてエラーコードを返す。
            """
        return super().exception(e)
    

    def select_budget_record(self, budget_info: dict, user_id: str):
        """
        指定された大分類・小分類の予算レコードを取得する。

        Args:
            budget_info (dict): budget_infoの値。
            user_id (str): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        params={
            "CAT1":budget_info.get("category1"),
            "CAT2":budget_info.get("category2"),
            "USER_ID": user_id,
        }
        sql = self.database.read_sql("SELECT_BUDGET_INFO", location=__file__)
        result=self.database.select(sql,params=params)

        return result 

    def insert_budget_info(self, budget_info: Dict[str,
                                                                      Any], user_id: str):
        """
        未登録の分類に対して予算情報を新規登録する。

        Args:
            budget_info (Dict[str, Any]): budget_infoの値。
            user_id (str): ユーザーID。

        Returns:
            Any: 処理結果。
        """

        budget_info_data = {
            "CRE_PROG":str(__class__.__name__),
            "UPD_PROG":str(__class__.__name__),
            "CAT1": budget_info.get("category1"),
            "CAT2": budget_info.get("category2"),
            "BUT_AMT": budget_info.get("budgetAmount"),
            "CRE_DT":datetime.now().strftime("%Y%m%d"),
            "CRE_TM":datetime.now().strftime("%H%M%S"),
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "USER_ID": user_id,
            "DEL_FLAG": 0
        }
        sql = self.database.read_sql("INSERT_BUDGET_INFO", location=__file__)
        self.database.insert(sql, params=budget_info_data)

    def update_budget_info(self, budget_info: Dict[str,
                                                                      Any], user_id: str):
        """
        登録済み分類の予算金額を更新する。

        Args:
            budget_info (Dict[str, Any]): budget_infoの値。
            user_id (str): ユーザーID。

        Returns:
            Any: 処理結果。
        """

        budget_info_data = {
            "UPD_PROG":str(__class__.__name__),
            "CAT1": budget_info.get("category1"),
            "CAT2": budget_info.get("category2"),
            "BUT_AMT": budget_info.get("budgetAmount"),
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "USER_ID": user_id,
            "DEL_FLAG": 0
        }
        sql = self.database.read_sql("UPDATE_BUDGET_INFO", location=__file__)
        self.database.insert(sql, params=budget_info_data)

  
