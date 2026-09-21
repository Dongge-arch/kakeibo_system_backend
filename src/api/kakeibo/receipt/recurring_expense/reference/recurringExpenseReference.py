"""定期出費一覧参照 API。"""

from src.api.kakeibo.receipt.recurring_expense.recurringExpenseBase import RecurringExpenseBase


class RecurringExpenseReference(RecurringExpenseBase):
    """認証済みユーザーの定期出費を取得する。"""

    def main(self, request_dict):
        """
        処理概要: 定期出費を一覧表示する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. ユーザーの有効な設定を照会する。
          3. 一覧を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 定期出費一覧の API レスポンス。
        """
        return self.list_rules(self.require_user_id(request_dict))
