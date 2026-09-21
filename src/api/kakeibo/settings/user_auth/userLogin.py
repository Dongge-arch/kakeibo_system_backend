"""ログイン API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class UserLogin(UserAuthBase):
    """ユーザーを認証してセッションを発行する。"""

    def main(self, request_dict):
        """
        処理概要: メールアドレスとパスワードでログインする。
        処理内容:
          1. 入力された認証情報を検証する。
          2. 登録済みユーザーと照合する。
          3. セッションを返す。

        Args:
            request_dict (dict): 認証情報を含むリクエスト。

        Returns:
            dict: セッションまたはエラーの API レスポンス。
        """
        return self.login(request_dict.get("body") or {})
