"""赤ちゃんプロフィール一覧参照 API。"""

from src.api.childcare.babyBase import BabyBase
from src.common.functions.response import response


class BabyReference(BabyBase):
    """所属家族の赤ちゃん情報を一覧表示する。"""

    def main(self, request_dict):
        """
        処理概要: 家族の赤ちゃんプロフィールを参照する。
        処理内容:
          1. ユーザーの認証と家族所属を確認する。
          2. 対象家族の赤ちゃん情報を取得する。
          3. 一覧を返す。

        Args:
            request_dict (dict): 家族 ID を含むリクエスト。

        Returns:
            dict: 赤ちゃん一覧の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        family_id = (request_dict.get("body") or {}).get("familyId")
        if not self.is_member(user_id, family_id):
            return response(403, {"errorMessage": "家族へのアクセス権がありません。"})
        return response(200, self.list_babies(family_id))
