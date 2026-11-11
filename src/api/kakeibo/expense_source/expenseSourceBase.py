# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""出費源取引の保存、候補算出、レシート照合を共通化する。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import hashlib
import json
import re
import unicodedata

from src.common.api_utils import now_ymd_hms
from src.common.base import BaseRestApi
from src.common.exception.error import Error


class ExpenseSourceBase(BaseRestApi):
    """出費源機能のDB操作と照合ロジックを提供する。"""

    _schema_ready = False
    AUTO_MATCH_MIN_SCORE = 85.0
    MATCH_DATE_WINDOW_DAYS = 3

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.ensure_schema()

    def main(self, request_dict):
        """共通処理専用クラスを直接APIとして実行した場合は明示的に拒否する。"""
        raise NotImplementedError("ExpenseSourceBaseは共通処理専用です。")

    def ensure_schema(self):
        """出費源、照合、Serverキュー、Gmail OAuth用の表を作成する。"""
        if ExpenseSourceBase._schema_ready:
            return
        sql = self.database.read_sql("CREATE_EXPENSE_SOURCE_TABLES", location=__file__)
        for statement in self.database.split_statements(sql):
            self.database.execute(statement)
        self.database.commit()
        ExpenseSourceBase._schema_ready = True

    def list_sources(self, user_id):
        """出費源一覧と未照合取引ごとの候補レシートを返す。"""
        sources = self.database.select(
            self.database.read_sql("SELECT_EXPENSE_SOURCES", location=__file__),
            {"CRE_USER_ID": user_id},
        )
        receipts = self.matchable_receipts(user_id)
        result = [self.public_source(row, receipts) for row in sources]
        return {
            "summary": {
                "total": len(result),
                "matched": sum(1 for row in result if row["matchStatus"] == "MATCHED"),
                "unmatched": sum(1 for row in result if row["matchStatus"] == "UNMATCHED"),
                "ignored": sum(1 for row in result if row["matchStatus"] == "IGNORED"),
            },
            "sources": result,
        }

    def upsert_source(self, user_id, source):
        """外部取引を冪等に保存し、未照合の場合は自動照合する。"""
        source_type = str(source.get("sourceType") or "").strip().upper()
        transaction_dt = self.normalize_date(source.get("transactionDate"))
        merchant_name = str(source.get("merchantName") or "").strip()
        amount = self.decimal_amount(source.get("amount"))
        if not source_type or not transaction_dt or amount is None:
            raise ValueError("sourceType、transactionDate、amount は必須です。")
        external_id = str(source.get("externalId") or "").strip() or self.source_key(
            source_type,
            transaction_dt,
            source.get("transactionTime"),
            merchant_name,
            amount,
        )
        ymd, hms = now_ymd_hms()
        params = {
            "source_type": source_type,
            "external_id": external_id,
            "transaction_dt": transaction_dt,
            "transaction_tm": self.normalize_time(source.get("transactionTime")),
            "merchant_name": merchant_name,
            "amount": amount,
            "currency": str(source.get("currency") or "JPY").upper(),
            "direction": str(source.get("direction") or "DEBIT").upper(),
            "source_kind": str(source.get("sourceKind") or "PAYMENT").upper(),
            "account_label": str(source.get("accountLabel") or "").strip(),
            "raw_data_json": json.dumps(source.get("rawData") or {}, ensure_ascii=False, default=str),
            "ymd": ymd,
            "hms": hms,
            "user_id": user_id,
        }
        sql = """
            INSERT INTO EXPENSE_SOURCE_TRANSACTION (
                CRE_PROG, UPD_PROG, SOURCE_TYPE, EXTERNAL_ID, TRANSACTION_DT,
                TRANSACTION_TM, MERCHANT_NAME, AMOUNT, CURRENCY, DIRECTION,
                SOURCE_KIND, ACCOUNT_LABEL, MATCH_STATUS, RAW_DATA_JSON,
                CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID
            ) VALUES (
                'ExpenseSourceImport', 'ExpenseSourceImport', %(source_type)s, %(external_id)s,
                %(transaction_dt)s, %(transaction_tm)s, %(merchant_name)s, %(amount)s,
                %(currency)s, %(direction)s, %(source_kind)s, %(account_label)s,
                'UNMATCHED', %(raw_data_json)s, %(ymd)s, %(hms)s, %(ymd)s, %(hms)s,
                %(user_id)s, %(user_id)s
            )
            ON CONFLICT (CRE_USER_ID, SOURCE_TYPE, EXTERNAL_ID)
            DO UPDATE SET
                TRANSACTION_DT = EXCLUDED.TRANSACTION_DT,
                TRANSACTION_TM = EXCLUDED.TRANSACTION_TM,
                MERCHANT_NAME = EXCLUDED.MERCHANT_NAME,
                AMOUNT = EXCLUDED.AMOUNT,
                CURRENCY = EXCLUDED.CURRENCY,
                DIRECTION = EXCLUDED.DIRECTION,
                SOURCE_KIND = EXCLUDED.SOURCE_KIND,
                ACCOUNT_LABEL = EXCLUDED.ACCOUNT_LABEL,
                RAW_DATA_JSON = EXCLUDED.RAW_DATA_JSON,
                UPD_PROG = 'ExpenseSourceImport',
                UPD_DT = EXCLUDED.UPD_DT,
                UPD_TM = EXCLUDED.UPD_TM,
                UPD_USER_ID = EXCLUDED.UPD_USER_ID,
                DEL_FLAG = 0
            RETURNING ID
        """
        source_id = self.database.do_sql_with_retry(sql, params).fetchone()["id"]
        self.auto_match_source(int(source_id), user_id)
        return int(source_id)

    def auto_match_all(self, user_id):
        """未照合の全出費源を再評価する。"""
        rows = self.database.select(
            """SELECT * FROM EXPENSE_SOURCE_TRANSACTION
               WHERE CRE_USER_ID = %(CRE_USER_ID)s AND DEL_FLAG = 0 AND MATCH_STATUS = 'UNMATCHED'""",
            {"CRE_USER_ID": user_id},
        )
        matched = sum(1 for row in rows if self.auto_match_source(int(self.value(row, "ID", "id")), user_id))
        self.database.commit()
        return {"evaluated": len(rows), "matched": matched}

    def auto_match_source(self, source_id, user_id):
        """一件の出費源を高信頼候補へ自動照合する。"""
        source = self.require_source(source_id, user_id)
        if str(self.value(source, "MATCH_STATUS", "match_status") or "") != "UNMATCHED":
            return False
        candidates = self.candidate_receipts(source, self.matchable_receipts(user_id))
        if not candidates or candidates[0]["score"] < self.AUTO_MATCH_MIN_SCORE:
            return False
        if len(candidates) > 1 and candidates[0]["score"] == candidates[1]["score"]:
            return False
        self.create_match(source_id, candidates[0]["receiptId"], candidates[0]["score"], "AUTO", user_id)
        return True

    def manual_match(self, source_id, receipt_id, user_id):
        """利用者が選んだ出費源とレシートを確定照合する。"""
        source = self.require_source(source_id, user_id)
        receipt = self.require_receipt(receipt_id, user_id)
        score = self.match_score(source, receipt)
        self.remove_match(source_id, user_id, commit=False)
        self.create_match(source_id, receipt_id, score, "MANUAL", user_id)
        self.database.commit()
        return {"ok": True, "message": "出費源とレシートを照合しました。"}

    def unmatch(self, source_id, user_id):
        """照合を解除して未照合へ戻す。"""
        self.require_source(source_id, user_id)
        self.remove_match(source_id, user_id, commit=True)
        return {"ok": True, "message": "照合を解除しました。"}

    def ignore(self, source_id, ignored, user_id):
        """振替・ATM・月次請求など照合不要の取引を除外または復帰する。"""
        self.require_source(source_id, user_id)
        ymd, hms = now_ymd_hms()
        status = "IGNORED" if ignored else "UNMATCHED"
        self.database.update(
            """UPDATE EXPENSE_SOURCE_TRANSACTION
               SET MATCH_STATUS=%(status)s, UPD_PROG='ExpenseSourceIgnore', UPD_DT=%(ymd)s,
                   UPD_TM=%(hms)s, UPD_USER_ID=%(user_id)s
               WHERE ID=%(source_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"status": status, "ymd": ymd, "hms": hms, "source_id": source_id, "user_id": user_id},
        )
        self.database.commit()
        return {"ok": True, "message": "出費源の状態を更新しました。"}

    def matchable_receipts(self, user_id):
        """まだ他の出費源と照合されていないレシートを取得する。"""
        return self.database.select(
            self.database.read_sql("SELECT_MATCHABLE_RECEIPTS", location=__file__),
            {"CRE_USER_ID": user_id},
        )

    def candidate_receipts(self, source, receipts):
        """金額一致かつ日付±3日のレシートをスコア順に返す。"""
        candidates = []
        for receipt in receipts:
            score = self.match_score(source, receipt)
            if score <= 0:
                continue
            candidates.append({
                "receiptId": str(self.value(receipt, "RET_ID", "ret_id")),
                "supplierName": str(self.value(receipt, "SUP_NAME", "sup_name") or ""),
                "receiptDate": str(self.value(receipt, "RET_DT", "ret_dt") or ""),
                "receiptTime": str(self.value(receipt, "RET_TM", "ret_tm") or ""),
                "totalPrice": float(self.value(receipt, "TOA_PRICE", "toa_price") or 0),
                "score": score,
            })
        return sorted(candidates, key=lambda row: (-row["score"], row["receiptDate"], row["receiptId"]))[:5]

    def match_score(self, source, receipt):
        """金額、日付、店名から0～100の照合スコアを算出する。"""
        try:
            source_amount = self.decimal_amount(self.value(source, "AMOUNT", "amount"))
            receipt_amount = self.decimal_amount(self.value(receipt, "TOA_PRICE", "toa_price"))
            if source_amount is None or receipt_amount is None or abs(source_amount) != abs(receipt_amount):
                return 0.0
            source_date = datetime.strptime(str(self.value(source, "TRANSACTION_DT", "transaction_dt")), "%Y-%m-%d").date()
            receipt_date = datetime.strptime(str(self.value(receipt, "RET_DT", "ret_dt")), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return 0.0
        day_diff = abs((source_date - receipt_date).days)
        if day_diff > self.MATCH_DATE_WINDOW_DAYS:
            return 0.0
        source_name = self.normalize_name(self.value(source, "MERCHANT_NAME", "merchant_name"))
        receipt_name = self.normalize_name(self.value(receipt, "SUP_NAME", "sup_name"))
        name_score = SequenceMatcher(None, source_name, receipt_name).ratio() if source_name and receipt_name else 0
        return round(70 + (20 - day_diff * 5) + name_score * 10, 2)

    def create_match(self, source_id, receipt_id, score, match_type, user_id):
        """照合行を登録し、出費源を照合済みにする。"""
        self.require_receipt(receipt_id, user_id)
        conflict = self.database.select(
            """SELECT ID FROM EXPENSE_SOURCE_MATCH
               WHERE RET_ID=%(receipt_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0
                 AND SOURCE_TRANSACTION_ID<>%(source_id)s""",
            {"receipt_id": receipt_id, "user_id": user_id, "source_id": source_id},
        )
        if conflict:
            raise Error(status_code=409, error_code="1000062", message="このレシートは別の出費源と照合済みです。")
        ymd, hms = now_ymd_hms()
        self.database.insert(
            """INSERT INTO EXPENSE_SOURCE_MATCH (
                   CRE_PROG, UPD_PROG, SOURCE_TRANSACTION_ID, RET_ID, MATCH_SCORE, MATCH_TYPE,
                   CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID
               ) VALUES (
                   'ExpenseSourceMatch', 'ExpenseSourceMatch', %(source_id)s, %(receipt_id)s,
                   %(score)s, %(match_type)s, %(ymd)s, %(hms)s, %(ymd)s, %(hms)s,
                   %(user_id)s, %(user_id)s
               )""",
            {"source_id": source_id, "receipt_id": receipt_id, "score": score,
             "match_type": match_type, "ymd": ymd, "hms": hms, "user_id": user_id},
        )
        self.database.update(
            """UPDATE EXPENSE_SOURCE_TRANSACTION SET MATCH_STATUS='MATCHED',
                   UPD_PROG='ExpenseSourceMatch', UPD_DT=%(ymd)s, UPD_TM=%(hms)s, UPD_USER_ID=%(user_id)s
               WHERE ID=%(source_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"ymd": ymd, "hms": hms, "user_id": user_id, "source_id": source_id},
        )

    def remove_match(self, source_id, user_id, commit):
        """有効な照合行を論理削除する。"""
        ymd, hms = now_ymd_hms()
        self.database.update(
            """UPDATE EXPENSE_SOURCE_MATCH SET DEL_FLAG=1, UPD_PROG='ExpenseSourceUnmatch',
                   UPD_DT=%(ymd)s, UPD_TM=%(hms)s, UPD_USER_ID=%(user_id)s
               WHERE SOURCE_TRANSACTION_ID=%(source_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"ymd": ymd, "hms": hms, "user_id": user_id, "source_id": source_id},
        )
        self.database.update(
            """UPDATE EXPENSE_SOURCE_TRANSACTION SET MATCH_STATUS='UNMATCHED',
                   UPD_PROG='ExpenseSourceUnmatch', UPD_DT=%(ymd)s, UPD_TM=%(hms)s, UPD_USER_ID=%(user_id)s
               WHERE ID=%(source_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"ymd": ymd, "hms": hms, "user_id": user_id, "source_id": source_id},
        )
        if commit:
            self.database.commit()

    def public_source(self, row, receipts):
        """DB行を出費源画面向けの形式へ変換する。"""
        matched_receipt_id = self.value(row, "RET_ID", "ret_id")
        return {
            "id": int(self.value(row, "ID", "id")),
            "sourceType": str(self.value(row, "SOURCE_TYPE", "source_type") or ""),
            "transactionDate": str(self.value(row, "TRANSACTION_DT", "transaction_dt") or ""),
            "transactionTime": str(self.value(row, "TRANSACTION_TM", "transaction_tm") or ""),
            "merchantName": str(self.value(row, "MERCHANT_NAME", "merchant_name") or ""),
            "amount": float(self.value(row, "AMOUNT", "amount") or 0),
            "currency": str(self.value(row, "CURRENCY", "currency") or "JPY"),
            "direction": str(self.value(row, "DIRECTION", "direction") or "DEBIT"),
            "sourceKind": str(self.value(row, "SOURCE_KIND", "source_kind") or "PAYMENT"),
            "accountLabel": str(self.value(row, "ACCOUNT_LABEL", "account_label") or ""),
            "matchStatus": str(self.value(row, "MATCH_STATUS", "match_status") or "UNMATCHED"),
            "matchType": str(self.value(row, "MATCH_TYPE", "match_type") or ""),
            "matchScore": float(self.value(row, "MATCH_SCORE", "match_score") or 0),
            "matchedReceipt": None if not matched_receipt_id else {
                "receiptId": str(matched_receipt_id),
                "supplierName": str(self.value(row, "SUP_NAME", "sup_name") or ""),
                "receiptDate": str(self.value(row, "RET_DT", "ret_dt") or ""),
                "receiptTime": str(self.value(row, "RET_TM", "ret_tm") or ""),
                "totalPrice": float(self.value(row, "TOA_PRICE", "toa_price") or 0),
            },
            "candidates": [] if matched_receipt_id else self.candidate_receipts(row, receipts),
        }

    def require_source(self, source_id, user_id):
        rows = self.database.select(
            """SELECT * FROM EXPENSE_SOURCE_TRANSACTION
               WHERE ID=%(source_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"source_id": source_id, "user_id": user_id},
        )
        if not rows:
            raise Error(status_code=404, error_code="1000062", message="出費源が見つかりません。")
        return rows[0]

    def require_receipt(self, receipt_id, user_id):
        rows = self.database.select(
            """SELECT RET_ID, SUP_NAME, RET_DT, RET_TM, TOA_PRICE FROM RECEIPT_INFO
               WHERE RET_ID=%(receipt_id)s AND CRE_USER_ID=%(user_id)s AND DEL_FLAG=0""",
            {"receipt_id": receipt_id, "user_id": user_id},
        )
        if not rows:
            raise Error(status_code=404, error_code="1000062", message="レシートが見つかりません。")
        return rows[0]

    @staticmethod
    def normalize_name(value):
        text = unicodedata.normalize("NFKC", str(value or "")).lower()
        return re.sub(r"(?:株式会社|有限会社|合同会社|[\s・･\-_/（）()])", "", text)

    @staticmethod
    def normalize_date(value):
        raw = str(value or "").strip().replace("/", "-")
        for pattern in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(raw, pattern).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""

    @staticmethod
    def normalize_time(value):
        raw = str(value or "").strip()
        match = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", raw)
        return f"{int(match.group(1)):02d}:{match.group(2)}:{match.group(3) or '00'}" if match else ""

    @staticmethod
    def decimal_amount(value):
        try:
            return Decimal(str(value).replace(",", ""))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def source_key(source_type, transaction_dt, transaction_tm, merchant_name, amount):
        raw = "|".join(map(str, (source_type, transaction_dt, transaction_tm or "", merchant_name, amount)))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def value(row, *keys):
        for key in keys:
            if key in row:
                return row.get(key)
        return None
