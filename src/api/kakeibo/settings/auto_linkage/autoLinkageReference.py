"""自動連携一覧参照 API。"""

from src.api.kakeibo.settings.auto_linkage.autoLinkageBase import AutoLinkageBase
from src.common.functions.response import response


class AutoLinkageReference(AutoLinkageBase):
    """利用できる連携先とユーザーの設定を一覧表示する。"""

    def main(self, request_dict):
        """
        処理概要: 自動連携先を一覧表示する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 連携先ごとの設定を取得する。
          3. 一覧を返す。

        Args:
            request_dict (dict): 認証済みリクエスト。

        Returns:
            dict: 自動連携一覧の API レスポンス。
        """
        return response(200, self.list_places(self.require_user_id(request_dict)))
