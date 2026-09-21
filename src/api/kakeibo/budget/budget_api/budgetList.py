"""予算一覧参照 API。"""

from src.api.kakeibo.budget.budget_api.budgetBase import BudgetBase
from src.common.functions.response import response


class BudgetList(BudgetBase):
    """認証済みユーザーの予算一覧を取得する。"""

    def main(self, request_dict):
        """
        処理概要: 予算の一覧を参照する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 有効な予算を取得する。
          3. 一覧を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 予算一覧の API レスポンス。
        """
        user_id = self.require_user_id(request_dict)
        return response(200, self.list_budgets(user_id))
