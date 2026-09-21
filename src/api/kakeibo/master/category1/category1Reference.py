"""大分類を参照する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class Category1Reference(MasterDataBase):
    """大分類の参照API。"""

    def main(self, request_dict):
        """
        処理概要: ユーザーの大分類一覧を取得する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 有効な大分類を照会する。
          3. 一覧を返す。

        Args:
            request_dict: 認証情報。

        Returns:
            dict: 大分類一覧。
        """
        return self.list_category1(self.require_user_id(request_dict))
