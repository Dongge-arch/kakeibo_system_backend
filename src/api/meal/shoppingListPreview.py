"""買い物リストプレビュー API。"""

from src.api.meal.mealBase import MealBase, RecipeValidationError
from src.common.functions.response import response


class ShoppingListPreview(MealBase):
    """選択したレシピから買い物リストを生成する。"""

    def main(self, request_dict):
        """
        処理概要: 人数と作る回数から購入量を計算する。
        処理内容:
          1. ユーザーと選択内容を検証する。
          2. 材料を購入単位へ換算し、調味料を集約する。
          3. プレビューを返す。

        Args:
            request_dict (dict): selectionsを含むリクエスト。

        Returns:
            dict: 買い物リストの API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        try:
            selections = self.normalize_selections(
                (request_dict.get("body") or {}).get("selections"),
            )
        except RecipeValidationError as error:
            return response(400, {"errorMessage": str(error)})
        preview = self.build_shopping_preview(user_id, selections)
        if preview is None:
            return response(404, {"errorMessage": "選択したレシピが見つかりません。"})
        return response(200, preview)
