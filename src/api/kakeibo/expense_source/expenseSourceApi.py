# -*- coding: utf-8 -*-

"""出費源一覧、照合、解除、除外、再照合API。"""

from src.api.kakeibo.expense_source.expenseSourceBase import ExpenseSourceBase
from src.common.functions.response import response


class ExpenseSourceApi(ExpenseSourceBase):
    """リクエストactionに応じて出費源操作を実行する。"""

    def main(self, request_dict):
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        action = str(body.get("action") or "list").lower()
        if action == "list":
            return response(200, self.list_sources(user_id))
        if action == "match":
            return response(200, self.manual_match(int(body.get("sourceId")), str(body.get("receiptId") or ""), user_id))
        if action == "unmatch":
            return response(200, self.unmatch(int(body.get("sourceId")), user_id))
        if action == "ignore":
            return response(200, self.ignore(int(body.get("sourceId")), bool(body.get("ignored", True)), user_id))
        if action == "rematch":
            result = self.auto_match_all(user_id)
            return response(200, {"ok": True, **result, "message": "未照合の出費源を再照合しました。"})
        return response(400, {"errorMessage": "出費源の操作が不正です。"})
