"""画像またはテキストからレシートを解析する。"""

from src.api.kakeibo.receipt.ai_receipt.aiReceiptBase import AiReceiptBase


class AiReceiptAnalyze(AiReceiptBase):
    """AI解析の入口。"""

    def main(self, request_dict):
        """
        処理概要: レシート解析と解析履歴の登録を行う。
        処理内容:
          1. 認証済みユーザーと画像・本文を取得する。
          2. AI解析を実行し、利用量を記録する。
          3. 正常な解析結果を履歴へ保存する。
          4. 結果と利用量を返す。

        Args:
            request_dict: 認証情報と解析対象。

        Returns:
            dict: 解析結果。
        """
        return self.analyze(request_dict.get("body") or {}, self.require_user_id(request_dict))
