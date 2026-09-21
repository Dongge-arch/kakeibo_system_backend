"""AIレシートの利用量を参照する。"""

from src.api.kakeibo.receipt.ai_receipt.aiReceiptBase import AiReceiptBase
from src.common.functions.response import response


class AiReceiptUsageReference(AiReceiptBase):
    """AI利用量参照の入口。"""

    def main(self, request_dict):
        """
        処理概要: ユーザー本人のAI利用量を取得する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 利用履歴を集計する。
          3. 集計結果を返す。

        Args:
            request_dict: 認証情報。

        Returns:
            dict: AI利用量の集計結果。
        """
        return response(200, self.usage_summary(self.require_user_id(request_dict)))
