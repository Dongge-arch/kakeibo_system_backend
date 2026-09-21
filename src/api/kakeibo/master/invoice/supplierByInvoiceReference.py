"""登録番号から取引先を参照する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class SupplierByInvoiceReference(MasterDataBase):
    """インボイス登録番号による参照API。"""

    def main(self, request_dict):
        """
        処理概要: 登録番号に対応する取引先を取得する。
        処理内容:
          1. 認証済みユーザーと登録番号を取得する。
          2. 登録番号を正規化して照会する。
          3. ロゴ・税区分を含めて返す。

        Args:
            request_dict: 認証情報と登録番号。

        Returns:
            dict: 取引先情報。
        """
        return self.supplier_by_invoice(request_dict.get("body") or {}, self.require_user_id(request_dict))
