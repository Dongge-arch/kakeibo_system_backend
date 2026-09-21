"""献立保存 API。"""

from src.api.meal.mealBase import MealBase
from src.common.functions.response import response


class ShoppingPlanUpdate(MealBase):
    """人数と回数に合わせた買い物計画を保存する。"""

    def main(self, request_dict):
        """
        処理概要: 献立の人数、回数、購入状態を保存する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 献立と買い物リストを検証して保存する。
          3. 最新の買い物リストを返す。

        Args:
            request_dict (dict): 献立を含むリクエスト。

        Returns:
            dict: 更新後の献立の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return self.save_plan(user_id, request_dict.get("body") or {})
