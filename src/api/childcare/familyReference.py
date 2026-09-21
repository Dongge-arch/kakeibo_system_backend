"""共有家族一覧参照 API。"""

from src.api.childcare.familyBase import FamilyBase
from src.common.functions.response import response


class FamilyReference(FamilyBase):
    """ユーザーの所属家族を取得する。"""

    def main(self, request_dict):
        """
        処理概要: 所属する家族とメンバーを参照する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 所属家族とメンバーを取得する。
          3. 一覧を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 家族一覧の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return response(200, self.list_families(user_id))
