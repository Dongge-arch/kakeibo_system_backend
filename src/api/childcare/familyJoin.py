"""家族招待参加 API。"""

from src.api.childcare.familyBase import FamilyBase
from src.common.functions.response import response


class FamilyJoin(FamilyBase):
    """有効な招待コードで家族に参加する。"""

    def main(self, request_dict):
        """
        処理概要: 招待された家族に参加する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 招待コードを照合して消費する。
          3. 参加した家族 ID を返す。

        Args:
            request_dict (dict): 招待コードを含むリクエスト。

        Returns:
            dict: 参加結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return self.join_family(user_id, (request_dict.get("body") or {}).get("code"))
