# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors


"""レシート情報の検索API。"""
from typing import Dict, Any, Optional
from src.common.base import BaseRestApi
from src.common.functions.response import response
from src.common.exception import Error
from datetime import datetime
from src.api.receipt.supplierLogoStorage import SupplierLogoStorage


class ReceiptReference(BaseRestApi):
    """日付・時刻・金額・分類条件でレシートを検索するAPIクラス。"""

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
        user_id = self.require_user_id(request_dict)


        # 時刻フォーマット変換 00:00 -> 0000
        if body.get("timeFrom",None):
            if len(body["timeFrom"])==5:
                body["timeFrom"]= datetime.strptime(body["timeFrom"], "%H:%M").strftime("%H%M%S")
        if body.get("timeTo",None):
            if len(body["timeTo"])==5:
                body["timeTo"]= datetime.strptime(body["timeTo"], "%H:%M").strftime("%H%M%S")

        # 日付フォーマット変換 2026-01-01 -> 20260101
        if body.get("dateFrom",None):
            if body["dateFrom"]:
                body["dateFrom"] = datetime.strptime(body["dateFrom"] , "%Y-%m-%d").strftime("%Y%m%d")
        if body.get("dateTo",None):
            if body["dateTo"]:
                body["dateTo"] = datetime.strptime( body["dateTo"], "%Y-%m-%d").strftime("%Y%m%d")

        # 検索条件はSQL片と命名パラメータへ分離して生成する。
        time_sql, time_params = self.adding_time_conditions(body=body)
        date_sql, date_params = self.adding_date_conditions(body=body)
        receipt_amount_sql, receipt_amount_params = self.adding_receipt_amount_conditions(body=body)
        detail_price_sql, detail_price_params = self.adding_detail_amount_conditions(body=body)
        category_sql, category_params = self.adding_category_conditions(body=body)
        inm_sql, inm_params = self.adding_address_and_inm_conditions(body=body)

        receipt_id = body.get("receiptId",None)

        receipt_params = {}
        for condition_params in [time_params, date_params, inm_params, receipt_amount_params]:
            receipt_params.update(condition_params)
        receipt_params["user_id"] = user_id

        receipt_result = self.select_receipt_info(
            receipt_id,
            time_sql,
            date_sql,
            inm_sql,
            receipt_amount_sql,
            receipt_params
        )

        receipt_id_list = [i.get("RET_ID") for i in receipt_result]

        detail_params = {}
        detail_params.update(detail_price_params)
        detail_params.update(category_params)
        detail_params["user_id"] = user_id

        details_result = self.select_receipt_details(
            receipt_id_list=receipt_id_list,
            detail_price_sql=detail_price_sql,
            category_sql=category_sql,
            params=detail_params
        )

        receipt_details = []

        detail_map = {}
        if details_result and receipt_result   :
            for d in details_result:
                rid = d.get("RET_ID") 
                if rid not in detail_map:
                    detail_map[rid] = []
                detail_map[rid].append(d)

            for r in receipt_result:
                rid = r.get("RET_ID")
                details = detail_map.get(rid, [])

                for d in details:
                    ret_dt = r.get("RET_DT")
                    ret_tm = r.get("RET_TM")
                    supplier_image = r.get("SUPPLIER_LOGO") or ""

                    if ret_dt and len(ret_dt)==8:
                        r["RET_DT"] = datetime.strptime(r["RET_DT"] , "%Y%m%d").strftime("%Y-%m-%d")
                    if ret_tm and len(ret_tm)==6:
                        r["RET_TM"] = datetime.strptime(r["RET_TM"] , "%H%M%S").strftime("%H:%M")
                    receipt_details.append({
                        "invoiceRegistrationNumber": r.get("INV_REG_NUM"),
                        "receiptId": r.get("RET_ID"),
                        "supplierName": r.get("SUP_NAME"),
                        "supplierImage": supplier_image,
                        "receiptDate": r.get("RET_DT"),
                        "receiptTime": r.get("RET_TM"),
                        "taxFlag": r.get("TAX_FLAG", ""),
                        "itemName": d.get("ITEM_NAME"),
                        "category1": d.get("CAT1"),
                        "category2": d.get("CAT2"),
                        "taxRate": d.get("TAX_RATE"),
                        "quantity": d.get("QTY"),
                        "unitPrice": d.get("UT_PRE"),
                        # レシート保存額と明細金額を混同しないよう、ヘッダ合計を別項目で返す。
                        "receiptTotalPrice": r.get("TOA_PRICE"),
                        "totalPrice": d.get("TO_PRE"),
                        "taxExcludedUnitPrice": d.get("UT_TAX_EXCLUDED"),
                        "taxExcludedTotalPrice": d.get("TO_TAX_EXCLUDED"),
                        "taxIncludedUnitPrice": d.get("UT_TAX_INCLUDED"),
                        "taxIncludedTotalPrice": d.get("TO_TAX_INCLUDED")
                    })

        return response(status_code=200,
                        body={"receiptDetails": receipt_details})

    def exception(self, e: Exception) -> dict:
        """
            例外処理を行う。

            Args:
                e(Exception): 発生した例外。

            Returns:
                dict: REST APIのレスポンスとしてエラーコードを返す。
            """
        return super().exception(e)

    def select_receipt_info(self, receipt_id, time_sql, date_sql, inm_sql, receipt_amount_sql, params) -> Dict[str, Any]:
        """ヘッダ条件に一致するレシート情報を取得する。"""
        sql = """
            SELECT DISTINCT
                re.RET_ID,
                re.INV_REG_NUM,
                re.SUP_NAME,
                re.RET_DT,
                re.RET_TM,
                re.TAX_FLAG,
                re.TOA_PRICE
            FROM receipt_info re
            WHERE re.DEL_FLAG = 0
              AND re.CRE_USER_ID = %(user_id)s
                """
        
        if receipt_id:
            sql += " AND re.RET_ID = %(receipt_id)s "
            params["receipt_id"] = receipt_id
        
        for i in [time_sql,date_sql,inm_sql,receipt_amount_sql]:
            if i is None:
                continue
            else:
                sql = sql+i

        sql = sql +"ORDER BY RET_ID DESC LIMIT 5000 ;"

        result = self.attach_supplier_images(self.database.select(sql=sql, params=params))
        return result if result else []

    def attach_supplier_images(self, rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """検索済みレシートへS3上の店舗ロゴURLを後付けする。"""
        logo_cache = {}
        for row in rows:
            invoice_number = row.get("INV_REG_NUM")
            if invoice_number not in logo_cache:
                logo_cache[invoice_number] = self.logo_storage.url_for(invoice_number)
            row["SUPPLIER_LOGO"] = logo_cache[invoice_number]
        
        return rows

    def select_receipt_details(self, receipt_id_list: list, detail_price_sql: str, category_sql: str, params) -> list[Dict[str, Any]]:
        """対象レシートIDに紐づく明細情報を検索条件付きで取得する。"""

        if not receipt_id_list:
            return []

        id_params = {f"receipt_id_{idx}": receipt_id for idx, receipt_id in enumerate(receipt_id_list)}
        params.update(id_params)
        placeholders = ",".join([f"%({f'receipt_id_{idx}'})s" for idx in range(len(receipt_id_list))])

        sql = f"""
        SELECT *
        FROM receipt_detail
        WHERE RET_ID IN ({placeholders}) 
        AND DEL_FLAG = 0
        AND CRE_USER_ID = %(user_id)s
        """

        if detail_price_sql is not None:
            sql = sql + str(detail_price_sql)
        if category_sql:
            sql = sql + str(category_sql)


        result = self.database.select(sql=sql, params=params)
        return result
    
    def adding_time_conditions(self, body) -> tuple[str, dict]:
        """
        時刻の条件のSQLを生成する
        """
        start_time = body.get("timeFrom",None)
        over_time = body.get("timeTo",None)
        params = {}
        if start_time is not None and over_time is not None :
            sql = "AND RET_TM BETWEEN %(time_from)s AND %(time_to)s "
            params["time_from"] = start_time
            params["time_to"] = over_time
        
        elif start_time is not None or over_time is not None:
            sql = "AND RET_TM = %(time_exact)s "
            params["time_exact"] = start_time if start_time is not None else over_time
        else:
            sql = ""

        return sql, params
    

    def adding_date_conditions(self, body) -> tuple[str, dict]:
        """
        日付の条件のSQLを生成する
        """
        start_date = body.get("dateFrom",None)
        over_date = body.get("dateTo",None)
        params = {}

        if start_date is not None  and over_date is not None :
            sql = "AND RET_DT BETWEEN %(date_from)s AND %(date_to)s "
            params["date_from"] = start_date
            params["date_to"] = over_date
        
        elif start_date is not None or over_date is not None:
            sql = "AND RET_DT = %(date_exact)s "
            params["date_exact"] = start_date if start_date is not None else over_date
        else:
            sql = ""

        return sql, params
    
        
    def adding_receipt_amount_conditions(self, body):
        """レシート合計金額の検索条件をSQL片へ変換する。"""

        def to_int(v):
            try:
                return int(v)
            except:
                return None

        min_amount = to_int(body.get("totalMin"))
        max_amount = to_int(body.get("totalMax"))
        params = {}

        if min_amount is not None and max_amount is not None:
            if min_amount > max_amount:
                min_amount, max_amount = max_amount, min_amount
            params["total_min"] = min_amount
            params["total_max"] = max_amount
            return "AND TOA_PRICE BETWEEN %(total_min)s AND %(total_max)s ", params

        if min_amount is not None:
            params["total_min"] = min_amount
            return "AND TOA_PRICE >= %(total_min)s ", params

        if max_amount is not None:
            params["total_max"] = max_amount
            return "AND TOA_PRICE <= %(total_max)s ", params

        return "", params
        
    def adding_detail_amount_conditions(self, body) -> tuple[str, dict]:
        """明細金額の検索条件をSQL片へ変換する。"""

        def to_int(v):
            try:
                return int(v)
            except:
                return None

        min_amount = to_int(body.get("priceMin"))
        max_amount = to_int(body.get("priceMax"))
        params = {}

        if min_amount is None and max_amount is None:
            return "", params

        if min_amount is not None and max_amount is not None:
            if min_amount > max_amount:
                min_amount, max_amount = max_amount, min_amount
            params["price_min"] = min_amount
            params["price_max"] = max_amount
            return "AND TO_PRE BETWEEN %(price_min)s AND %(price_max)s ", params

        if min_amount is not None:
            params["price_min"] = min_amount
            return "AND TO_PRE >= %(price_min)s ", params

        if max_amount is not None:
            params["price_max"] = max_amount
            return "AND TO_PRE <= %(price_max)s ", params

        return "", params
    

    def adding_category_conditions(self, body:dict) -> tuple[str, dict]:
        """大分類・小分類の検索条件をSQL片へ変換する。"""
        sql=""
        params = {}
        if body.get("category1"):
            sql += "AND CAT1 = %(category1)s "
            params["category1"] = body.get("category1")
        if body.get("category2"):
            sql += "AND CAT2 = %(category2)s "
            params["category2"] = body.get("category2")

        return sql, params

    def adding_address_and_inm_conditions(self, body:dict) -> tuple[str, dict]:
        """店舗名とインボイス登録番号の検索条件をSQL片へ変換する。"""
        sql = ""
        params = {}
        if body.get("invoiceRegistrationNumber"):
            sql += "AND re.INV_REG_NUM = %(invoice_registration_number)s "
            params["invoice_registration_number"] = body.get("invoiceRegistrationNumber")

        if body.get("supplierName"):
            sql += "AND re.SUP_NAME = %(supplier_name)s "
            params["supplier_name"] = body.get("supplierName")

        
        return sql, params
