"""プロフィール更新 API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class UserProfileUpdate(UserAuthBase):
    """認証済みユーザー自身のプロフィールだけを変更する。"""

    def main(self, request_dict):
        """
        処理概要: ログインユーザーのプロフィールを更新する。
        処理内容:
          1. トークンからユーザーを特定する。
          2. 表示名とアイコンを検証して保存する。
          3. 更新後のセッションを返す。

        Args:
            request_dict (dict): トークンとプロフィールを含むリクエスト。

        Returns:
            dict: 更新結果の API レスポンス。
        """
        return self.update_profile(request_dict.get("body") or {})
