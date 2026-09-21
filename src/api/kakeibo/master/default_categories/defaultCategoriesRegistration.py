"""標準分類を登録する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class DefaultCategoriesRegistration(MasterDataBase):
    """標準分類の一括登録API。"""

    def main(self, request_dict):
        """
        処理概要: 指定された標準分類を重複なく追加する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 既存分類と入力分類を比較する。
          3. 未登録の分類のみ保存し結果を返す。

        Args:
            request_dict: 認証情報と標準分類。

        Returns:
            dict: 登録結果。
        """
        return self.add_default_categories(request_dict.get("body") or {}, self.require_user_id(request_dict))
