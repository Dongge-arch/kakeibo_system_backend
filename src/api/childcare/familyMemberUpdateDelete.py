"""家族メンバー権限解除 API。"""

from src.api.childcare.familyBase import FamilyBase
from src.common.functions.response import response


class FamilyMemberUpdateDelete(FamilyBase):
    """家族の管理者だけがメンバーを解除する。"""

    def main(self, request_dict):
        """
        処理概要: 家族メンバーの共有権限を解除する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 管理者権限と対象メンバーを確認する。
          3. 解除結果を返す。

        Args:
            request_dict (dict): 家族 ID とユーザー ID を含むリクエスト。

        Returns:
            dict: 解除結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        body = request_dict.get("body") or {}
        return self.remove_member(user_id, body.get("familyId"), body.get("userId"))
