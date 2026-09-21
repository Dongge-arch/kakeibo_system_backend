"""パスワード再設定申請 API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class PasswordResetRequest(UserAuthBase):
    """期限付きのパスワード再設定コードを発行する。"""

    def main(self, request_dict):
        """
        処理概要: パスワード再設定コードを申請する。
        処理内容:
          1. メールアドレスを検証する。
          2. 対象アカウントがあれば再設定コードを発行する。
          3. 申請結果を返す。

        Args:
            request_dict (dict): メールアドレスを含むリクエスト。

        Returns:
            dict: 申請結果の API レスポンス。
        """
        return self.request_password_reset(request_dict.get("body") or {})
