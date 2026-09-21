"""入金履歴を参照する。"""

from datetime import datetime

from src.common.base import BaseRestApi
from src.common.functions.response import response


class IncomeReference(BaseRestApi):
    """入金の参照API。"""

    def __init__(self, db_path=None):
        """
        APIを初期化する。

        Args:
            db_path: 旧呼び出し互換のDB指定。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def main(self, request_dict):
        """
        処理概要: 指定された期間の入金履歴を取得する。
        処理内容:
          1. 認証済みユーザーと期間指定を取得する。
          2. 月、日付範囲、全件のいずれかのSQLを選ぶ。
          3. DBの日付形式を画面表示形式へ変換する。
          4. 入金履歴を返す。

        Args:
            request_dict: 認証情報と期間指定。

        Returns:
            dict: 入金履歴のレスポンス。
        """
        user_id = self.require_user_id(request_dict)
        body = request_dict.get("body") or {}
        params = {"CRE_USER_ID": user_id}
        if body.get("month"):
            sql_name = "SELECT_SALARY_INFO_MONTH"
            params["SAL_DATE"] = f"{body['month'].replace('-', '')}%"
        elif body.get("dateFrom") and body.get("dateTo"):
            sql_name = "SELECT_SALARY_INFO_RANGE"
            params["SAL_DATE"] = [
                datetime.strptime(body["dateFrom"], "%Y-%m-%d").strftime("%Y%m%d"),
                datetime.strptime(body["dateTo"], "%Y-%m-%d").strftime("%Y%m%d"),
            ]
        else:
            sql_name = "SELECT_SALARY_INFO"

        rows = self.database.select(self.database.read_sql(sql_name, location=__file__), params)
        records = []
        for row in rows:
            salary_date = row.get("SAL_DATE")
            if salary_date:
                salary_date = datetime.strptime(salary_date, "%Y%m%d").strftime("%Y-%m-%d")
            records.append({
                "id": row.get("ID"),
                "salaryDate": salary_date,
                "salaryName": row.get("SAL_NAME"),
                "salaryCategory": row.get("SAL_CAT"),
                "salaryAmount": row.get("SAL_AMT"),
            })
        return response(200, records)
