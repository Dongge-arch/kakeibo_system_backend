"""献立と買い物リスト参照 API。"""

from src.api.meal.mealBase import MealBase
from src.common.functions.response import response


class ShoppingPlanReference(MealBase):
    """保存済み献立から買い物リストを計算する。"""

    def main(self, request_dict):
        """
        処理概要: 献立と買い物リストを参照する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 保存済み献立と材料の合計を取得する。
          3. 買い物リストを返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 献立と買い物リストの API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return response(200, self.get_plan(user_id))
