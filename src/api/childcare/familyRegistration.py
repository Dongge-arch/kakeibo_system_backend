"""共有家族登録 API。"""

from src.api.childcare.familyBase import FamilyBase
from src.common.functions.response import response


class FamilyRegistration(FamilyBase):
    """家族スペースを作成する。"""

    def main(self, request_dict):
        """
        処理概要: 家族共有スペースを作成する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 家族名を検証して保存する。
          3. 家族 ID を返す。

        Args:
            request_dict (dict): 家族名を含むリクエスト。

        Returns:
            dict: 作成結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return self.create_family(user_id, request_dict.get("body") or {})
