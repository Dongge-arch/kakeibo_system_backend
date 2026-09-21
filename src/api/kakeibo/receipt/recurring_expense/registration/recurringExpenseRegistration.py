"""定期出費登録 API。"""

from src.api.kakeibo.receipt.recurring_expense.recurringExpenseBase import RecurringExpenseBase


class RecurringExpenseRegistration(RecurringExpenseBase):
    """新しい定期出費を登録する。"""

    def main(self, request_dict):
        """
        処理概要: 定期出費の設定を新規登録する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 設定内容を検証して保存する。
          3. 登録結果を返す。

        Args:
            request_dict (dict): 設定を含む認証済みリクエスト。

        Returns:
            dict: 登録結果の API レスポンス。
        """
        return self.create_rule(request_dict.get("body") or {}, self.require_user_id(request_dict))
