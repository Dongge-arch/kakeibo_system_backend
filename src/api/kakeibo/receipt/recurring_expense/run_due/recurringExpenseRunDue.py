"""期日到来の定期出費実行 API。"""

from src.api.kakeibo.receipt.recurring_expense.recurringExpenseBase import RecurringExpenseBase


class RecurringExpenseRunDue(RecurringExpenseBase):
    """期日を迎えた定期出費をレシートとして登録する。"""

    def main(self, request_dict):
        """
        処理概要: 今月分の未実行の定期出費を登録する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 実行日を迎えた設定からレシートを登録する。
          3. 実行結果を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 登録件数と対象を含む API レスポンス。
        """
        return self.run_due(self.require_user_id(request_dict))
