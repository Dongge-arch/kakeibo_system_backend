"""自動連携先のログイン情報確認 API。"""

from src.api.kakeibo.settings.auto_linkage.autoLinkageBase import AutoLinkageBase
from src.common.functions.response import response


class AutoLinkageLogin(AutoLinkageBase):
    """保存済みのログイン情報が利用できるか確認する。"""

    def main(self, request_dict):
        """
        処理概要: 連携先のログイン情報を確認する。
        処理内容:
          1. 認証済みユーザーと連携先を特定する。
          2. 保存された会員 ID とパスワードを検証する。
          3. 確認結果を返す。

        Args:
            request_dict (dict): 連携先を含む認証済みリクエスト。

        Returns:
            dict: ログイン情報確認の API レスポンス。
        """
        return response(200, self.login_place(request_dict.get("body") or {}, self.require_user_id(request_dict)))
