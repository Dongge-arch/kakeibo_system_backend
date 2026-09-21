"""アカウント登録 API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class UserRegistration(UserAuthBase):
    """メールアドレスとパスワードで新規ユーザーを登録する。"""

    def main(self, request_dict):
        """
        処理概要: 新しいユーザーを登録する。
        処理内容:
          1. メールアドレスとパスワードを検証する。
          2. ユーザー情報を保存する。
          3. ログイン情報を返す。

        Args:
            request_dict (dict): 登録情報を含むリクエスト。

        Returns:
            dict: 登録結果の API レスポンス。
        """
        return self.register(request_dict.get("body") or {})
