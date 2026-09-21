"""赤ちゃんプロフィール更新・削除 API。"""

from src.api.childcare.babyBase import BabyBase
from src.common.functions.response import response


class BabyUpdateDelete(BabyBase):
    """既存の赤ちゃん情報を変更または削除する。"""

    def main(self, request_dict):
        """
        処理概要: 赤ちゃんのプロフィールを更新または削除する。
        処理内容:
          1. ユーザーの認証を確認する。
          2. 家族所属と操作対象を検証する。
          3. 更新または削除結果を返す。

        Args:
            request_dict (dict): 操作と赤ちゃん ID を含むリクエスト。

        Returns:
            dict: 更新または削除結果の API レスポンス。
        """
        user_id = self.require_verified_user_id(request_dict)
        if not user_id or user_id == "__anonymous__":
            return response(401, {"errorMessage": "ログインしてください。"})
        body = request_dict.get("body") or {}
        if body.get("action") == "save_baby":
            return self.save_baby(user_id, body.get("baby") or {})
        if body.get("action") == "delete_baby":
            return self.delete_baby(user_id, body.get("babyId"))
        return response(400, {"errorMessage": "unknown baby action"})
