"""登録済み取引先を参照する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class InvoiceReference(MasterDataBase):
    """インボイス一覧の参照API。"""

    def main(self, request_dict):
        """
        処理概要: 登録済み取引先の一覧を取得する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 有効な取引先を照会する。
          3. ロゴURLを付けて返す。

        Args:
            request_dict: 認証情報。

        Returns:
            dict: 取引先一覧。
        """
        return self.list_invoice(self.require_user_id(request_dict))
