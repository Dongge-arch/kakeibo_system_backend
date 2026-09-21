"""パスワード再設定確定 API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class PasswordResetConfirm(UserAuthBase):
    """有効な再設定コードを使ってパスワードを更新する。"""

    def main(self, request_dict):
        """
        処理概要: パスワードを再設定する。
        処理内容:
          1. 再設定コードと新しいパスワードを確認する。
          2. アカウントのパスワードを更新する。
          3. 更新結果を返す。

        Args:
            request_dict (dict): 再設定コードを含むリクエスト。

        Returns:
            dict: 更新結果の API レスポンス。
        """
        return self.reset_password(request_dict.get("body") or {})
