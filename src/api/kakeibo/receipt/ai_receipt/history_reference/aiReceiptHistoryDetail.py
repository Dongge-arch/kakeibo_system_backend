"""一件のAIレシート解析履歴を参照する。"""

from src.api.kakeibo.receipt.ai_receipt.aiReceiptBase import AiReceiptBase
from src.common.functions.response import response


class AiReceiptHistoryDetail(AiReceiptBase):
    """解析履歴詳細の入口。"""

    def main(self, request_dict):
        """
        処理概要: 指定した解析履歴を取得する。
        処理内容:
          1. 認証済みユーザーと解析IDを取得する。
          2. 本人が所有する履歴だけを照会する。
          3. 解析内容と確認結果を返す。

        Args:
            request_dict: 認証情報と解析ID。

        Returns:
            dict: 解析履歴詳細。
        """
        body = request_dict.get("body") or {}
        return response(200, self.get_history(body.get("analysisId"), self.require_user_id(request_dict)))
