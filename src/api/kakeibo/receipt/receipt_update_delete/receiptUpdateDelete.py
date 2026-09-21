# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""レシート情報の更新・削除API。"""
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error
from datetime import datetime
from src.api.kakeibo.receipt.supplierLogoStorage import SupplierLogoStorage
from src.api.kakeibo.receipt.taxPrice import enrich_detail_prices
from src.api.kakeibo.receipt.receiptValidation import validate_receipt_for_save


class ReceiptUpdateDelete(BaseRestApi):
    """レシートヘッダと明細の更新・論理削除を扱うAPIクラス。"""

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
        self.logo_storage = SupplierLogoStorage()

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
        処理概要: 小票を更新または削除する。
        処理内容:
          1. 認証済みユーザーと小票IDを取得する。
          2. 対象小票の所有権と内容を検証する。
          3. 更新または論理削除を実行する。
          4. 結果を返す。

        Args:
            request_dict (Dict[str, Any]): 正規化済みのリクエストコンテキスト。

        Returns:
            Dict[str, Any]: 標準化されたAPIレスポンス。
        """


        body = request_dict.get("body", {})
        user_id = self.require_user_id(request_dict)
        
        if body.get("updateDeleteType") == "update":
            receipt_info = body.get("receiptInfo") or {}
            # 2026-06-28 Codex: 更新時も登録時と同じ業務チェックを通し、空明細や合計不一致を防ぐ。
            validate_receipt_for_save(receipt_info)
            receipt_id = receipt_info.get("receiptId")
            self.update_receipt_info(receipt_id=receipt_id,body=body,user_id=user_id)
            self.update_receipt_details(receipt_id=receipt_id,body=body,user_id=user_id)
            return response(status_code=200,
                            body={"message": "領収書の情報が正常に更新されました。"})
        else:
            receipt_id = body.get("receiptId")
            self.delete_receipt_info_and_details(receipt_id=receipt_id,user_id=user_id)
            return response(status_code=200,
                            body={"message": "領収書の情報が正常に削除されました。"})



    def exception(self, e: Exception) -> dict:
        """
            例外処理を行う。

            Args:
                e(Exception): 発生した例外。

            Returns:
                dict: REST APIのレスポンスとしてエラーコードを返す。
            """
        return super().exception(e)

    def select_receipt_info(self, receipt_id: str, user_id: str) -> Dict[str, Any]:
        """
        領収書の情報を取得

        Args:
            receipt_id(str): 領収書ID

        Returns:
            Dict[str, Any]: 領収書の情報
        """

        sql = self.database.read_sql("SELECT_RECEIPT_INFO", location=__file__)
        result = self.database.select(sql=sql, params={"RET_ID": receipt_id, "CRE_USER_ID": user_id})
        return result if result else []

    def select_receipt_details(self, receipt_id: str, user_id: str) -> list[Dict[str, Any]]:

        """
        領収書の詳細情報を取得

        Args:
            receipt_id(str): 領収書ID

        Returns:
            list[Dict[str, Any]]: 領収書の詳細情報
        """

        self.ensure_receipt_detail_tax_columns()
        sql = self.database.read_sql("SELECT_RECEIPT_DETAIL", location=__file__)
        result = self.database.select(sql=sql, params={"RET_ID": receipt_id, "CRE_USER_ID": user_id})
        return result

    def update_receipt_info(self, receipt_id: str,body: Dict[str, Any], user_id: str) -> None:
        """
        領収書の情報を更新する

        Args:
            body(Dict[str, Any]): 領収書の情報

        Returns:
            None: 戻り値なし。
        """

        receipt_info = body.get("receiptInfo")
        receipt_details = receipt_info.get("receiptDetails", [])
        # 時刻フォーマット変換　00:00 -> 000000
        if receipt_info.get("receiptTime"):
            receipt_info["receiptTime"]=datetime.strptime(receipt_info["receiptTime"], "%H:%M").strftime("%H%M%S")

        # 日付フォーマット変換 2026-01-01 -> 20260101
        if receipt_info.get("receiptDate"):
            receipt_info["receiptDate"] = datetime.strptime(receipt_info["receiptDate"], "%Y-%m-%d").strftime("%Y%m%d")


        receipt_info_data = {
            "UPD_PROG":"ReceiptUpdateDelete",
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "RET_ID": receipt_id,
            "INV_REG_NUM": receipt_info.get("invoiceRegistrationNumber"),
            "SUP_NAME": receipt_info.get("supplierName"),
            "RET_DT": receipt_info.get("receiptDate"),
            "RET_TM": receipt_info.get("receiptTime"),
            "TAX_FLAG": receipt_info.get("taxFlag"),
            "RET_DET_CNT": len(receipt_details),
            "TOA_PRICE": receipt_info.get("totalPrice"),
            "CRE_USER_ID": user_id,
            "UPD_USER_ID": user_id,
        }

        sql = self.database.read_sql("UPDATE_RECEIPT_INFO", location=__file__)
        self.database.update(sql, params=receipt_info_data)
        self.upsert_invoice_registration(receipt_info, user_id)

    def upsert_invoice_registration(self, receipt_info: Dict[str, Any], user_id: str) -> None:
        """
        upsert_invoice_registrationの処理を実行する。

        Args:
            receipt_info (Dict[str, Any]): receipt_infoの値。
            user_id (str): ユーザーID。

        Returns:
            None: 戻り値なし。
        """
        invoice_number = receipt_info.get("invoiceRegistrationNumber")
        if not invoice_number or str(invoice_number).upper().startswith("A"):
            return

        self.logo_storage.upload(invoice_number, receipt_info.get("supplierImage"))
        now_dt = datetime.now()
        params = {
            "CRE_PROG": "ReceiptUpdateDelete",
            "UPD_PROG": "ReceiptUpdateDelete",
            "INV_REG_NUM": invoice_number,
            "SUP_NAME": receipt_info.get("supplierName"),
            "TAX_FLAG": receipt_info.get("taxFlag"),
            "CRE_DT": now_dt.strftime("%Y%m%d"),
            "CRE_TM": now_dt.strftime("%H%M%S"),
            "UPD_DT": now_dt.strftime("%Y%m%d"),
            "UPD_TM": now_dt.strftime("%H%M%S"),
            "CRE_USER_ID": user_id,
            "UPD_USER_ID": user_id,
            "DEL_FLAG": 0,
        }

        update_sql = self.database.read_sql("UPDATE_INVOICE_REGISTRATION", location=__file__)
        updated_count = self.database.update(update_sql, params=params)
        if updated_count:
            return

        insert_sql = self.database.read_sql("INSERT_INVOICE_REGISTRATION", location=__file__)
        self.database.insert(insert_sql, params=params)

    def update_receipt_details(self,receipt_id: str , body: Dict[str, Any], user_id: str) -> None:
        """
        領収書の詳細情報を更新する

        Args:
            body(Dict[str, Any]): 領収書の情報

        Returns:
            None: 戻り値なし。
        """
        # 該当する領収書の詳細情報を削除(del_flag = 1)
        sql = self.database.read_sql("UPDATE_RECEIPT_DETAIL", location=__file__)
        params={
            "UPD_PROG":"ReceiptUpdateDelete",
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "UPD_USER_ID": user_id,
            "CRE_USER_ID": user_id,
            "RET_ID": receipt_id
        }
        self.database.update(sql, params=params)

        receipt_info = body.get("receiptInfo") or {}
        receipt_details = receipt_info.get("receiptDetails") or []
        tax_flag = receipt_info.get("taxFlag")
        self.ensure_receipt_detail_tax_columns()

        for detail in receipt_details:
            prices = enrich_detail_prices(detail, tax_flag)
            receipt_detail_data = {
                "UPD_PROG":"ReceiptUpdateDelete",
                "UPD_DT":datetime.now().strftime("%Y%m%d"),
                "UPD_TM":datetime.now().strftime("%H%M%S"),
                "CRE_PROG":"ReceiptUpdateDelete",
                "CRE_DT":datetime.now().strftime("%Y%m%d"),
                "CRE_TM":datetime.now().strftime("%H%M%S"),
                "RET_ID": receipt_id,
                "ITEM_NAME": detail.get("itemName"),
                "CAT1": detail.get("category1"),
                "CAT2": detail.get("category2"),
                "TAX_RATE": detail.get("taxRate",None),
                "QTY": detail.get("quantity"),
                "UT": detail.get("unit",None),
                "UT_PRE": prices.get("unitPrice"),
                "TO_PRE": prices.get("totalPrice"),
                "UT_TAX_EXCLUDED": prices.get("taxExcludedUnitPrice"),
                "TO_TAX_EXCLUDED": prices.get("taxExcludedTotalPrice"),
                "UT_TAX_INCLUDED": prices.get("taxIncludedUnitPrice"),
                "TO_TAX_INCLUDED": prices.get("taxIncludedTotalPrice"),
                "DEL_FLAG":0
                ,"CRE_USER_ID": user_id,
                "UPD_USER_ID": user_id,
            }
            sql = self.database.read_sql("INSERT_RECEIPT_DETAIL",
                                         location=__file__)
            self.database.insert(sql, params=receipt_detail_data)

    def ensure_receipt_detail_tax_columns(self) -> None:
        """
        ensure_receipt_detail_tax_columnsの処理を実行する。

        Args:
            None: 引数なし。

        Returns:
            None: 戻り値なし。
        """
        for column in ("UT_TAX_EXCLUDED", "TO_TAX_EXCLUDED", "UT_TAX_INCLUDED", "TO_TAX_INCLUDED"):
            self.database.execute(self.database.read_sql(f"ALTER_RECEIPT_DETAIL_{column}", location=__file__))

    def delete_receipt_info_and_details(self, receipt_id: str, user_id: str) -> None:
        """
        領収書の情報と詳細情報を削除する

        Args:
            receipt_id(str): 領収書ID

        Returns:
            None: 戻り値なし。
        """
        # 領収書の情報を削除
        sql = self.database.read_sql("DELETE_RECEIPT_INFO", location=__file__)

        params={
            "UPD_PROG":"ReceiptUpdateDelete",
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "CRE_USER_ID": user_id,
            "UPD_USER_ID": user_id,
            "RET_ID": receipt_id,
        }
        self.database.update(sql, params=params)
        # 領収書の詳細情報を削除
        sql = self.database.read_sql("DELETE_RECEIPT_DETAIL", location=__file__)
        self.database.update(sql, params=params)
