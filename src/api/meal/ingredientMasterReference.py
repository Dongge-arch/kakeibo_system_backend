"""食材入力候補参照 API。"""

from src.api.meal.mealBase import MealBase
from src.common.functions.response import response


class IngredientMasterReference(MealBase):
    """ユーザーのレシピから食材入力候補を返す。"""

    def main(self, request_dict):
        """
        処理概要: 保存済みレシピから食材マスターを作成する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 食材ID、単位、補助単位を重複なく集める。
          3. 名称順で返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 食材入力候補の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        return response(200, self.ingredient_master(user_id))
