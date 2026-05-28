# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""レシート情報の更新・削除API。"""
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error
from datetime import datetime
from src.api.receipt.supplierLogoStorage import SupplierLogoStorage
from src.api.receipt.taxPrice import enrich_detail_prices


class ReceiptUpdateDelete(BaseRestApi):
    """レシートヘッダと明細の更新・論理削除を扱うAPIクラス。"""

    def __init__(self ,db_path: Optional[str] = None):
        super().__init__(class_name=self.__class__.__name__,db_path = db_path or None)
        self._validate_body_functions = {}
        self.logo_storage = SupplierLogoStorage()

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


        body = request_dict.get("body", {})
        
        if body.get("updateDeleteType") == "update":
            receipt_id = body.get("receiptInfo").get("receiptId")
            self.update_receipt_info(receipt_id=receipt_id,body=body)
            self.update_receipt_details(receipt_id=receipt_id,body=body)
            return response(status_code=200,
                            body={"message": "領収書の情報が正常に更新されました。"})
        else:
            receipt_id = body.get("receiptId")
            self.delete_receipt_info_and_details(receipt_id=receipt_id)
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

    def select_receipt_info(self, receipt_id: str) -> Dict[str, Any]:
        """
        領収書の情報を取得

        Args:
            receipt_id(str): 領収書ID

        Returns:
            Dict[str, Any]: 領収書の情報
        """

        sql = """
                SELECT RET_ID, INV_REG_NUM, SUP_NAME, RET_DT, RET_TM, RET_DET_CNT, TOA_PRICE
                FROM receipt_info
                WHERE RET_ID = :receipt_id
                """
        
        result = self.database.select(sql=sql,params={"receipt_id" :receipt_id})
        return result if result else []

    def select_receipt_details(self, receipt_id: str) -> list[Dict[str, Any]]:

        """
        領収書の詳細情報を取得

        Args:
            receipt_id(str): 領収書ID

        Returns:
            list[Dict[str, Any]]: 領収書の詳細情報
        """

        self.ensure_receipt_detail_tax_columns()
        sql = f"""
        SELECT RET_ID, ITEM_NAME, CAT1, CAT2, TAX_RATE, QTY, UT, UT_PRE, TO_PRE,
               UT_TAX_EXCLUDED, TO_TAX_EXCLUDED, UT_TAX_INCLUDED, TO_TAX_INCLUDED
        FROM receipt_detail
        WHERE RET_ID = :receipt_id
        AND DEL_FLAG = 0
        """

        result = self.database.select(sql=sql,params={"receipt_id":receipt_id})
        return result

    def update_receipt_info(self, receipt_id: str,body: Dict[str, Any]) -> None:
        """
        領収書の情報を更新する

        Args:
            body(Dict[str, Any]): 領収書の情報
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
        }

        sql = self.database.read_sql("UPDATE_RECEIPT_INFO", location=__file__)
        self.database.update(sql, params=receipt_info_data)
        self.upsert_invoice_registration(receipt_info)

    def upsert_invoice_registration(self, receipt_info: Dict[str, Any]) -> None:
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
            "IMG": "",
            "TAX_FLAG": receipt_info.get("taxFlag"),
            "CRE_DT": now_dt.strftime("%Y%m%d"),
            "CRE_TM": now_dt.strftime("%H%M%S"),
            "UPD_DT": now_dt.strftime("%Y%m%d"),
            "UPD_TM": now_dt.strftime("%H%M%S"),
            "DEL_FLAG": 0,
        }

        update_sql = """
        UPDATE invoice_registration
        SET
            UPD_PROG = :UPD_PROG,
            UPD_DT = :UPD_DT,
            UPD_TM = :UPD_TM,
            SUP_NAME = COALESCE(:SUP_NAME, SUP_NAME),
            IMG = '',
            TAX_FLAG = COALESCE(:TAX_FLAG, TAX_FLAG)
        WHERE INV_REG_NUM = :INV_REG_NUM
          AND DEL_FLAG = 0
        """
        updated_count = self.database.update(update_sql, params=params)
        if updated_count:
            return

        insert_sql = """
        INSERT INTO invoice_registration (
            CRE_PROG,
            UPD_PROG,
            INV_REG_NUM,
            SUP_NAME,
            IMG,
            TAX_FLAG,
            CRE_DT,
            CRE_TM,
            UPD_DT,
            UPD_TM,
            DEL_FLAG
        ) VALUES (
            :CRE_PROG,
            :UPD_PROG,
            :INV_REG_NUM,
            :SUP_NAME,
            :IMG,
            :TAX_FLAG,
            :CRE_DT,
            :CRE_TM,
            :UPD_DT,
            :UPD_TM,
            :DEL_FLAG
        )
        """
        self.database.insert(insert_sql, params=params)

    def update_receipt_details(self,receipt_id: str , body: Dict[str, Any]) -> None:
        """
        領収書の詳細情報を更新する

        Args:
            body(Dict[str, Any]): 領収書の情報
        """
        # 該当する領収書の詳細情報を削除(del_flag = 1)
        sql = self.database.read_sql("UPDATE_RECEIPT_DETAIL", location=__file__)
        params={
            "UPD_PROG":"ReceiptUpdateDelete",
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "receipt_id" :receipt_id
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
            }
            sql = self.database.read_sql("INSERT_RECEIPT_DETAIL",
                                         location=__file__)
            self.database.insert(sql, params=receipt_detail_data)

    def ensure_receipt_detail_tax_columns(self) -> None:
        for sql in (
            "ALTER TABLE receipt_detail ADD COLUMN IF NOT EXISTS UT_TAX_EXCLUDED DOUBLE PRECISION",
            "ALTER TABLE receipt_detail ADD COLUMN IF NOT EXISTS TO_TAX_EXCLUDED DOUBLE PRECISION",
            "ALTER TABLE receipt_detail ADD COLUMN IF NOT EXISTS UT_TAX_INCLUDED DOUBLE PRECISION",
            "ALTER TABLE receipt_detail ADD COLUMN IF NOT EXISTS TO_TAX_INCLUDED DOUBLE PRECISION",
        ):
            self.database.execute(sql)

    def delete_receipt_info_and_details(self, receipt_id: str) -> None:
        """
        領収書の情報と詳細情報を削除する

        Args:
            receipt_id(str): 領収書ID
        """
        # 領収書の情報を削除
        sql = """
        UPDATE receipt_info
        SET 
        UPD_PROG = :UPD_PROG,
        UPD_DT = :UPD_DT,
        UPD_TM = :UPD_TM,
        del_flag = 1    
        WHERE RET_ID = :receipt_id
        AND del_flag = 0;
        """

        params={
            "UPD_PROG":"ReceiptUpdateDelete",
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "receipt_id" :receipt_id
        }
        self.database.update(sql, params=params)
        # 領収書の詳細情報を削除
        sql = """
        UPDATE receipt_detail
                SET del_flag = 1,
                UPD_PROG = :UPD_PROG,
                UPD_DT = :UPD_DT,
                UPD_TM = :UPD_TM
                WHERE RET_ID = :receipt_id
                AND del_flag = 0;
                """
        self.database.update(sql, params=params)
