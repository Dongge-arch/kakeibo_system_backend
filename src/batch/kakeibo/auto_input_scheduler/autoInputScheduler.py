# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""EventBridge から有効な自動入力サービスを実行するスケジューラ。"""

from src.batch.kakeibo.auto_input_targets.auto_input_belc.autoInput_Belc import AutoInput_Belc
from src.batch.kakeibo.auto_input_targets.auto_input_etc.autoInput_Etc import AutoInput_Etc
from src.batch.kakeibo.auto_input_targets.auto_input_amazon.autoInput_Amazon import AutoInput_Amazon
from src.common.base.base_auto_input import BaseAutoInput
from src.common.functions.response import response


AUTO_INPUT_BATCHES = {
    "BELC": AutoInput_Belc,
    "ETC": AutoInput_Etc,
    "AMAZON": AutoInput_Amazon,
}

DEFAULT_AUTO_INPUT_CONNECTIONS = ("BELC", "ETC")
SERVER_AUTO_INPUT_CONNECTIONS = ("BELC", "ETC", "AMAZON")


class AutoInputScheduler(BaseAutoInput):
    """自動入力を有効化したユーザーごとに対応バッチを実行する。"""

    def __init__(self, db_path=None):
        """
        自動入力スケジューラを初期化する。

        Args:
            db_path (Optional[str]): ローカル実行時に使用するDBパス。

        Returns:
            None: 戻り値なし。
        """
        super().__init__(class_name=self.__class__.__name__, db_path=db_path)

    def main(self, request_dict):
        """
        処理概要: 有効な自動入力をユーザー別に実行する。
        処理内容:
          1. 実行対象の連携先を決める。
          2. 有効な連携設定を照会する。
          3. 連携先ごとにバッチを実行する。
          4. 成功・失敗件数を返す。

        Args:
            request_dict (dict): EventBridgeイベントを正規化したリクエスト情報。

        Returns:
            dict: 実行件数とサービス別結果を含むレスポンス。
        """
        target_connections = self.resolve_target_connections(request_dict.get("body") or {})
        rows = self.database.select(
            self.database.read_sql("SELECT_KAKEIBO_AUTO_INPUT_INFO", location=__file__),
            {"CONNECTION_TYPE": list(target_connections)},
        )
        results = []
        succeeded = 0
        failed = 0
        unavailable_connections = set()

        for row in rows:
            user_id = str(self.value(row, "CRE_USER_ID", "cre_user_id") or "")
            connection_type = str(
                self.value(row, "CONNECTION_TYPE", "connection_type") or ""
            ).upper()
            batch_class = AUTO_INPUT_BATCHES.get(connection_type)
            if not user_id or batch_class is None:
                continue

            if connection_type in unavailable_connections:
                # 2026-06-28 Codex: 同一スケジュール内で外部サイト障害を検知したら、同サイトへの連続アクセスを止める。
                batch_result = {
                    "statusCode": 503,
                    "body": {
                        "errorCode": "1000062",
                        "errorMessage": f"{connection_type} service is temporarily unavailable; skipped in this run.",
                    },
                }
            else:
                batch_result = batch_class().call(
                    body={"action": "scheduled"},
                    headers={"x-kakeibo-user-id": user_id},
                )
            status_code = int(batch_result.get("statusCode", 500))
            body = batch_result.get("body") or {}
            if connection_type == "BELC" and status_code == 503:
                unavailable_connections.add(connection_type)
            batch_failed_count = int(body.get("failed") or 0)
            batch_registered_count = int(body.get("registered") or 0)
            body_ok = body.get("ok")
            # 2026-07-15 Codex: サーバー実行ではAmazon等の追加認証待ちを成功扱いにしないよう、ok=falseを失敗として集計する。
            is_batch_success = status_code < 400 and body_ok is not False and (
                batch_failed_count == 0 or batch_registered_count > 0
            )
            if is_batch_success:
                succeeded += 1
            else:
                failed += 1
            results.append({
                "userId": user_id,
                "connectionType": connection_type,
                "statusCode": status_code,
                "body": body,
            })

        return response(200, {
            "targetCount": len(results),
            "succeededCount": succeeded,
            "failedCount": failed,
            "connectionTypes": list(target_connections),
            "results": results,
        })

    def resolve_target_connections(self, body):
        """
        実行対象の連携種別を決定する。
        Args:
            body (dict): サーバー実行時に渡された実行条件。
        Returns:
            tuple[str, ...]: 実行対象の連携種別。
        """
        requested = body.get("connectionTypes") or body.get("connectionType")
        if not requested:
            if body.get("source") == "armbian-server":
                return SERVER_AUTO_INPUT_CONNECTIONS
            return DEFAULT_AUTO_INPUT_CONNECTIONS
        if isinstance(requested, str):
            candidates = [value.strip().upper() for value in requested.split(",")]
        else:
            candidates = [str(value).strip().upper() for value in requested]
        # 2026-07-15 Codex: サーバー移行中も未対応の連携種別を誤実行しないよう、実装済みバッチだけに絞る。
        filtered = tuple(value for value in candidates if value in AUTO_INPUT_BATCHES)
        return filtered or DEFAULT_AUTO_INPUT_CONNECTIONS
