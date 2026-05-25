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
        action = body.get("action")
        if action == "create":
            return self.create_income(body.get("salaryInfo") if isinstance(body.get("salaryInfo"), dict) else body)
        if action == "list":
            return self.list_income(body)
        if action == "update":
            return self.update_income(body)
        if action == "delete":
            return self.delete_income(body)
        return json_response(400, {"errorMessage": "unknown income action"})

    def create_income(self, body):
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
                SAL_COMMENT, SAL_AMT, CRE_DT, CRE_TM, UPD_DT, UPD_TM, DEL_FLAG
            )
            VALUES (
                :CRE_PROG, :UPD_PROG, :SAL_DATE, :SAL_NAME, :SAL_CAT, :SAL_SUB_CAT,
                :SAL_COMMENT, :SAL_AMT, :CRE_DT, :CRE_TM, :UPD_DT, :UPD_TM, :DEL_FLAG
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
                "DEL_FLAG": 0,
            },
        )
        return {"statusCode": 201, "message": "入金項目は正しく登録しました。"}

    def list_income(self, body):
        """月指定または日付範囲指定で入金情報を取得する。"""
        sql = "SELECT * FROM salary_info WHERE DEL_FLAG = 0"
        params = {}
        if body.get("month"):
            sql += " AND SAL_DATE LIKE :SAL_DATE_PREFIX"
            params["SAL_DATE_PREFIX"] = f"{body['month'].replace('-', '')}%"
        elif body.get("dateFrom") and body.get("dateTo"):
            sql += " AND SAL_DATE >= :DATE_FROM AND SAL_DATE <= :DATE_TO"
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

    def update_income(self, body):
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
            SET SAL_DATE = :SAL_DATE,
                SAL_NAME = :SAL_NAME,
                SAL_CAT = :SAL_CAT,
                SAL_AMT = :SAL_AMT,
                UPD_DT = :UPD_DT,
                UPD_TM = :UPD_TM,
                DEL_FLAG = 0
            WHERE id = :id AND DEL_FLAG = 0
            """,
            {
                "SAL_DATE": salary_date,
                "SAL_NAME": body.get("salaryName"),
                "SAL_CAT": body.get("salaryCategory"),
                "SAL_AMT": body.get("salaryAmount"),
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "id": income_id,
            },
        )
        return {"statusCode": 200, "message": "ok"}

    def delete_income(self, body):
        """指定IDの入金情報を論理削除する。"""
        income_id = body.get("id")
        if not income_id:
            return {"statusCode": 400, "error": "id is required"}
        ymd, hms = now_ymd_hms()
        self.database.execute(
            """
            UPDATE salary_info
            SET DEL_FLAG = 1, UPD_DT = :UPD_DT, UPD_TM = :UPD_TM
            WHERE id = :id AND DEL_FLAG = 0
            """,
            {"UPD_DT": ymd, "UPD_TM": hms, "id": income_id},
        )
        return {"statusCode": 200, "message": "ok"}
