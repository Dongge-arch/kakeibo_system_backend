"""家族招待コード発行 API。"""

from src.api.childcare.familyBase import FamilyBase
from src.common.functions.response import response


class FamilyInviteRegistration(FamilyBase):
    """家族の管理者に招待コードを発行する。"""

    def main(self, request_dict):
        """
        処理概要: 家族招待コードを発行する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 対象家族の管理者権限を確認する。
          3. 招待コードを返す。

        Args:
            request_dict (dict): 家族 ID を含むリクエスト。

        Returns:
            dict: 招待コードの API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return self.create_invite(user_id, (request_dict.get("body") or {}).get("familyId"))
