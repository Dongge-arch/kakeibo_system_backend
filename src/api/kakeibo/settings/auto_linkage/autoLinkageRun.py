"""自動連携手動実行 API。"""

from src.api.kakeibo.settings.auto_linkage.autoLinkageBase import AutoLinkageBase


class AutoLinkageRun(AutoLinkageBase):
    """選択された連携先の取り込みを手動で実行する。"""

    def main(self, request_dict):
        """
        処理概要: 自動連携先のデータを取り込む。
        処理内容:
          1. 認証済みユーザーと連携先を特定する。
          2. 連携先別の取り込み処理を実行する。
          3. 実行結果を返す。

        Args:
            request_dict (dict): 連携先を含む認証済みリクエスト。

        Returns:
            dict: 取り込み結果の API レスポンス。
        """
        body = request_dict.get("body") or {}
        return self.run_place(body, self.require_user_id(request_dict), request_dict)
