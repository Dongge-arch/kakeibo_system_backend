"""AIレシート解析履歴を参照する。"""

from src.api.kakeibo.receipt.ai_receipt.aiReceiptBase import AiReceiptBase
from src.common.functions.response import response


class AiReceiptHistoryReference(AiReceiptBase):
    """解析履歴一覧の入口。"""

    def main(self, request_dict):
        """
        処理概要: ユーザー本人の解析履歴一覧を取得する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 履歴を新しい順に照会する。
          3. 一覧を返す。

        Args:
            request_dict: 認証情報。

        Returns:
            dict: 解析履歴一覧。
        """
        return response(200, self.list_history(self.require_user_id(request_dict)))
