# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from datetime import datetime

from src.api.utils import json_response, now_ymd_hms
from src.common.base import BaseRestApi


class IncomeApi(BaseRestApi):
    """入金情報の登録、参照、更新、削除を扱うAPIクラス。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        """actionに応じて入金系の処理へ振り分ける。"""
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        action = body.get("action")
        if action == "create":
            return self.create_income(body.get("salaryInfo") if isinstance(body.get("salaryInfo"), dict) else body, user_id)
        if action == "list":
            return self.list_income(body, user_id)
        if action == "update":
            return self.update_income(body, user_id)
        if action == "delete":
            return self.delete_income(body, user_id)
        return json_response(400, {"errorMessage": "unknown income action"})

    def create_income(self, body, user_id):
        """画面入力を既存DB形式へ変換して入金情報を登録する。"""
        salary_time = body.get("salaryTime") or ""
        salary_date = body.get("salaryDate")
        if salary_time and len(str(salary_time)) == 5:
            salary_time = datetime.strptime(salary_time, "%H:%M").strftime("%H%M%S")
        if salary_date:
            salary_date = datetime.strptime(salary_date, "%Y-%m-%d").strftime("%Y%m%d")

        ymd, hms = now_ymd_hms()
        self.database.insert(
            """
            INSERT INTO salary_info (
                CRE_PROG, UPD_PROG, SAL_DATE, SAL_NAME, SAL_CAT, SAL_SUB_CAT,
                SAL_COMMENT, SAL_AMT, CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG
            )
            VALUES (
                %(CRE_PROG)s, %(UPD_PROG)s, %(SAL_DATE)s, %(SAL_NAME)s, %(SAL_CAT)s, %(SAL_SUB_CAT)s,
                %(SAL_COMMENT)s, %(SAL_AMT)s, %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, %(USER_ID)s, %(USER_ID)s, %(DEL_FLAG)s
            )
            """,
            {
                "CRE_PROG": "SalaryRegistrationNew",
                "UPD_PROG": "SalaryRegistrationNew",
                "SAL_DATE": salary_date,
                "SAL_NAME": body.get("salaryName"),
                "SAL_CAT": body.get("salaryCategory"),
                "SAL_SUB_CAT": "",
                "SAL_COMMENT": body.get("salaryComment"),
                "SAL_AMT": body.get("salaryAmount"),
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
                "DEL_FLAG": 0,
            },
        )
        return {"statusCode": 201, "message": "入金項目は正しく登録しました。"}

    def list_income(self, body, user_id):
        """月指定または日付範囲指定で入金情報を取得する。"""
        sql = "SELECT * FROM salary_info WHERE DEL_FLAG = 0 AND CRE_USER_ID = %(USER_ID)s"
        params = {"USER_ID": user_id}
        if body.get("month"):
            sql += " AND SAL_DATE LIKE %(SAL_DATE_PREFIX)s"
            params["SAL_DATE_PREFIX"] = f"{body['month'].replace('-', '')}%"
        elif body.get("dateFrom") and body.get("dateTo"):
            sql += " AND SAL_DATE >= %(DATE_FROM)s AND SAL_DATE <= %(DATE_TO)s"
            params["DATE_FROM"] = datetime.strptime(body["dateFrom"], "%Y-%m-%d").strftime("%Y%m%d")
            params["DATE_TO"] = datetime.strptime(body["dateTo"], "%Y-%m-%d").strftime("%Y%m%d")

        rows = self.database.select(sql, params)
        response = []
        for row in rows:
            salary_date = row.get("SAL_DATE")
            if salary_date:
                salary_date = datetime.strptime(salary_date, "%Y%m%d").strftime("%Y-%m-%d")
            response.append({
                "id": row.get("id"),
                "salaryDate": salary_date,
                "salaryName": row.get("SAL_NAME"),
                "salaryCategory": row.get("SAL_CAT"),
                "salaryAmount": row.get("SAL_AMT"),
            })
        return json_response(200, response)

    def update_income(self, body, user_id):
        """指定IDの入金情報を更新する。"""
        income_id = body.get("id")
        if not income_id:
            return {"statusCode": 400, "error": "id is required"}
        salary_date = body.get("salaryDate")
        if salary_date:
            salary_date = datetime.strptime(salary_date, "%Y-%m-%d").strftime("%Y%m%d")
        _, hms = now_ymd_hms()
        ymd = datetime.now().strftime("%Y%m%d")
        self.database.execute(
            """
            UPDATE salary_info
            SET SAL_DATE = %(SAL_DATE)s,
                SAL_NAME = %(SAL_NAME)s,
                SAL_CAT = %(SAL_CAT)s,
                SAL_AMT = %(SAL_AMT)s,
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s,
                UPD_USER_ID = %(USER_ID)s,
                DEL_FLAG = 0
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {
                "SAL_DATE": salary_date,
                "SAL_NAME": body.get("salaryName"),
                "SAL_CAT": body.get("salaryCategory"),
                "SAL_AMT": body.get("salaryAmount"),
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "USER_ID": user_id,
                "id": income_id,
            },
        )
        return {"statusCode": 200, "message": "ok"}

    def delete_income(self, body, user_id):
        """指定IDの入金情報を論理削除する。"""
        income_id = body.get("id")
        if not income_id:
            return {"statusCode": 400, "error": "id is required"}
        ymd, hms = now_ymd_hms()
        self.database.execute(
            """
            UPDATE salary_info
            SET DEL_FLAG = 1, UPD_DT = %(UPD_DT)s, UPD_TM = %(UPD_TM)s, UPD_USER_ID = %(USER_ID)s
            WHERE id = %(id)s AND CRE_USER_ID = %(USER_ID)s AND DEL_FLAG = 0
            """,
            {"UPD_DT": ymd, "UPD_TM": hms, "USER_ID": user_id, "id": income_id},
        )
        return {"statusCode": 200, "message": "ok"}
