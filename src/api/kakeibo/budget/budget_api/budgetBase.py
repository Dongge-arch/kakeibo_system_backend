# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from src.common.api_utils import now_ymd_hms
from src.common.base import BaseRestApi


class BudgetBase(BaseRestApi):
    """予算一覧取得と一括更新に共通するDB操作。"""

    def __init__(self, db_path=None):
        """
        クラスを初期化する。

        Args:
            db_path (Any): 旧呼び出し互換のためのDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def list_budgets(self, user_id):
        """
        有効な予算情報を画面表示用の項目名で取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """

        param = {"CRE_USER_ID": user_id}
        return self.database.select(
            self.database.read_sql("SELECT_BUDGET_INFO", location=__file__),
            param,
        )

    def upsert_budgets(self, budgets, user_id):
        """
        分類単位で既存予算を更新し、未登録の分類は新規追加する。

        Args:
            budgets (Any): budgetsの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        ymd, hms = now_ymd_hms()
        for item in budgets:
            cat1 = item.get("category1") or ""
            cat2 = item.get("category2") or ""
            amount = item.get("budgetAmount") or 0
            if not cat1:
                continue
            
            param = {"CAT1": cat1, "CAT2": cat2, "CRE_USER_ID": user_id}
            existing = self.database.select(
                self.database.read_sql("SELECT_BUDGET_INFO_02", location=__file__),
                param,
            )

            if existing:
                param={"BUT_AMT": amount, "UPD_PROG": "budget_upsert", "UPD_DT": ymd, "UPD_TM": hms, "ID": existing[0].get("ID", existing[0].get("id")), "CRE_USER_ID": user_id, "UPD_USER_ID": user_id}
                self.database.execute(
                    self.database.read_sql("UPDATE_BUDGET_INFO", location=__file__),
                    param,
                )
                continue
            param = {
                    "CRE_PROG": "budget_upsert",
                    "UPD_PROG": "budget_upsert",
                    "CAT1": cat1,
                    "CAT2": cat2,
                    "BUT_AMT": amount,
                    "CRE_DT": ymd,
                    "CRE_TM": hms,
                    "UPD_DT": ymd,
                    "UPD_TM": hms,
                    "DEL_FLAG": 0,
                    "CRE_USER_ID": user_id,
                    "UPD_USER_ID": user_id,
                }

            self.database.insert(
                self.database.read_sql("INSERT_BUDGET_INFO", location=__file__),
                param,
            )
            continue
