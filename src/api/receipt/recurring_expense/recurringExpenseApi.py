# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from calendar import monthrange
from datetime import datetime
import json

from src.api.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.api.utils import json_response, now_ymd_hms
from src.common.base import BaseRestApi


class RecurringExpenseApi(BaseRestApi):
    """毎月の自動引き落としなど、定期出費設定と自動登録を扱うAPI。"""

    _schema_ready = False

    def __init__(self, db_path=None):
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.ensure_schema()

    def validate_body(self, request_dict):
        return super().validate_body(request_dict)

    def main(self, request_dict):
        body = request_dict.get("body") or {}
        action = body.get("action")
        if action == "list":
            return self.list_rules()
        if action == "create":
            return self.create_rule(body)
        if action == "update":
            return self.update_rule(body)
        if action == "delete":
            return self.delete_rule(body)
        if action == "run_due":
            return self.run_due()
        return json_response(400, {"errorMessage": "不明な定期出費操作です。"})

    def ensure_schema(self):
        if self.__class__._schema_ready:
            return
        self.database.execute(
            """
            CREATE TABLE IF NOT EXISTS recurring_expense (
                id BIGSERIAL PRIMARY KEY,
                CRE_PROG TEXT,
                UPD_PROG TEXT,
                RULE_NAME TEXT NOT NULL,
                DAY_OF_MONTH INTEGER NOT NULL,
                ITEM_NAME TEXT NOT NULL,
                CAT1 TEXT,
                CAT2 TEXT,
                AMOUNT NUMERIC(100, 2) DEFAULT 0,
                TAX_FLAG INTEGER DEFAULT 1,
                ENABLED INTEGER DEFAULT 1,
                LAST_RUN_MONTH TEXT,
                MEMO TEXT,
                CRE_DT TEXT,
                CRE_TM TEXT,
                UPD_DT TEXT,
                UPD_TM TEXT,
                CRE_USER_ID TEXT,
                UPD_USER_ID TEXT,
                DEL_FLAG INTEGER DEFAULT 0,
                CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.__class__._schema_ready = True

    def list_rules(self):
        rows = self.database.select(
            """
            SELECT
                id,
                RULE_NAME AS ruleName,
                DAY_OF_MONTH AS dayOfMonth,
                ITEM_NAME AS itemName,
                CAT1 AS category1,
                CAT2 AS category2,
                AMOUNT AS amount,
                TAX_FLAG AS taxFlag,
                ENABLED AS enabled,
                LAST_RUN_MONTH AS lastRunMonth,
                MEMO AS memo
            FROM recurring_expense
            WHERE DEL_FLAG = 0
            ORDER BY DAY_OF_MONTH, id
            """
        )
        return json_response(200, [self.normalize_row(row) for row in rows])

    def create_rule(self, body):
        data = self.rule_params(body, create=True)
        ymd, hms = now_ymd_hms()
        data.update({
            "CRE_PROG": "RecurringExpenseApi",
            "UPD_PROG": "RecurringExpenseApi",
            "CRE_DT": ymd,
            "CRE_TM": hms,
            "UPD_DT": ymd,
            "UPD_TM": hms,
        })
        self.database.insert(
            """
            INSERT INTO recurring_expense (
                CRE_PROG, UPD_PROG, RULE_NAME, DAY_OF_MONTH, ITEM_NAME,
                CAT1, CAT2, AMOUNT, TAX_FLAG, ENABLED, LAST_RUN_MONTH, MEMO,
                CRE_DT, CRE_TM, UPD_DT, UPD_TM, DEL_FLAG
            ) VALUES (
                %(CRE_PROG)s, %(UPD_PROG)s, %(RULE_NAME)s, %(DAY_OF_MONTH)s, %(ITEM_NAME)s,
                %(CAT1)s, %(CAT2)s, %(AMOUNT)s, %(TAX_FLAG)s, %(ENABLED)s, %(LAST_RUN_MONTH)s, %(MEMO)s,
                %(CRE_DT)s, %(CRE_TM)s, %(UPD_DT)s, %(UPD_TM)s, 0
            )
            """,
            data,
        )
        return json_response(201, {"ok": True, "message": "定期出費を登録しました。"})

    def update_rule(self, body):
        rule_id = int(body.get("id") or 0)
        if rule_id <= 0:
            return json_response(400, {"errorMessage": "更新対象が不正です。"})
        data = self.rule_params(body, create=False)
        ymd, hms = now_ymd_hms()
        data.update({"id": rule_id, "UPD_DT": ymd, "UPD_TM": hms})
        updated = self.database.update(
            """
            UPDATE recurring_expense
            SET UPD_PROG = 'RecurringExpenseApi',
                RULE_NAME = %(RULE_NAME)s,
                DAY_OF_MONTH = %(DAY_OF_MONTH)s,
                ITEM_NAME = %(ITEM_NAME)s,
                CAT1 = %(CAT1)s,
                CAT2 = %(CAT2)s,
                AMOUNT = %(AMOUNT)s,
                TAX_FLAG = %(TAX_FLAG)s,
                ENABLED = %(ENABLED)s,
                MEMO = %(MEMO)s,
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s
            WHERE id = %(id)s
              AND DEL_FLAG = 0
            """,
            data,
        )
        return json_response(200, {"ok": bool(updated), "message": "定期出費を更新しました。"})

    def delete_rule(self, body):
        rule_id = int(body.get("id") or 0)
        if rule_id <= 0:
            return json_response(400, {"errorMessage": "削除対象が不正です。"})
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE recurring_expense
            SET UPD_PROG = 'RecurringExpenseApi',
                DEL_FLAG = 1,
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s
            WHERE id = %(id)s
              AND DEL_FLAG = 0
            """,
            {"id": rule_id, "UPD_DT": ymd, "UPD_TM": hms},
        )
        return json_response(200, {"ok": True, "message": "定期出費を削除しました。"})

    def run_due(self):
        today = datetime.now()
        current_month = today.strftime("%Y-%m")
        rows = self.database.select(
            """
            SELECT *
            FROM recurring_expense
            WHERE DEL_FLAG = 0
              AND ENABLED = 1
              AND (LAST_RUN_MONTH IS NULL OR LAST_RUN_MONTH <> %(current_month)s)
            ORDER BY DAY_OF_MONTH, id
            """,
            {"current_month": current_month},
        )
        created = []
        for row in rows:
            receipt_date = self.scheduled_date(today, int(self.row_value(row, "DAY_OF_MONTH", "day_of_month", "dayofmonth") or 1))
            if receipt_date.date() > today.date():
                continue
            receipt_id = self.create_receipt_from_rule(row, receipt_date)
            if not receipt_id:
                raise ValueError("定期出費の出費明細登録に失敗しました。")
            rule_id = self.row_value(row, "id", "ID")
            self.mark_run(rule_id, current_month)
            created.append({"id": rule_id, "receiptId": receipt_id})
        return json_response(200, {"ok": True, "createdCount": len(created), "created": created})

    def create_receipt_from_rule(self, row, receipt_date):
        name = self.row_value(row, "RULE_NAME", "rule_name", "rulename") or "定期出費"
        item_name = self.row_value(row, "ITEM_NAME", "item_name", "itemname") or name
        amount = float(self.row_value(row, "AMOUNT", "amount") or 0)
        receipt_info = {
            "invoiceRegistrationNumber": "",
            "supplierName": "",
            "supplierImage": "",
            "receiptDate": receipt_date.strftime("%Y-%m-%d"),
            "receiptTime": "00:00",
            "taxFlag": "1",
            "totalPrice": amount,
            "receiptDetailCount": 1,
            "receiptDetails": [{
                "itemName": item_name,
                "category1": self.row_value(row, "CAT1", "cat1") or "",
                "category2": self.row_value(row, "CAT2", "cat2") or "",
                "quantity": 1,
                "unitPrice": amount,
                "discount": 0,
                "totalPrice": amount,
            }],
        }
        api = NewReceiptRegistration()
        result = api.call(body={"receiptInfo": receipt_info}, validate_b=False)
        body = result.get("body") or {}
        if isinstance(body, str):
            body = json.loads(body)
        if int(result.get("statusCode") or 500) >= 400:
            raise ValueError(body.get("errorMessage") or "定期出費の出費明細登録に失敗しました。")
        return body.get("receiptId")

    def mark_run(self, rule_id, month):
        ymd, hms = now_ymd_hms()
        self.database.update(
            """
            UPDATE recurring_expense
            SET LAST_RUN_MONTH = %(LAST_RUN_MONTH)s,
                UPD_PROG = 'RecurringExpenseApi',
                UPD_DT = %(UPD_DT)s,
                UPD_TM = %(UPD_TM)s
            WHERE id = %(id)s
            """,
            {"id": rule_id, "LAST_RUN_MONTH": month, "UPD_DT": ymd, "UPD_TM": hms},
        )

    def scheduled_date(self, today, day_of_month):
        last_day = monthrange(today.year, today.month)[1]
        return today.replace(day=min(max(day_of_month, 1), last_day), hour=0, minute=0, second=0, microsecond=0)

    def rule_params(self, body, create):
        day = int(body.get("dayOfMonth") or body.get("day_of_month") or 1)
        day = min(max(day, 1), 31)
        amount = float(body.get("amount") or 0)
        rule_name = self.clean(body.get("ruleName") or body.get("rule_name"))
        item_name = self.clean(body.get("itemName") or body.get("item_name") or rule_name)
        if not rule_name:
            raise ValueError("名称を入力してください。")
        if not item_name:
            raise ValueError("明細名を入力してください。")
        if amount <= 0:
            raise ValueError("金額は1円以上で入力してください。")
        return {
            "RULE_NAME": rule_name,
            "DAY_OF_MONTH": day,
            "ITEM_NAME": item_name,
            "CAT1": self.clean(body.get("category1")),
            "CAT2": self.clean(body.get("category2")),
            "AMOUNT": amount,
            "TAX_FLAG": 1,
            "ENABLED": 1 if body.get("enabled", True) else 0,
            "LAST_RUN_MONTH": self.clean(body.get("lastRunMonth")) if create else None,
            "MEMO": self.clean(body.get("memo")),
        }

    def normalize_row(self, row):
        return {
            "id": self.row_value(row, "id", "ID"),
            "ruleName": self.row_value(row, "ruleName", "rulename", "RULE_NAME") or "",
            "dayOfMonth": int(self.row_value(row, "dayOfMonth", "dayofmonth", "DAY_OF_MONTH") or 1),
            "itemName": self.row_value(row, "itemName", "itemname", "ITEM_NAME") or "",
            "category1": self.row_value(row, "category1", "CAT1") or "",
            "category2": self.row_value(row, "category2", "CAT2") or "",
            "amount": float(self.row_value(row, "amount", "AMOUNT") or 0),
            "taxFlag": str(self.row_value(row, "taxFlag", "taxflag", "TAX_FLAG") or "1"),
            "enabled": str(self.row_value(row, "enabled", "ENABLED") or "1") not in ("0", "false", "False"),
            "lastRunMonth": self.row_value(row, "lastRunMonth", "lastrunmonth", "LAST_RUN_MONTH") or "",
            "memo": self.row_value(row, "memo", "MEMO") or "",
        }

    def row_value(self, row, *names):
        for name in names:
            value = row.get(name)
            if value is not None:
                return value
        return None

    def clean(self, value):
        return str(value or "").strip()
