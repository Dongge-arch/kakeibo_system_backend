"""入金分類を参照する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class SalaryCategoryReference(MasterDataBase):
    """入金分類の参照API。"""

    def main(self, request_dict):
        """
        処理概要: ユーザーの入金分類一覧を取得する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 有効な入金分類を照会する。
          3. 一覧を返す。

        Args:
            request_dict: 認証情報。

        Returns:
            dict: 入金分類一覧。
        """
        return self.list_salary_category(self.require_user_id(request_dict))
