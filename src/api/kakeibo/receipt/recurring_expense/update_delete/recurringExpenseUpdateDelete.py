"""定期出費更新・削除 API。"""

from src.api.kakeibo.receipt.recurring_expense.recurringExpenseBase import RecurringExpenseBase
from src.common.functions.response import response


class RecurringExpenseUpdateDelete(RecurringExpenseBase):
    """既存の定期出費を更新または削除する。"""

    def main(self, request_dict):
        """
        処理概要: 定期出費の更新または削除を行う。
        処理内容:
          1. 認証済みユーザーと操作種別を取得する。
          2. 対象の設定を更新または削除する。
          3. 処理結果を返す。

        Args:
            request_dict (dict): 操作と設定を含む認証済みリクエスト。

        Returns:
            dict: 更新または削除結果の API レスポンス。
        """
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        if body.get("action") == "update":
            return self.update_rule(body, user_id)
        if body.get("action") == "delete":
            return self.delete_rule(body, user_id)
        return response(400, {"errorMessage": "不明な定期出費操作です。"})
