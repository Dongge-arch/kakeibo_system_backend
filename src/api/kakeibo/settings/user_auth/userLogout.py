"""ログアウト API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class UserLogout(UserAuthBase):
    """クライアントのログアウト要求に応答する。"""

    def main(self, request_dict):
        """
        処理概要: ログアウト結果を返す。
        処理内容:
          1. ログアウト要求を受け取る。
          2. クライアントへ完了を通知する。

        Args:
            request_dict (dict): ログアウト要求。

        Returns:
            dict: ログアウト結果の API レスポンス。
        """
        return self.logout(request_dict.get("body") or {})
