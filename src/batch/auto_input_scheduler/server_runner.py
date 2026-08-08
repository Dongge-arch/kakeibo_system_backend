# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""Armbianサーバー上で自動入力バッチを実行するCLI入口。"""

import argparse
import json
import sys

from src.batch.auto_input_scheduler.autoInputScheduler import AutoInputScheduler


def parse_args():
    """CLI引数を解析する。"""
    parser = argparse.ArgumentParser(
        description="Home Kakeibo auto input batch runner for Armbian server."
    )
    parser.add_argument(
        "--connection-types",
        default="BELC,ETC,AMAZON",
        help="実行対象の連携種別。例: BELC,ETC,AMAZON",
    )
    parser.add_argument(
        "--schedule-name",
        default="daily-midnight",
        help="実行元を識別する任意のスケジュール名。",
    )
    return parser.parse_args()


def main():
    """AutoInputSchedulerをCLIから実行し、結果をJSONで標準出力へ返す。"""
    args = parse_args()
    connection_types = [
        value.strip().upper()
        for value in args.connection_types.split(",")
        if value.strip()
    ]
    # 2026-07-15 Codex: Lambda以外からも同じ業務ロジックを使えるよう、bodyだけで実行条件を渡す。
    result = AutoInputScheduler().call(
        body={
            "source": "armbian-server",
            "scheduleName": args.schedule_name,
            "connectionTypes": connection_types,
        },
        headers={},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    status_code = int(result.get("statusCode", 500))
    body = result.get("body") or {}
    failed_count = int(body.get("failedCount") or 0)
    return 0 if status_code < 400 and failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
