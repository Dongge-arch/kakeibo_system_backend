# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import base64

from src.api.utils import (
    json_response,
    normalize_invoice_number,
    normalize_tax_flag,
)
from src.common.base import BaseRestApi


class MasterDataApi(BaseRestApi):
    """レシート関連マスタと入金分類マスタを扱うAPIクラス。"""

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        """actionに応じて各マスタ処理へ振り分ける。"""
        body = request_dict.get("body") or {}
        action = body.get("action")

        actions = {
            "list_category1": self.list_category1,
            "add_category1": lambda: self.add_category1(body),
            "delete_category1": lambda: self.delete_category1(body),
            "list_category2": self.list_category2,
            "add_category2": lambda: self.add_category2(body),
            "delete_category2": lambda: self.delete_category2(body),
            "supplier_by_invoice": lambda: self.supplier_by_invoice(body),
            "list_invoice": self.list_invoice,
            "delete_invoice": lambda: self.delete_invoice(body),
            "update_invoice": lambda: self.update_invoice(body),
            "add_salary_category": lambda: self.add_salary_category(body),
            "list_salary_category": self.list_salary_category,
            "delete_salary_category": lambda: self.delete_salary_category(body),
        }

        handler = actions.get(action)
        if not handler:
            return json_response(400, {"errorMessage": "unknown master action"})
        return handler()

    def list_category1(self):
        """レシート大分類の有効データを取得する。"""
        rows = self.database.select(
            "SELECT DISTINCT CATEGORY1_NAME FROM receipt_info_category1 WHERE DEL_FLAG = 0"
        )
        return json_response(200, rows)

    def add_category1(self, body):
        """レシート大分類を追加する。"""
        name = body.get("category1_name")
        if not name:
            return {"statusCode": 400, "error": "category1_name is required"}
        self.database.execute(
            "INSERT INTO receipt_info_category1 (CATEGORY1_NAME) VALUES (:CATEGORY1_NAME)",
            {"CATEGORY1_NAME": name},
        )
        return {"statusCode": 201, "message": "Category1 added successfully"}

    def delete_category1(self, body):
        """レシート大分類を論理削除する。"""
        name = body.get("category1_name")
        if not name:
            return {"statusCode": 400, "error": "category1_name is required"}
        self.database.execute(
            "UPDATE receipt_info_category1 SET DEL_FLAG = 1 WHERE CATEGORY1_NAME = :CATEGORY1_NAME",
            {"CATEGORY1_NAME": name},
        )
        return {"statusCode": 200, "message": "Category1 deleted successfully"}

    def list_category2(self):
        """レシート小分類と税率を取得する。"""
        rows = self.database.select(
            "SELECT CATEGORY1_NAME, CATEGORY2_NAME, TAX_RATE FROM receipt_info_category2 WHERE DEL_FLAG = 0"
        )
        for row in rows:
            try:
                rate = float(row.get("TAX_RATE"))
            except (TypeError, ValueError):
                rate = 0.1
            row["TAX_RATE"] = 0.08 if abs(rate - 0.08) < 0.001 else 0.1
        return json_response(200, rows)

    def add_category2(self, body):
        """レシート小分類を大分類・税率と一緒に追加する。"""
        category2_name = body.get("category2_name")
        category1_name = body.get("category1_name")
        tax_rate = body.get("tax_rate", 0.1)
        if not category2_name or not category1_name:
            return {"statusCode": 400, "error": "category1_name and category2_name are required"}
        self.database.execute(
            """
            INSERT INTO receipt_info_category2 (CATEGORY1_NAME, CATEGORY2_NAME, TAX_RATE)
            VALUES (:CATEGORY1_NAME, :CATEGORY2_NAME, :TAX_RATE)
            """,
            {
                "CATEGORY1_NAME": category1_name,
                "CATEGORY2_NAME": category2_name,
                "TAX_RATE": tax_rate,
            },
        )
        return {"statusCode": 201, "message": "Category2 added successfully"}

    def delete_category2(self, body):
        """指定した大分類・小分類の組み合わせを論理削除する。"""
        category2_name = body.get("category2_name")
        category1_name = body.get("category1_name")
        if not category2_name or not category1_name:
            return {"statusCode": 400, "error": "category1_name and category2_name are required"}
        self.database.execute(
            """
            UPDATE receipt_info_category2
            SET DEL_FLAG = 1
            WHERE CATEGORY1_NAME = :CATEGORY1_NAME AND CATEGORY2_NAME = :CATEGORY2_NAME
            """,
            {"CATEGORY1_NAME": category1_name, "CATEGORY2_NAME": category2_name},
        )
        return {"statusCode": 200, "message": "Category2 deleted successfully"}

    def supplier_by_invoice(self, body):
        """インボイス登録番号から取引先名、ロゴ、税区分を取得する。"""
        invoice_no = normalize_invoice_number(body.get("invoiceNo"))
        if not invoice_no:
            return json_response(400, {
                "errorMessage": "登録番号は T を除いた13桁、または T + 13桁で指定してください。"
            })
        rows = self.database.select(
            """
            SELECT SUP_NAME AS supplierName, IMG AS supplierLogo, TAX_FLAG AS taxFlag
            FROM invoice_registration
            WHERE INV_REG_NUM = :INV_REG_NUM AND DEL_FLAG = 0
            """,
            {"INV_REG_NUM": invoice_no},
        )
        for row in rows:
            image = row.get("supplierLogo")
            if image and isinstance(image, (bytes, bytearray)):
                row["supplierLogo"] = base64.b64encode(image).decode("utf-8")
            if row.get("taxFlag") is None:
                row["taxFlag"] = 1
        return json_response(200, rows)

    def list_invoice(self):
        """インボイス登録マスタの有効データを取得する。"""
        rows = self.database.select("SELECT * FROM invoice_registration WHERE DEL_FLAG = 0")
        return json_response(200, [self.invoice_response(row) for row in rows])

    def delete_invoice(self, body):
        """インボイス登録マスタを論理削除する。"""
        self.database.update(
            "UPDATE invoice_registration SET DEL_FLAG = 1 WHERE INV_REG_NUM = :INV_REG_NUM AND DEL_FLAG = 0",
            {"INV_REG_NUM": body.get("invoiceRegistrationNumber")},
        )
        return json_response(200, [])

    def update_invoice(self, body):
        """インボイス登録マスタの取引先名、税区分、画像を更新する。"""
        invoice_number = body.get("invoiceRegistrationNumber")
        params = {
            "SUP_NAME": body.get("supplierName"),
            "TAX_FLAG": normalize_tax_flag(body.get("taxFlag")),
            "INV_REG_NUM": invoice_number,
        }
        if body.get("supplierImage") is None:
            self.database.execute(
                """
                UPDATE invoice_registration
                SET SUP_NAME = :SUP_NAME, TAX_FLAG = :TAX_FLAG
                WHERE INV_REG_NUM = :INV_REG_NUM AND DEL_FLAG = 0
                """,
                params,
            )
        else:
            params["IMG"] = body.get("supplierImage")
            self.database.execute(
                """
                UPDATE invoice_registration
                SET IMG = :IMG, SUP_NAME = :SUP_NAME, TAX_FLAG = :TAX_FLAG
                WHERE INV_REG_NUM = :INV_REG_NUM AND DEL_FLAG = 0
                """,
                params,
            )
        rows = self.database.select(
            """
            SELECT INV_REG_NUM, IMG, SUP_NAME, TAX_FLAG
            FROM invoice_registration
            WHERE INV_REG_NUM = :INV_REG_NUM AND DEL_FLAG = 0
            """,
            {"INV_REG_NUM": invoice_number},
        )
        return json_response(200, [self.invoice_response(row) for row in rows])

    def invoice_response(self, row):
        """DB行を画面で扱うインボイス項目名へ変換する。"""
        return {
            "invoiceRegistrationNumber": row.get("INV_REG_NUM"),
            "supplierImage": row.get("IMG"),
            "supplierName": row.get("SUP_NAME"),
            "taxFlag": normalize_tax_flag(row.get("TAX_FLAG")),
        }

    def add_salary_category(self, body):
        """入金分類を追加する。"""
        name = body.get("salary_category_name")
        if not name:
            return {"statusCode": 400, "error": "salary_category_name is required"}
        self.database.execute(
            "INSERT INTO salary_info_category (SAL_CAT, DEL_FLAG) VALUES (:SAL_CAT, 0)",
            {"SAL_CAT": name},
        )
        return {"statusCode": 201, "message": "Category2 added successfully"}

    def list_salary_category(self):
        """入金分類の有効データを取得する。"""
        rows = self.database.select("SELECT * FROM salary_info_category WHERE DEL_FLAG = 0")
        return json_response(200, rows)

    def delete_salary_category(self, body):
        """入金分類を論理削除する。"""
        rows = self.database.update(
            "UPDATE salary_info_category SET DEL_FLAG = 1 WHERE DEL_FLAG = 0 AND SAL_CAT = :SAL_CAT",
            {"SAL_CAT": body.get("salary_category_name")},
        )
        return json_response(200, rows)
