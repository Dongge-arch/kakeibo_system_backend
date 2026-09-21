"""小分類を削除する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class Category2UpdateDelete(MasterDataBase):
    """小分類の変更・削除API。"""

    def main(self, request_dict):
        """
        処理概要: 指定した小分類を論理削除する。
        処理内容:
          1. 認証済みユーザーと分類名を取得する。
          2. 本人の小分類を論理削除する。
          3. 削除結果を返す。

        Args:
            request_dict: 認証情報と分類名。

        Returns:
            dict: 削除結果。
        """
        return self.delete_category2(request_dict.get("body") or {}, self.require_user_id(request_dict))
