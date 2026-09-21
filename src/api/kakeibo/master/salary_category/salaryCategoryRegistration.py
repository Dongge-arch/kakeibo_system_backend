"""入金分類を登録する。"""

from src.api.kakeibo.master.master_data.masterDataBase import MasterDataBase


class SalaryCategoryRegistration(MasterDataBase):
    """入金分類の新規登録API。"""

    def main(self, request_dict):
        """
        処理概要: 入金分類を追加する。
        処理内容:
          1. 認証済みユーザーを取得する。
          2. 分類名を検証して登録する。
          3. 登録結果を返す。

        Args:
            request_dict: 認証情報と分類名。

        Returns:
            dict: 登録結果。
        """
        return self.add_salary_category(request_dict.get("body") or {}, self.require_user_id(request_dict))
