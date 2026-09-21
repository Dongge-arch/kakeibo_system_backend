# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""
レシート情報の新規登録API。
"""
import secrets
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error
from src.common.auth_context import get_current_user_id
from datetime import datetime
from src.api.kakeibo.receipt.supplierLogoStorage import SupplierLogoStorage
from src.api.kakeibo.receipt.taxPrice import enrich_detail_prices
from src.api.kakeibo.receipt.receiptValidation import validate_receipt_for_save

from psycopg import IntegrityError


class NewReceiptRegistration(BaseRestApi):
    """
    レシートヘッダ、明細、取引先マスタを登録するAPIクラス。
    """

    def __init__(self ,db_path: Optional[str] = None):
        """
        レシート新規登録APIを初期化する。

        Args:
            db_path(Optional[str]): 旧ローカル実行互換のための未使用引数。

        Returns:
            None: 戻り値なし。
        """
        # 旧ローカル実行互換のための未使用引数を受け取る。
        super().__init__(class_name=self.__class__.__name__,db_path = db_path or None)
        self._validate_body_functions = {}
        self.logo_storage = SupplierLogoStorage()

    def validate_headers(self, request_dict):
        """
            リクエストヘッダーの共通バリデーションを行う。

            Args:
                request_dict(dict): BaseRestApiから渡されるリクエストヘッダー。

            Returns:
                dict: バリデーション後のリクエストヘッダー。
        """

        return super().validate_headers(request_dict)

    def validate_body(self, request_dict):
        """
            リクエスト本文の共通バリデーションを行う。

            Args:
                request_dict(dict): BaseRestApiから渡されるリクエストボディ。

            Returns:
                dict: バリデーション後のリクエストボディ。
        """
        # 既存のBaseRestApiバリデーションフローへ委譲する。
        return super().validate_body(request_dict)

    def main(self, request_dict: Dict[str, Any]) -> Dict[str, Any]:
        
        """
        処理概要: 小票を新規登録する。
        処理内容:
          1. 認証済みユーザーと小票情報を取得する。
          2. 明細と重複を検証する。
          3. 小票IDと登録番号を確定する。
          4. 小票本体と明細を保存する。
          5. 登録結果を返す。

        Args:
            request_dict (Dict[str, Any]): 正規化済みのリクエストコンテキスト。

        Returns:
            Dict[str, Any]: 標準化されたAPIレスポンス。
        """
        # ボディ、ユーザーID、レシート情報を取得する。
        body = request_dict.get("body", {})
        user_id = self.require_user_id(request_dict)
        receipt_info = body.get("receiptInfo", {})

        # ボディが存在しない場合はえラーを返す。
        if not body or not receipt_info:
            raise Error(status_code=510,
                        error_code="1000062",
                        message="リクエストのボディが空です。")

        # 2026-06-28 Codex: AI解析や画面入力から空明細・0円明細が正式登録されるのを防ぐ。
        validate_receipt_for_save(receipt_info)

        detail_count = receipt_info.get("receiptDetailCount")
        receipt_details = receipt_info.get("receiptDetails", [])
        if detail_count:
            if int(detail_count) != len(receipt_details):
                raise Error(
                    status_code=510,
                    error_code="1000062",
                    message="receiptDetailCountとreceiptDetailsの数が一致しません。")

        # 同一店舗、日付、時刻、合計金額のレシートが登録済みか確認する。 
        self.raise_if_duplicate_receipt(receipt_info=receipt_info, user_id=user_id)

        # レシートIDを生成する。
        receipt_id = self.create_receipt_id(user_id=user_id)

        # インボイス登録番号を正規化または新規発行する。
        invoice_number = self.normalize_or_create_receipt_number(receipt_info.get("invoiceRegistrationNumber", ""), user_id)

        # インボイス番号が空欄の場合は、システム番号を発行して登録する。
        receipt_info["invoiceRegistrationNumber"] = invoice_number

        # 取引先ロゴをアップロードする。
        self.logo_storage.upload(invoice_number, receipt_info.get("supplierImage"))

        # 取引先マスタに登録されていない場合は、取引先マスタに登録する。
        select_response = self.select_invoice_registration(
            inv_reg_num=invoice_number, user_id=user_id)
        if not select_response:
            self.insert_invoice_registration(body=receipt_info, user_id=user_id)

        # レシート情報と明細情報をデータベースに挿入する。
        self.insert_receipt_info(receipt_id=receipt_id,
                                 receipt_info=receipt_info,
                                 user_id=user_id)
        self.insert_receipt_details(receipt_id=receipt_id,
                                    receipt_details=receipt_details,
                                    tax_flag=receipt_info.get("taxFlag"),
                                    user_id=user_id)
        # レスポンスを返す。
        api_response = {
            "message": "領収書の情報が正常に登録されました。",
            "receiptId": receipt_id
        }

        return response(status_code=201, body=api_response)

    def raise_if_duplicate_receipt(self, receipt_info: Dict[str, Any], user_id: str) -> None:
        """
        同一店舗、日付、時刻、合計金額のレシートが登録済みか確認する。

        Args:
            receipt_info(Dict[str, Any]): 登録対象のレシート情報。
            user_id(str): ユーザーID。

        Returns:
            None: 戻り値なし。

        Raises:
            Error: 同一条件のレシートがすでに登録されている場合。
        """
        receipt_date = datetime.strptime(receipt_info.get("receiptDate"), "%Y-%m-%d").strftime("%Y%m%d") if "-" in receipt_info.get("receiptDate") else receipt_info.get("receiptDate")

        receipt_time = datetime.strptime(receipt_info.get("receiptTime"), "%H:%M").strftime("%H%M%S") if ":" in receipt_info.get("receiptTime") else receipt_info.get("receiptTime")

        params = {
            "SUP_NAME": receipt_info.get("supplierName"), # 取引先名
            "RET_DT": receipt_date, # 領収書日付
            "RET_TM": receipt_time, # 領収書時刻
            "TOA_PRICE": receipt_info.get("totalPrice"), # 領収書合計金額
            "USER_ID": user_id, # ユーザーID
        }
        sql = self.database.read_sql("SELECT_DUPLICATE_RECEIPT", location=__file__)
        if self.database.select(sql, params=params):
            raise Error(
                status_code=409,
                error_code="1000062",
                message="このレシートはすでに登録されています。",
            )

    def exception(self, e: Exception) -> dict:
        """
            例外処理を行う。

            Args:
                e(Exception): 発生した例外。

            Returns:
                dict: REST APIのレスポンスとしてエラーコードを返す。
            """
        return super().exception(e)

    def insert_receipt_info(self, receipt_id: str, receipt_info: Dict[str, Any], user_id: str):
        """
        領収書の情報をデータベースに挿入する。

        Args:
            receipt_id(str): 領収書のID。
            receipt_info(Dict[str, Any]): 領収書の情報を含む辞書。
            user_id(str): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        # 時刻フォーマット変換　00:00 -> 000000
        if receipt_info.get("receiptTime"):
            receipt_info["receiptTime"]=datetime.strptime(receipt_info["receiptTime"], "%H:%M").strftime("%H%M%S")

        # 日付フォーマット変換 2026-01-01 -> 20260101
        if receipt_info.get("receiptDate"):
            receipt_info["receiptDate"] = datetime.strptime(receipt_info["receiptDate"], "%Y-%m-%d").strftime("%Y%m%d")

        receipt_info_data = {
            "CRE_PROG":"NewReceiptRegistration", # 登録プログラム名
            "UPD_PROG":"NewReceiptRegistration", # 更新プログラム名
            "RET_ID": receipt_id, # 領収書ID
            "INV_REG_NUM": receipt_info.get("invoiceRegistrationNumber"), # インボイス登録番号
            "SUP_NAME": receipt_info.get("supplierName"), # 取引先名
            "RET_DT": receipt_info.get("receiptDate"), # 領収書日付
            "RET_TM": receipt_info.get("receiptTime"), # 領収書時刻
            "TAX_FLAG": receipt_info.get("taxFlag"), # 税区分
            "RET_DET_CNT": receipt_info.get("receiptDetailCount"), # 領収書明細件数
            "TOA_PRICE": receipt_info.get("totalPrice"), # 領収書合計金額
            "CRE_DT":datetime.now().strftime("%Y%m%d"), # 登録日
            "CRE_TM":datetime.now().strftime("%H%M%S"), # 登録時刻
            "UPD_DT":datetime.now().strftime("%Y%m%d"), # 更新日
            "UPD_TM":datetime.now().strftime("%H%M%S"), # 更新時刻
            "USER_ID": user_id, # ユーザーID
        }
        sql = self.database.read_sql("INSERT_RECEIPT_INFO", location=__file__)
        self.database.insert(sql, params=receipt_info_data)

    def insert_receipt_details(self, receipt_id: str, receipt_details: list, tax_flag=None, user_id: str = ""):
        """
        領収書の詳細情報をデータベースに挿入する。

        Args:
            receipt_id(str): 領収書のID。
            receipt_details(list): 領収書の詳細情報を含む辞書のリスト。

        Returns:
            Any: 処理結果。
        """
        for detail in receipt_details:
            prices = enrich_detail_prices(detail, tax_flag)
            receipt_detail_data = {
                "CRE_PROG":"NewReceiptRegistration", # 登録プログラム名
                "UPD_PROG":"NewReceiptRegistration", # 更新プログラム名
                "RET_ID": receipt_id, # 領収書ID
                "ITEM_NAME": detail.get("itemName"), # 項目名
                "CAT1": detail.get("category1"), # 大分類
                "CAT2": detail.get("category2"), # 小分類
                "TAX_RATE": detail.get("taxRate"), # 税率
                "QTY": detail.get("quantity"), # 数量
                "UT": detail.get("unit"), # 単位
                "UT_PRE": prices.get("unitPrice"), # 単価
                "TO_PRE": prices.get("totalPrice"), # 合計金額
                "UT_TAX_EXCLUDED": prices.get("taxExcludedUnitPrice"), # 税抜単価
                "TO_TAX_EXCLUDED": prices.get("taxExcludedTotalPrice"), # 税抜合計
                "UT_TAX_INCLUDED": prices.get("taxIncludedUnitPrice"), # 税込単価
                "TO_TAX_INCLUDED": prices.get("taxIncludedTotalPrice"), # 税込合計
                "CRE_DT":datetime.now().strftime("%Y%m%d"), # 登録日
                "CRE_TM":datetime.now().strftime("%H%M%S"), # 登録時刻
                "UPD_DT":datetime.now().strftime("%Y%m%d"), # 更新日
                "UPD_TM":datetime.now().strftime("%H%M%S"), # 更新時刻
                "USER_ID": user_id, # ユーザーID
            }

            self.database.insert(self.database.read_sql("INSERT_RECEIPT_DETAIL",
                                         location=__file__), params=receipt_detail_data)



    def create_receipt_id(self, user_id: str) -> str:
        """
            領収書のIDを生成する。

            Args:
                user_id(str): ユーザーID。

            Returns:
                str: 生成された領収書のID。
        """
        #DBの最大receiptIDを取得
        now_date = datetime.now().strftime("%Y%m%d")
        
        # ユーザーIDから8文字以内の識別文字列を生成
        user_id = get_current_user_id() or "__anonymous__"
        cleaned = "".join(char.lower() for char in user_id if char.isalnum())
        user_fragment = (cleaned or "anon")[:8]

        # 生成された領収書IDのプレフィックスを作成
        receipt_id_prefix = f"{now_date}-{user_fragment}"
        max_receipt_id = None
        self.logger.info(f"現在の日付: {now_date}")

        # ユーザーIDの識別文字列: {user_fragment}")
        sql = self.database.read_sql("SELECT_MAX_RECEIPT_ID",
                                     location=__file__)
        self.logger.info(f"ユーザーIDの識別文字列: {user_fragment}")

        # 同一ユーザーの同一日付の最大receiptIDを取得する。
        max_receipt_response = (self.database.select(
            sql, params={"RET_ID": f"{receipt_id_prefix}%", "CRE_USER_ID": user_id}))
        if max_receipt_response:
            max_receipt_id = max_receipt_response[0].get("receipt_id") if max_receipt_response else None
        if max_receipt_id:
            self.logger.info(f"最大の領収書ID: {max_receipt_id}")
            #最大receiptIDの末尾の数字をインクリメント
            new_receipt_id = int(max_receipt_id[-4:]) + 1
            receipt_id = f"{receipt_id_prefix}-{new_receipt_id:04d}"
        else:
            #当日初のreceiptIDを生成
            receipt_id = f"{receipt_id_prefix}-0001"
        return receipt_id


    def insert_invoice_registration(self, body: Dict[str, Any], user_id: str) -> None:
        """
        登録者情報をデータベースに挿入するメソッド

        Args:
            body (Dict[str, Any]): 登録者情報を含む辞書
            user_id (str): ユーザーID

        Returns:
            None: 戻り値なし。
        """
        # インボイス登録番号が空欄または"A"で始まる場合は登録しない。
        invoice_number = body.get("invoiceRegistrationNumber")
        if not invoice_number or str(invoice_number).upper().startswith("A"):
            return

        param = {
            "CRE_PROG":"NewReceiptRegistration", # 登録プログラム名
            "UPD_PROG":"NewReceiptRegistration", # 更新プログラム名
            "INV_REG_NUM": invoice_number, # インボイス登録番号
            "SUP_NAME": body.get("supplierName"), # 取引先名
            "TAX_FLAG": body.get("taxFlag"), # 税区分
            "CRE_DT":datetime.now().strftime("%Y%m%d"), # 登録日
            "CRE_TM":datetime.now().strftime("%H%M%S"), # 登録時刻
            "UPD_DT":datetime.now().strftime("%Y%m%d"), # 更新日
            "UPD_TM":datetime.now().strftime("%H%M%S"), # 更新時刻
            "USER_ID": user_id, # ユーザーID
            "DEL_FLAG": 0 # 抹消フラグ
        }

        sql = self.database.read_sql("INSERT_INV_NUM", location=__file__)

        try:
            self.database.insert(sql, params=param)

        except IntegrityError as e:
            # 同時登録時の重複挿入を許容する。
            if "UNIQUE" in str(e):
                self.logger.warning("登録者番号はすでに登録されています。")
            else:
                raise e

            
    def select_invoice_registration(self, inv_reg_num: str , user_id: str) -> Dict[str, Any]:
        """
            インボイス登録番号に一致する取引先マスタを取得する。

            Args:
                inv_reg_num(str): 検索対象のインボイス登録番号。
                user_id(str): ユーザーID。

            Returns:
                Dict[str, Any]: 取引先マスタ。存在しない場合はNone。
        """
        if not inv_reg_num or str(inv_reg_num).upper().startswith("A"):
            return None
        
        result = self.database.select(self.database.read_sql("SELECT_INV_REG_NUM", location=__file__), params={"INV_REG_NUM": inv_reg_num, "USER_ID": user_id})
        return result[0] if result else None

    def normalize_or_create_receipt_number(self, value: str, user_id: str) -> str:
        """
        空欄なら A + 13桁のシステム番号を重複しない形で発行する。

        Args:
            value (str): valueの値。
            user_id (str): ユーザーID。

        Returns:
            str: 処理結果。
        """
        raw = str(value or "").strip().upper()
        if raw.startswith("A") and len(raw) == 14 and raw[1:].isdigit():
            return raw
        if raw.startswith("T") and len(raw) == 14 and raw[1:].isdigit():
            return raw
        # 2026-07-15 Codex: 実店舗のインボイス番号を持たない自動連携元は、画面で識別できる固定番号として保存する。
        if raw in ("SUICA", "AMAZON"):
            return raw
        if raw.isdigit() and len(raw) == 13:
            return f"T{raw}"   

        # 空欄または不正な値の場合は、A + 13桁のシステム番号を重複しない形で発行する。
        for _ in range(20):
            candidate = f"A{secrets.randbelow(10 ** 13):013d}"
            params={
                "INV_REG_NUM": candidate, 
                "USER_ID": user_id
                }
            rows = self.database.select(self.database.read_sql("SELECT_RECEIPT_INFO_FOR_GET_RECEIPT_NUM", location=__file__),params)
            if not rows:
                return candidate

        # 20回試行しても重複しない番号が発行できなかった場合は、エラーを返す。
        raise Error(status_code=500, error_code="1000062", message="システム番号を発行できませんでした。")
