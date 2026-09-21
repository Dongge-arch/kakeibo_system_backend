"""レシピ更新・削除 API。"""

from src.api.meal.mealBase import MealBase
from src.common.functions.response import response


class RecipeUpdateDelete(MealBase):
    """既存のレシピを変更または削除する。"""

    def main(self, request_dict):
        """
        処理概要: 既存レシピを更新または削除する。
        処理内容:
          1. ユーザーの認証と対象レシピを確認する。
          2. 指定された変更または削除を実行する。
          3. 処理結果を返す。

        Args:
            request_dict (dict): 操作とレシピを含むリクエスト。

        Returns:
            dict: 更新または削除結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        body = request_dict.get("body") or {}
        if body.get("action") == "delete_recipe":
            return self.delete_recipe(user_id, body.get("recipeId"))
        if body.get("action") == "save_recipe":
            return self.save_recipe(user_id, body.get("recipe") or {})
        return response(400, {"errorMessage": "unknown meal action"})
