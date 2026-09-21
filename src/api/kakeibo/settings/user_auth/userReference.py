"""ログイン中ユーザー参照 API。"""

from src.api.kakeibo.settings.user_auth.userAuthBase import UserAuthBase


class UserReference(UserAuthBase):
    """保存済みセッションからユーザーを復元する。"""

    def main(self, request_dict):
        """
        処理概要: 認証中のユーザー情報を参照する。
        処理内容:
          1. 署名済みトークンを確認する。
          2. 最新のプロフィールを読み取る。
          3. ユーザー情報を返す。

        Args:
            request_dict (dict): トークンを含むリクエスト。

        Returns:
            dict: ユーザー情報の API レスポンス。
        """
        return self.me(request_dict.get("body") or {})
