# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from src.api.utils import now_ymd_hms
from src.common.functions.response import response
from src.common.base import BaseRestApi


class BudgetBatchApi(BaseRestApi):
    """予算一覧取得と一括更新を扱うAPIクラス。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        """actionに応じて予算の一覧取得・一括更新を実行する。"""
        body = request_dict.get("body") or {}
        # ユーザーIDを取得
        user_id = self.require_user_id(request_dict)
        action = body.get("action")
        if action == "list":
            result = self.list_budgets(user_id)
            return response(200, result)
        if action == "upsert":
            self.upsert_budgets(body.get("budgets") or [], user_id)
            result = {"ok": True}
            return response(200, result)
        
        return response(400, {"errorMessage": "unknown budget action"})

    def list_budgets(self, user_id):
        """有効な予算情報を画面表示用の項目名で取得する。"""

        param = {"USER_ID": user_id}
        return self.database.select(
            """
            SELECT CAT1 as category1, CAT2 as category2, BUT_AMT as budgetAmount
            FROM budget_info
            WHERE DEL_FLAG = 0 AND CRE_USER_ID = %(USER_ID)s
            """,
            param,
        )

    def upsert_budgets(self, budgets, user_id):
        """分類単位で既存予算を更新し、未登録の分類は新規追加する。"""
        ymd, hms = now_ymd_hms()
        for item in budgets:
            cat1 = item.get("category1") or ""
            cat2 = item.get("category2") or ""
            amount = item.get("budgetAmount") or 0
            if not cat1:
                continue
            
            param = {"CAT1": cat1, "CAT2": cat2, "USER_ID": user_id}
            existing = self.database.select(
                """
                SELECT id FROM budget_info
                WHERE CAT1 = %(CAT1)s AND COALESCE(CAT2, '') = %(CAT2)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
                LIMIT 1
                """,
                param,
            )

            if existing:
                param={"BUT_AMT": amount, "UPD_PROG": "budget_upsert", "UPD_DT": ymd, "UPD_TM": hms, "id": existing[0]["id"], "USER_ID": user_id}
                self.database.execute(
                    """
                    UPDATE budget_info
                    SET BUT_AMT = %(BUT_AMT)s,
                        UPD_PROG = %(UPD_PROG)s,
                        UPD_DT = %(UPD_DT)s,
                        UPD_TM = %(UPD_TM)s,
                        UPD_USER_ID = %(USER_ID)s
                    WHERE id = %(id)s
                      AND CRE_USER_ID = %(USER_ID)s
                    """,
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
                    "USER_ID": user_id,
                }

            self.database.insert(
                """
                INSERT INTO budget_info (
                  CRE_PROG, UPD_PROG, CAT1, CAT2, BUT_AMT,
                  CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
                ) VALUES (
                  %(CRE_PROG)s, %(UPD_PROG)s, %(CAT1)s, %(CAT2)s, %(BUT_AMT)s,
                  %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, %(USER_ID)s, %(USER_ID)s, %(DEL_FLAG)s
                )
                """,
                param,
            )
            continue        

            