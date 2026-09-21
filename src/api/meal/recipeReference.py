"""レシピ一覧参照 API。"""

from src.api.meal.mealBase import MealBase
from src.common.functions.response import response


class RecipeReference(MealBase):
    """ユーザーのレシピを一覧表示する。"""

    def main(self, request_dict):
        """
        処理概要: 保存済みレシピを参照する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. ユーザーのレシピを取得する。
          3. 一覧を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: レシピ一覧の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return response(200, self.list_recipes(user_id))
