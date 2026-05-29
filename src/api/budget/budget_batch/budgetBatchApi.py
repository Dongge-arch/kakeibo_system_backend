# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from src.api.utils import now_ymd_hms, json_response
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
        action = body.get("action")
        if action == "list":
            return json_response(200, self.list_budgets())
        if action == "upsert":
            self.upsert_budgets(body.get("budgets") or [])
            return json_response(200, {"ok": True})
        return json_response(400, {"errorMessage": "unknown budget action"})

    def list_budgets(self):
        """有効な予算情報を画面表示用の項目名で取得する。"""
        return self.database.select(
            """
            SELECT CAT1 as category1, CAT2 as category2, BUT_AMT as budgetAmount
            FROM budget_info
            WHERE DEL_FLAG = 0
            """
        )

    def upsert_budgets(self, budgets):
        """分類単位で既存予算を更新し、未登録の分類は新規追加する。"""
        ymd, hms = now_ymd_hms()
        for item in budgets:
            cat1 = item.get("category1") or ""
            cat2 = item.get("category2") or ""
            amount = item.get("budgetAmount") or 0
            if not cat1:
                continue

            existing = self.database.select(
                """
                SELECT id FROM budget_info
                WHERE CAT1 = %(CAT1)s AND COALESCE(CAT2, '') = %(CAT2)s AND DEL_FLAG = 0
                LIMIT 1
                """,
                {"CAT1": cat1, "CAT2": cat2},
            )

            if existing:
                self.database.execute(
                    """
                    UPDATE budget_info
                    SET BUT_AMT = %(BUT_AMT)s,
                        UPD_PROG = %(UPD_PROG)s,
                        UPD_DT = %(UPD_DT)s,
                        UPD_TM = %(UPD_TM)s
                    WHERE id = %(id)s
                    """,
                    {
                        "BUT_AMT": amount,
                        "UPD_PROG": "budget_upsert",
                        "UPD_DT": ymd,
                        "UPD_TM": hms,
                        "id": existing[0]["id"],
                    },
                )
                continue

            self.database.insert(
                """
                INSERT INTO budget_info (
                  CRE_PROG, UPD_PROG, CAT1, CAT2, BUT_AMT,
                  CRE_DT, CRE_TM, UPD_DT, UPD_TM, DEL_FLAG
                ) VALUES (
                  %(CRE_PROG)s, %(UPD_PROG)s, %(CAT1)s, %(CAT2)s, %(BUT_AMT)s,
                  %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, %(DEL_FLAG)s
                )
                """,
                {
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
                },
            )
