# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from calendar import monthrange
from datetime import datetime
import json

from src.api.kakeibo.receipt.new_receipt_registration.newReceiptRegistration import NewReceiptRegistration
from src.common.api_utils import now_ymd_hms
from src.common.functions.response import response
from src.common.base import BaseRestApi


class RecurringExpenseBase(BaseRestApi):
    """定期出費の設定と自動登録に共通するDB操作。"""

    _schema_ready = False

    def __init__(self, db_path=None):
        """
        クラスを初期化する。

        Args:
            db_path (Any): 旧呼び出し互換のためのDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)
        self.ensure_schema()

    def validate_body(self, request_dict):
        """
        リクエスト本文を検証する。

        Args:
            request_dict (Any): API呼び出し時のリクエスト情報。

        Returns:
            Any: 処理結果。
        """
        return super().validate_body(request_dict)

    def ensure_schema(self):
        """
        ensure_schemaの処理を実行する。

        Args:
            None: 引数なし。

        Returns:
            Any: 処理結果。
        """
        if RecurringExpenseBase._schema_ready:
            return
        self.database.execute(self.database.read_sql("CREATE_RECURRING_EXPENSE", location=__file__))
        RecurringExpenseBase._schema_ready = True

    def list_rules(self, user_id):
        """
        list_rulesの処理を実行する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rows = self.database.select(
            self.database.read_sql("SELECT_RECURRING_EXPENSE", location=__file__),
            {"CRE_USER_ID": user_id},
        )
        return response(200, [self.normalize_row(row) for row in rows])

    def create_rule(self, body, user_id):
        """
        create_ruleの処理を実行する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        data = self.rule_params(body, create=True)
        ymd, hms = now_ymd_hms()
        data.update({
            "CRE_PROG": "RecurringExpenseRegistration",
            "UPD_PROG": "RecurringExpenseRegistration",
            "CRE_DT": ymd,
            "CRE_TM": hms,
            "UPD_DT": ymd,
            "UPD_TM": hms,
            "CRE_USER_ID": user_id,
            "UPD_USER_ID": user_id,
        })
        self.database.insert(
            self.database.read_sql("INSERT_RECURRING_EXPENSE", location=__file__),
            data,
        )
        return response(201, {"ok": True, "message": "定期出費を登録しました。"})

    def update_rule(self, body, user_id):
        """
        update_ruleの処理を実行する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rule_id = int(body.get("id") or 0)
        if rule_id <= 0:
            return response(400, {"errorMessage": "更新対象が不正です。"})
        data = self.rule_params(body, create=False)
        ymd, hms = now_ymd_hms()
        data.update({"ID": rule_id, "UPD_DT": ymd, "UPD_TM": hms, "CRE_USER_ID": user_id, "UPD_USER_ID": user_id})
        updated = self.database.update(
            self.database.read_sql("UPDATE_RECURRING_EXPENSE", location=__file__),
            data,
        )
        return response(200, {"ok": bool(updated), "message": "定期出費を更新しました。"})

    def delete_rule(self, body, user_id):
        """
        delete_ruleの処理を実行する。

        Args:
            body (Any): リクエスト本文。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        rule_id = int(body.get("id") or 0)
        if rule_id <= 0:
            return response(400, {"errorMessage": "削除対象が不正です。"})
        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_RECURRING_EXPENSE_02", location=__file__),
            {"ID": rule_id, "UPD_DT": ymd, "UPD_TM": hms, "CRE_USER_ID": user_id, "UPD_USER_ID": user_id},
        )
        return response(200, {"ok": True, "message": "定期出費を削除しました。"})

    def run_due(self, user_id):
        """
        run_dueの処理を実行する。

        Args:
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        today = datetime.now()
        current_month = today.strftime("%Y-%m")
        rows = self.database.select(
            self.database.read_sql("SELECT_RECURRING_EXPENSE_02", location=__file__),
            {"LAST_RUN_MONTH": current_month, "CRE_USER_ID": user_id},
        )
        created = []
        for row in rows:
            receipt_date = self.scheduled_date(today, int(self.row_value(row, "DAY_OF_MONTH", "day_of_month", "dayofmonth") or 1))
            if receipt_date.date() > today.date():
                continue
            receipt_id = self.create_receipt_from_rule(row, receipt_date, user_id)
            if not receipt_id:
                raise ValueError("定期出費の出費明細登録に失敗しました。")
            rule_id = self.row_value(row, "id", "ID")
            self.mark_run(rule_id, current_month, user_id)
            created.append({"id": rule_id, "receiptId": receipt_id})
        return response(200, {"ok": True, "createdCount": len(created), "created": created})

    def create_receipt_from_rule(self, row, receipt_date, user_id):
        """
        create_receipt_from_ruleの処理を実行する。

        Args:
            row (Any): rowの値。
            receipt_date (Any): receipt_dateの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
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
        result = api.call(body={"receiptInfo": receipt_info}, headers={"x-kakeibo-user-id": user_id}, validate_b=False)
        body = result.get("body") or {}
        if isinstance(body, str):
            body = json.loads(body)
        if int(result.get("statusCode") or 500) >= 400:
            raise ValueError(body.get("errorMessage") or "定期出費の出費明細登録に失敗しました。")
        return body.get("receiptId")

    def mark_run(self, rule_id, month, user_id):
        """
        mark_runの処理を実行する。

        Args:
            rule_id (Any): rule_idの値。
            month (Any): monthの値。
            user_id (Any): ユーザーID。

        Returns:
            Any: 処理結果。
        """
        ymd, hms = now_ymd_hms()
        self.database.update(
            self.database.read_sql("UPDATE_RECURRING_EXPENSE_03", location=__file__),
            {"ID": rule_id, "LAST_RUN_MONTH": month, "UPD_DT": ymd, "UPD_TM": hms, "CRE_USER_ID": user_id, "UPD_USER_ID": user_id},
        )

    def scheduled_date(self, today, day_of_month):
        """
        scheduled_dateの処理を実行する。

        Args:
            today (Any): todayの値。
            day_of_month (Any): day_of_monthの値。

        Returns:
            Any: 処理結果。
        """
        last_day = monthrange(today.year, today.month)[1]
        return today.replace(day=min(max(day_of_month, 1), last_day), hour=0, minute=0, second=0, microsecond=0)

    def rule_params(self, body, create):
        """
        rule_paramsの処理を実行する。

        Args:
            body (Any): リクエスト本文。
            create (Any): createの値。

        Returns:
            Any: 処理結果。
        """
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
        """
        normalize_rowの処理を実行する。

        Args:
            row (Any): rowの値。

        Returns:
            Any: 処理結果。
        """
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
        """
        row_valueの処理を実行する。

        Args:
            row (Any): rowの値。
            *names: 追加の位置引数。

        Returns:
            Any: 処理結果。
        """
        for name in names:
            value = row.get(name)
            if value is not None:
                return value
        return None

    def clean(self, value):
        """
        cleanの処理を実行する。

        Args:
            value (Any): valueの値。

        Returns:
            Any: 処理結果。
        """
        return str(value or "").strip()
