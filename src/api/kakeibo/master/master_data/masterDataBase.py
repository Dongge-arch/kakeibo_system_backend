# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

from src.common.api_utils import (
    normalize_invoice_number,
    normalize_tax_flag,
)
from src.api.kakeibo.receipt.supplierLogoStorage import SupplierLogoStorage
from src.common.base import BaseRestApi
from src.common.functions.response import response


class MasterDataBase(BaseRestApi):
    """マスタAPI間で共有するDB操作。"""

    def __init__(self, db_path=None):
        """
        クラスを初期化する。

        Args:
            db_path (Any): 旧呼び出し互換のためのDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.logo_storage = SupplierLogoStorage()

    def validate_body(self, request_dict):
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def list_category1(self, user_id):
        """
        レシート大分類の有効データを取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_RECEIPT_INFO_CATEGORY1", location=__file__),
            {"USER_ID": user_id},
        )
        return response(200, rows)

    def add_category1(self, body, user_id):
        """
        レシート大分類を追加する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        name = body.get("category1Name") or body.get("category1_name")
        if not name:
            return response(400, {"errorMessage": "category1_name is required"})
        self.database.execute(
            self.database.read_sql("INSERT_RECEIPT_INFO_CATEGORY1", location=__file__),
            {"CATEGORY1_NAME": name, "USER_ID": user_id},
        )
        return response(201, {"message": "Category1 added successfully"})

    def delete_category1(self, body, user_id):
        """
        レシート大分類を論理削除する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        name = body.get("category1Name") or body.get("category1_name")
        if not name:
            return response(400, {"errorMessage": "category1_name is required"})
        self.database.execute(
            self.database.read_sql("UPDATE_RECEIPT_INFO_CATEGORY1", location=__file__),
            {"CATEGORY1_NAME": name, "USER_ID": user_id},
        )
        return response(200, {"message": "Category1 deleted successfully"})

    def list_category2(self, user_id):
        """
        レシート小分類と税率を取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_RECEIPT_INFO_CATEGORY2", location=__file__),
            {"USER_ID": user_id},
        )
        for row in rows:
            try:
                rate = float(row.get("TAX_RATE"))
            except (TypeError, ValueError):
                rate = 0.1
            row["TAX_RATE"] = 0.08 if abs(rate - 0.08) < 0.001 else 0.1
        return response(200, rows)

    def add_category2(self, body, user_id):
        """
        レシート小分類を大分類・税率と一緒に追加する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        category2_name = body.get("category2Name") or body.get("category2_name")
        category1_name = body.get("category1Name") or body.get("category1_name")
        tax_rate = body.get("taxRate", body.get("tax_rate", 0.1))
        if not category2_name or not category1_name:
            return response(400, {"errorMessage": "category1_name and category2_name are required"})
        self.database.execute(
            self.database.read_sql("INSERT_RECEIPT_INFO_CATEGORY2", location=__file__),
            {
                "CATEGORY1_NAME": category1_name,
                "CATEGORY2_NAME": category2_name,
                "TAX_RATE": tax_rate,
                "USER_ID": user_id,
            },
        )
        return response(201, {"message": "Category2 added successfully"})

    def delete_category2(self, body, user_id):
        """
        指定した大分類・小分類の組み合わせを論理削除する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        category2_name = body.get("category2Name") or body.get("category2_name")
        category1_name = body.get("category1Name") or body.get("category1_name")
        if not category2_name or not category1_name:
            return response(400, {"errorMessage": "category1_name and category2_name are required"})
        self.database.execute(
            self.database.read_sql("UPDATE_RECEIPT_INFO_CATEGORY2", location=__file__),
            {"CATEGORY1_NAME": category1_name, "CATEGORY2_NAME": category2_name, "USER_ID": user_id},
        )
        return response(200, {"message": "Category2 deleted successfully"})

    def add_default_categories(self, body, user_id):
        """
        画面から渡された標準分類を、既存分は重複させずに一括追加する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        category1_items = [self.clean_name(item) for item in body.get("category1", [])]
        category2_items = body.get("category2", [])
        salary_items = [self.clean_name(item) for item in body.get("salaryCategories", [])]

        category1_items = [item for item in category1_items if item]
        salary_items = [item for item in salary_items if item]

        existing_category1 = {
            row.get("CATEGORY1_NAME")
            for row in self.database.select(self.database.read_sql("SELECT_RECEIPT_INFO_CATEGORY1_02", location=__file__), {"USER_ID": user_id})
        }
        existing_category2 = {
            (row.get("CATEGORY1_NAME"), row.get("CATEGORY2_NAME"))
            for row in self.database.select(self.database.read_sql("SELECT_RECEIPT_INFO_CATEGORY2_02", location=__file__), {"USER_ID": user_id})
        }
        existing_salary = {
            row.get("SAL_CAT")
            for row in self.database.select(self.database.read_sql("SELECT_SALARY_INFO_CATEGORY_02", location=__file__), {"USER_ID": user_id})
        }

        added = {"category1": 0, "category2": 0, "salaryCategories": 0}
        for name in category1_items:
            if name in existing_category1:
                continue
            self.database.execute(
                self.database.read_sql("INSERT_RECEIPT_INFO_CATEGORY1_02", location=__file__),
                {"CATEGORY1_NAME": name, "USER_ID": user_id},
            )
            existing_category1.add(name)
            added["category1"] += 1

        for item in category2_items:
            if not isinstance(item, dict):
                continue
            category1_name = self.clean_name(item.get("category1Name") or item.get("category1_name"))
            category2_name = self.clean_name(item.get("category2Name") or item.get("category2_name"))
            tax_rate = item.get("taxRate", item.get("tax_rate", 0.1))
            if not category1_name or not category2_name:
                continue
            if category1_name not in existing_category1:
                self.database.execute(
                    self.database.read_sql("INSERT_RECEIPT_INFO_CATEGORY1_03", location=__file__),
                    {"CATEGORY1_NAME": category1_name, "USER_ID": user_id},
                )
                existing_category1.add(category1_name)
                added["category1"] += 1
            key = (category1_name, category2_name)
            if key in existing_category2:
                continue
            self.database.execute(
                self.database.read_sql("INSERT_RECEIPT_INFO_CATEGORY2_02", location=__file__),
                {
                    "CATEGORY1_NAME": category1_name,
                    "CATEGORY2_NAME": category2_name,
                    "TAX_RATE": tax_rate,
                    "USER_ID": user_id,
                },
            )
            existing_category2.add(key)
            added["category2"] += 1

        for name in salary_items:
            if name in existing_salary:
                continue
            self.database.execute(
                self.database.read_sql("INSERT_SALARY_INFO_CATEGORY_02", location=__file__),
                {"SAL_CAT": name, "USER_ID": user_id},
            )
            existing_salary.add(name)
            added["salaryCategories"] += 1

        return response(200, {"ok": True, "added": added})

    def clean_name(self, value):
        """
        clean_nameの処理を実行する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        return "" if value is None else str(value).strip()

    def supplier_by_invoice(self, body, user_id):
        """
        インボイス登録番号から取引先名、ロゴ、税区分を取得する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        invoice_no = normalize_invoice_number(body.get("invoiceNo"))
        if not invoice_no:
            return response(400, {
                "errorMessage": "登録番号は T を除いた13桁、または T + 13桁で指定してください。"
            })
        rows = self.database.select(
            self.database.read_sql("SELECT_INVOICE_REGISTRATION", location=__file__),
            {"INV_REG_NUM": invoice_no, "USER_ID": user_id},
        )
        for row in rows:
            row["supplierLogo"] = self.logo_storage.url_for(row.get("INV_REG_NUM"))
            row.pop("INV_REG_NUM", None)
            if row.get("taxFlag") is None:
                row["taxFlag"] = 1
        return response(200, rows)

    def list_invoice(self, user_id):
        """
        インボイス登録マスタの有効データを取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_INVOICE_REGISTRATION_02", location=__file__),
            {"USER_ID": user_id},
        )
        return response(200, [self.invoice_response(row) for row in rows])

    def delete_invoice(self, body, user_id):
        """
        インボイス登録マスタを論理削除する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        self.database.update(
            self.database.read_sql("UPDATE_INVOICE_REGISTRATION", location=__file__),
            {"INV_REG_NUM": body.get("invoiceRegistrationNumber"), "USER_ID": user_id},
        )
        return response(200, [])

    def update_invoice(self, body, user_id):
        """
        インボイス登録マスタの取引先名、税区分、画像を更新する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        invoice_number = body.get("invoiceRegistrationNumber")
        params = {
            "SUP_NAME": body.get("supplierName"),
            "TAX_FLAG": normalize_tax_flag(body.get("taxFlag")),
            "INV_REG_NUM": invoice_number,
            "USER_ID": user_id,
        }
        if body.get("supplierImage") is not None:
            self.logo_storage.upload(invoice_number, body.get("supplierImage"))
        self.database.execute(
            self.database.read_sql("UPDATE_INVOICE_REGISTRATION_02", location=__file__),
            params,
        )
        rows = self.database.select(
            self.database.read_sql("SELECT_INVOICE_REGISTRATION_03", location=__file__),
            {"INV_REG_NUM": invoice_number, "USER_ID": user_id},
        )
        return response(200, [self.invoice_response(row) for row in rows])

    def invoice_response(self, row):
        """
        DB行を画面で扱うインボイス項目名へ変換する。

        Args:
            row (Any): rowの値。

        Returns:
            Any: 処理結果。
        """
        supplier_logo = self.logo_storage.url_for(row.get("INV_REG_NUM"))
        return {
            "invoiceRegistrationNumber": row.get("INV_REG_NUM"),
            "supplierImage": supplier_logo,
            "supplierName": row.get("SUP_NAME"),
            "taxFlag": normalize_tax_flag(row.get("TAX_FLAG")),
        }

    def add_salary_category(self, body, user_id):
        """
        入金分類を追加する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        name = body.get("salaryCategoryName") or body.get("salary_category_name")
        if not name:
            return response(400, {"errorMessage": "salary_category_name is required"})
        self.database.execute(
            self.database.read_sql("INSERT_SALARY_INFO_CATEGORY", location=__file__),
            {"SAL_CAT": name, "USER_ID": user_id},
        )
        return response(201, {"message": "入金分類を登録しました。"})

    def list_salary_category(self, user_id):
        """
        入金分類の有効データを取得する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(self.database.read_sql("SELECT_SALARY_INFO_CATEGORY", location=__file__), {"USER_ID": user_id})
        return response(200, rows)

    def delete_salary_category(self, body, user_id):
        """
        入金分類を論理削除する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.update(
            self.database.read_sql("UPDATE_SALARY_INFO_CATEGORY", location=__file__),
            {"SAL_CAT": body.get("salaryCategoryName") or body.get("salary_category_name"), "USER_ID": user_id},
        )
        return response(200, rows)
