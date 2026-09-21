"""確認済みレシートを解析履歴へ保存する。"""

from src.api.kakeibo.receipt.ai_receipt.aiReceiptBase import AiReceiptBase


class AiReceiptHistoryFinal(AiReceiptBase):
    """解析履歴の確定入口。"""

    def main(self, request_dict):
        """
        処理概要: 確認・編集済みのレシートを保存する。
        処理内容:
          1. 認証済みユーザーと確定内容を取得する。
          2. 対象履歴の所有権を確認する。
          3. 確定内容と保存状態を更新する。
          4. 処理結果を返す。

        Args:
            request_dict: 認証情報と確定レシート。

        Returns:
            dict: 確定結果。
        """
        return self.save_final_receipt(request_dict.get("body") or {}, self.require_user_id(request_dict))
