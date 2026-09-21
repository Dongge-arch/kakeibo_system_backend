"""入金情報を新規登録する。"""

from datetime import datetime

from src.common.api_utils import now_ymd_hms
from src.common.base import BaseRestApi
from src.common.functions.response import response


class NewIncomeRegistration(BaseRestApi):
    """入金の新規登録API。"""

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
        処理概要: 入金情報を一件登録する。
        処理内容:
          1. 認証済みユーザーと入力値を取得する。
          2. 日付・時刻を既存テーブルの形式へ変換する。
          3. 登録日時とユーザーIDを付けて保存する。
          4. 登録結果を返す。

        Args:
            request_dict: 認証情報とリクエスト本文。

        Returns:
            dict: 登録結果。
        """
        user_id = self.require_user_id(request_dict)
        request_body = request_dict.get("body") or {}
        body = request_body.get("salaryInfo") if isinstance(request_body.get("salaryInfo"), dict) else request_body
        salary_time = body.get("salaryTime") or ""
        salary_date = body.get("salaryDate")
        if salary_time and len(str(salary_time)) == 5:
            salary_time = datetime.strptime(salary_time, "%H:%M").strftime("%H%M%S")
        if salary_date:
            salary_date = datetime.strptime(salary_date, "%Y-%m-%d").strftime("%Y%m%d")

        ymd, hms = now_ymd_hms()
        # 監査列には登録者・更新者をそれぞれの列名で渡す。
        self.database.insert(
            self.database.read_sql("INSERT_SALARY_INFO", location=__file__),
            {
                "CRE_PROG": "SalaryRegistrationNew",
                "UPD_PROG": "SalaryRegistrationNew",
                "SAL_DATE": salary_date,
                "SAL_NAME": body.get("salaryName"),
                "SAL_CAT": body.get("salaryCategory"),
                "SAL_SUB_CAT": "",
                "SAL_COMMENT": body.get("salaryComment"),
                "SAL_AMT": body.get("salaryAmount"),
                "CRE_DT": ymd,
                "CRE_TM": hms,
                "UPD_DT": ymd,
                "UPD_TM": hms,
                "CRE_USER_ID": user_id,
                "UPD_USER_ID": user_id,
                "DEL_FLAG": 0,
            },
        )
        return response(201, {"message": "入金項目は正しく登録しました。"})
