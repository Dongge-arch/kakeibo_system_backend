# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""EventBridge から有効な自動入力サービスを実行するスケジューラ。"""

from src.batch.auto_input_targets.auto_input_belc.autoInput_Belc import AutoInput_Belc
from src.batch.auto_input_targets.auto_input_etc.autoInput_Etc import AutoInput_Etc
from src.common.base.base_auto_input import BaseAutoInput
from src.common.functions.response import response


AUTO_INPUT_BATCHES = {
    "BELC": AutoInput_Belc,
    "ETC": AutoInput_Etc,
}


class AutoInputScheduler(BaseAutoInput):
    """自動入力を有効化したユーザーごとに対応バッチを実行する。"""

    def __init__(self, db_path=None):
        """
        自動入力スケジューラを初期化する。

        Args:
            db_path (Optional[str]): ローカル実行時に使用するDBパス。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def main(self, request_dict):
        """
        有効なBELC/ETC設定を取得し、ユーザー単位で自動入力を実行する。

        Args:
            request_dict (dict): EventBridgeイベントを正規化したリクエスト情報。

        Returns:
            dict: 実行件数とサービス別結果を含むレスポンス。
        """
        rows = self.database.select(
            """
            SELECT CRE_USER_ID, CONNECTION_TYPE
            FROM kakeibo.auto_input_info
            WHERE ENABLED = 1
              AND CONNECTION_TYPE IN ('BELC', 'ETC')
              AND COALESCE(LOGIN_ID_1, '') <> ''
              AND COALESCE(LOGIN_PW_1, '') <> ''
              AND DEL_FLAG = 0
            ORDER BY CRE_USER_ID, CONNECTION_TYPE
            """
        )
        results = []
        succeeded = 0
        failed = 0

        for row in rows:
            user_id = str(self.value(row, "CRE_USER_ID", "cre_user_id") or "")
            connection_type = str(
                self.value(row, "CONNECTION_TYPE", "connection_type") or ""
            ).upper()
            batch_class = AUTO_INPUT_BATCHES.get(connection_type)
            if not user_id or batch_class is None:
                continue

            batch_result = batch_class().call(
                body={"action": "scheduled"},
                headers={"x-kakeibo-user-id": user_id},
            )
            status_code = int(batch_result.get("statusCode", 500))
            if status_code < 400:
                succeeded += 1
            else:
                failed += 1
            results.append({
                "userId": user_id,
                "connectionType": connection_type,
                "statusCode": status_code,
                "body": batch_result.get("body") or {},
            })

        return response(200, {
            "targetCount": len(results),
            "succeededCount": succeeded,
            "failedCount": failed,
            "results": results,
        })
