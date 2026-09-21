"""登録済み取引先を更新または削除する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase
from src.common.functions.response import response


class InvoiceUpdateDelete(MasterDataBase):
    """インボイスの更新・削除API。"""

    def main(self, request_dict):
        """
        処理概要: 登録済み取引先を更新または論理削除する。
        処理内容:
          1. 認証済みユーザーと操作種別を取得する。
          2. 更新時は名称・税区分・ロゴを保存する。
          3. 削除時は対象を論理削除する。
          4. 処理結果を返す。

        Args:
            request_dict: 認証情報と取引先の変更内容。

        Returns:
            dict: 更新または削除の結果。
        """
        body = request_dict.get("body") or {}
        user_id = self.require_user_id(request_dict)
        if body.get("action") == "update":
            return self.update_invoice(body, user_id)
        if body.get("action") == "delete":
            return self.delete_invoice(body, user_id)
        return response(400, {"errorMessage": "unknown invoice action"})
