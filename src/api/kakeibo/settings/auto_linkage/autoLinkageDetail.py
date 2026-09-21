"""自動連携先詳細参照 API。"""

from src.api.kakeibo.settings.auto_linkage.autoLinkageBase import AutoLinkageBase
from src.common.functions.response import response


class AutoLinkageDetail(AutoLinkageBase):
    """一つの連携先の設定を参照する。"""

    def main(self, request_dict):
        """
        処理概要: 指定された連携先を参照する。
        処理内容:
          1. 認証済みユーザーを特定する。
          2. 指定された連携先を取得する。
          3. 詳細を返す。

        Args:
            request_dict (dict): 連携先を含む認証済みリクエスト。

        Returns:
            dict: 連携先詳細の API レスポンス。
        """
        return response(200, self.get_place(request_dict.get("body") or {}, self.require_user_id(request_dict)))
