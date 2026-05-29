# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""レシート情報の新規登録API。"""
import secrets
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error
from src.common.auth_context import get_current_user_id
from datetime import datetime
from src.api.receipt.supplierLogoStorage import SupplierLogoStorage
from src.api.receipt.taxPrice import enrich_detail_prices


class NewReceiptRegistration(BaseRestApi):
    """レシートヘッダ、明細、取引先マスタを登録するAPIクラス。"""

    def __init__(self ,db_path: Optional[str] = None):
        """
            レシート新規登録APIを初期化する。

            Args:
                db_path(Optional[str]): 旧ローカル実行互換のための未使用引数。
        """
        super().__init__(class_name=self.__class__.__name__,db_path = db_path or None)
        self._validate_body_functions = {}
        self.logo_storage = SupplierLogoStorage()

    def validate_headers(self, request_dict):
        """
            リクエストヘッダーの共通バリデーションを行う。

            Args:
                request_dict(dict): BaseRestApiから渡されるリクエストコンテキスト。

            Returns:
                dict: バリデーション後のリクエストコンテキスト。
        """

        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        """
            リクエスト本文の共通バリデーションを行う。

            Args:
                request_dict(dict): BaseRestApiから渡されるリクエストコンテキスト。

            Returns:
                dict: バリデーション後のリクエストコンテキスト。
        """
        # 既存のBaseRestApiバリデーションフローへ委譲する。
        return super().validate_body(request_dict)

    def main(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        
        """
        Args:
            request_dict (Dict[str, Any]): 正規化済みのリクエストコンテキスト。

        Returns:
            Dict[str, Any]: 標準化されたAPIレスポンス。
        """
        self.logger.info(f"リクエストボディ: {request_dict.get('body')}")
        body = request_dict.get("body", {})
        receipt_info = body.get("receiptInfo", {})
        if not body:
            raise Error(status_code=510,
                        error_code="1000062",
                        message="リクエストのボディが空です。")

        detail_count = receipt_info.get("receiptDetailCount")
        receipt_details = receipt_info.get("receiptDetails", [])
        if detail_count:
            if int(detail_count) != len(receipt_details):
                raise Error(
                    status_code=510,
                    error_code="1000062",
                    message="receiptDetailCountとreceiptDetailsの数が一致しません。")
        receipt_id = self.create_receipt_id(receipt_info=receipt_info)
        invoice_number = self.normalize_or_create_receipt_number(receipt_info.get("invoiceRegistrationNumber"))
        receipt_info["invoiceRegistrationNumber"] = invoice_number
        self.logo_storage.upload(invoice_number, receipt_info.get("supplierImage"))
        select_response = self.select_invoice_registration(
            inv_reg_num=invoice_number)
        if not select_response:
            self.insert_invoice_registration(body=receipt_info)

        self.insert_receipt_info(receipt_id=receipt_id,
                                 receipt_info=receipt_info)
        self.insert_receipt_details(receipt_id=receipt_id,
                                    receipt_details=receipt_details,
                                    tax_flag=receipt_info.get("taxFlag"))

        api_response = {
            "message": "領収書の情報が正常に登録されました。",
            "receiptId": receipt_id
        }

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

    def insert_receipt_info(self, receipt_id: str, receipt_info: Dict[str,
                                                                      Any]):
        """
            領収書の情報をデータベースに挿入する。

            Args:
                receipt_id(str): 領収書のID。
                receipt_info(Dict[str, Any]): 領収書の情報を含む辞書。
        """
        # 時刻フォーマット変換　00:00 -> 000000
        if receipt_info.get("receiptTime"):
            receipt_info["receiptTime"]=datetime.strptime(receipt_info["receiptTime"], "%H:%M").strftime("%H%M%S")

        # 日付フォーマット変換 2026-01-01 -> 20260101
        if receipt_info.get("receiptDate"):
            receipt_info["receiptDate"] = datetime.strptime(receipt_info["receiptDate"], "%Y-%m-%d").strftime("%Y%m%d")

        receipt_info_data = {
            "CRE_PROG":"NewReceiptRegistration",
            "UPD_PROG":"NewReceiptRegistration",
            "RET_ID": receipt_id,
            "INV_REG_NUM": receipt_info.get("invoiceRegistrationNumber"),
            "SUP_NAME": receipt_info.get("supplierName"),
            "RET_DT": receipt_info.get("receiptDate"),
            "RET_TM": receipt_info.get("receiptTime"),
            "TAX_FLAG": receipt_info.get("taxFlag"),
            "RET_DET_CNT": receipt_info.get("receiptDetailCount"),
            "TOA_PRICE": receipt_info.get("totalPrice"),
            "CRE_DT":datetime.now().strftime("%Y%m%d"),
            "CRE_TM":datetime.now().strftime("%H%M%S"),
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
        }
        sql = self.database.read_sql("INSERT_RECEIPT_INFO", location=__file__)
        self.database.insert(sql, params=receipt_info_data)

    def insert_receipt_details(self, receipt_id: str, receipt_details: list, tax_flag=None):
        """
            領収書の詳細情報をデータベースに挿入する。

            Args:
                receipt_id(str): 領収書のID。
                receipt_details(list): 領収書の詳細情報を含む辞書のリスト。
        """
        self.ensure_receipt_detail_tax_columns()
        for detail in receipt_details:
            prices = enrich_detail_prices(detail, tax_flag)
            receipt_detail_data = {
                "CRE_PROG":"NewReceiptRegistration",
                "UPD_PROG":"NewReceiptRegistration",
                "RET_ID": receipt_id,
                "ITEM_NAME": detail.get("itemName"),
                "CAT1": detail.get("category1"),
                "CAT2": detail.get("category2"),
                "TAX_RATE": detail.get("taxRate"),
                "QTY": detail.get("quantity"),
                "UT": detail.get("unit"),
                "UT_PRE": prices.get("unitPrice"),
                "TO_PRE": prices.get("totalPrice"),
                "UT_TAX_EXCLUDED": prices.get("taxExcludedUnitPrice"),
                "TO_TAX_EXCLUDED": prices.get("taxExcludedTotalPrice"),
                "UT_TAX_INCLUDED": prices.get("taxIncludedUnitPrice"),
                "TO_TAX_INCLUDED": prices.get("taxIncludedTotalPrice"),
                "CRE_DT":datetime.now().strftime("%Y%m%d"),
                "CRE_TM":datetime.now().strftime("%H%M%S"),
                "UPD_DT":datetime.now().strftime("%Y%m%d"),
                "UPD_TM":datetime.now().strftime("%H%M%S"),
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

    def create_receipt_id(self, receipt_info: Dict[str, Any]) -> str:
        """
            領収書のIDを生成する。

            Args:
                receipt_info(Dict[str, Any]): 領収書の情報を含む辞書。

            Returns:
                str: 生成された領収書のID。
        """
        #DBの最大receiptIDを取得
        now_date = datetime.now().strftime("%Y%m%d")
        user_fragment = self.receipt_user_fragment()
        receipt_id_prefix = f"{now_date}-{user_fragment}"
        max_receipt_id = None
        self.logger.info(f"現在の日付: {now_date}")
        sql = self.database.read_sql("SELECT_MAX_RECEIPT_ID",
                                     location=__file__)
        response = (self.database.select(
            sql, params={"receipt_id_date": f"{receipt_id_prefix}%"}))
        if response:
            max_receipt_id = response[0].get("receipt_id") if response else None
        if max_receipt_id:
            self.logger.info(f"最大の領収書ID: {max_receipt_id}")
            #最大receiptIDの末尾の数字をインクリメント
            new_receipt_id = int(max_receipt_id[-4:]) + 1
            receipt_id = f"{receipt_id_prefix}-{new_receipt_id:04d}"
        else:
            #当日初のreceiptIDを生成
            receipt_id = f"{receipt_id_prefix}-0001"
        return receipt_id

    def receipt_user_fragment(self) -> str:
        """
            領収書IDに含めるユーザー識別用の短い文字列を生成する。

            Returns:
                str: ユーザーIDから作成した8文字以内の識別文字列。
        """
        user_id = get_current_user_id() or "__anonymous__"
        cleaned = "".join(char.lower() for char in user_id if char.isalnum())
        return (cleaned or "anon")[:8]

    def insert_invoice_registration(self, body: Dict[str, Any]) -> None:
        """
        登録者情報をデータベースに挿入するメソッド

        Args:
            body (Dict[str, Any]): 登録者情報を含む辞書
        """
        invoice_number = body.get("invoiceRegistrationNumber")
        if not invoice_number or str(invoice_number).upper().startswith("A"):
            return

        param = {
            "CRE_PROG":"NewReceiptRegistration",
            "UPD_PROG":"NewReceiptRegistration",
            "INV_REG_NUM": invoice_number,
            "SUP_NAME": body.get("supplierName"),
            "TAX_FLAG": body.get("taxFlag"),
            "CRE_DT":datetime.now().strftime("%Y%m%d"),
            "CRE_TM":datetime.now().strftime("%H%M%S"),
            "UPD_DT":datetime.now().strftime("%Y%m%d"),
            "UPD_TM":datetime.now().strftime("%H%M%S"),
            "DEL_FLAG": 0
        }

        sql = self.database.read_sql("INSERT_INV_NUM", location=__file__)

        try:
            self.database.insert(sql, params=param)

        except Exception as e:
            # 同時登録時の重複挿入を許容する。
            if "UNIQUE" in str(e):
                self.logger.warning("登録者番号はすでに登録されています。")
            else:
                raise e

            
    def select_invoice_registration(self, inv_reg_num: str) -> Dict[str, Any]:
        """
            インボイス登録番号に一致する取引先マスタを取得する。

            Args:
                inv_reg_num(str): 検索対象のインボイス登録番号。

            Returns:
                Dict[str, Any]: 取引先マスタ。存在しない場合はNone。
        """
        if not inv_reg_num or str(inv_reg_num).upper().startswith("A"):
            return None
        sql = self.database.read_sql("SELECT_INV_REG_NUM", location=__file__)
        result = self.database.select(sql, params={"INV_REG_NUM": inv_reg_num})
        return result[0] if result else None

    def normalize_or_create_receipt_number(self, value: str) -> str:
        """空欄なら A + 13桁のシステム番号を重複しない形で発行する。"""
        raw = str(value or "").strip().upper()
        if raw.startswith("A") and len(raw) == 14 and raw[1:].isdigit():
            return raw
        if raw.startswith("T") and len(raw) == 14 and raw[1:].isdigit():
            return raw
        if raw.isdigit() and len(raw) == 13:
            return f"T{raw}"

        for _ in range(20):
            candidate = f"A{secrets.randbelow(10 ** 13):013d}"
            rows = self.database.select(
                """
                SELECT RET_ID
                FROM receipt_info
                WHERE INV_REG_NUM = %(INV_REG_NUM)s
                  AND DEL_FLAG = 0
                LIMIT 1
                """,
                {"INV_REG_NUM": candidate},
            )
            if not rows:
                return candidate
        raise Error(status_code=500, error_code="1000062", message="システム番号を発行できませんでした。")
