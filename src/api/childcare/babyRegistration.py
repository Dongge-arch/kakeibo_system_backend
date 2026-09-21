"""赤ちゃんプロフィール登録 API。"""

from src.api.childcare.babyBase import BabyBase
from src.common.functions.response import response


class BabyRegistration(BabyBase):
    """家族の赤ちゃん情報を新規登録する。"""

    def main(self, request_dict):
        """
        処理概要: 赤ちゃんのプロフィールを登録する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 家族所属とプロフィールを検証して保存する。
          3. 赤ちゃん ID を返す。

        Args:
            request_dict (dict): 赤ちゃん情報を含むリクエスト。

        Returns:
            dict: 登録結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        return self.save_baby(user_id, (request_dict.get("body") or {}).get("baby") or {})
