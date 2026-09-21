"""予算一括保存 API。"""

from src.api.kakeibo.budget.budget_api.budgetBase import BudgetBase
from src.common.functions.response import response


class BudgetUpsert(BudgetBase):
    """分類ごとの予算をまとめて保存する。"""

    def main(self, request_dict):
        """
        処理概要: ユーザーの予算を一括登録または更新する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 予算の分類と金額を保存する。
          3. 保存結果を返す。

        Args:
            request_dict (dict): 予算一覧を含む認証済みリクエスト。

        Returns:
            dict: 保存結果の API レスポンス。
        """
        user_id = self.require_user_id(request_dict)
        self.upsert_budgets((request_dict.get("body") or {}).get("budgets") or [], user_id)
        return response(200, {"ok": True})
