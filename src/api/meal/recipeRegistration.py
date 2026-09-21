"""レシピ登録 API。"""

from src.api.meal.mealBase import MealBase
from src.common.functions.response import response


class RecipeRegistration(MealBase):
    """新しいレシピを保存する。"""

    def main(self, request_dict):
        """
        処理概要: 新しいレシピを登録する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 材料と手順を検証して登録する。
          3. レシピ ID を返す。

        Args:
            request_dict (dict): レシピを含むリクエスト。

        Returns:
            dict: 登録結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return self.save_recipe(user_id, (request_dict.get("body") or {}).get("recipe") or {})
