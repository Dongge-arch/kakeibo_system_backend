"""入金情報を更新または論理削除する。"""

from datetime import datetime

from src.common.api_utils import now_ymd_hms
from src.common.base import BaseRestApi
from src.common.functions.response import response


class IncomeUpdateDelete(BaseRestApi):
    """入金の更新・削除API。"""

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
        処理概要: 指定IDの入金情報を更新または論理削除する。
        処理内容:
          1. 認証済みユーザー、対象ID、操作種別を取得する。
          2. 更新時は入力日付と金額を既存DB形式へ変換する。
          3. 操作種別に対応するSQLを実行する。
          4. 処理結果を返す。

        Args:
            request_dict: 認証情報と更新・削除内容。

        Returns:
            dict: 更新または削除の結果。
        """
        user_id = self.require_user_id(request_dict)
        body = request_dict.get("body") or {}
        income_id = body.get("id")
        if not income_id:
            return response(400, {"errorMessage": "id is required"})
        ymd, hms = now_ymd_hms()
        params = {"ID": income_id, "CRE_USER_ID": user_id, "UPD_USER_ID": user_id, "UPD_DT": ymd, "UPD_TM": hms}
        action = body.get("action")
        if action == "delete":
            sql_name = "DELETE_SALARY_INFO"
        elif action == "update":
            sql_name = "UPDATE_SALARY_INFO"
            salary_date = body.get("salaryDate")
            params.update({
                "SAL_DATE": datetime.strptime(salary_date, "%Y-%m-%d").strftime("%Y%m%d") if salary_date else None,
                "SAL_NAME": body.get("salaryName"),
                "SAL_CAT": body.get("salaryCategory"),
                "SAL_AMT": body.get("salaryAmount"),
            })
        else:
            return response(400, {"errorMessage": "unknown income action"})
        self.database.execute(self.database.read_sql(sql_name, location=__file__), params)
        return response(200, {"message": "ok"})
