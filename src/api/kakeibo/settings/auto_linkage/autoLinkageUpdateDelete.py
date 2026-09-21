"""自動連携設定更新・削除 API。"""

from src.api.kakeibo.settings.auto_linkage.autoLinkageBase import AutoLinkageBase
from src.common.functions.response import response


class AutoLinkageUpdateDelete(AutoLinkageBase):
    """自動連携先の認証情報や有効状態を更新・削除する。"""

    def main(self, request_dict):
        """
        処理概要: 自動連携先の設定を更新または削除する。
        処理内容:
          1. 認証済みユーザーと連携先を特定する。
          2. 指定された操作で設定を変更する。
          3. 変更結果を返す。

        Args:
            request_dict (dict): 操作と連携先を含む認証済みリクエスト。

        Returns:
            dict: 更新または削除結果の API レスポンス。
        """
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        if body.get("action") == "update":
            return response(200, self.update_place(body, user_id))
        if body.get("action") == "delete":
            return response(200, self.delete_place(body, user_id))
        return response(400, {"errorMessage": "自動連携の操作が不正です。"})
