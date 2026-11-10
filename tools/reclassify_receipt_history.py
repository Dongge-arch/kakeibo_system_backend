# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""登録済みレシート明細を最新分類へ安全に再分類する保守ツール。"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.category_catalog import (  # noqa: E402
    LEGACY_EXPENSE_CATEGORY_REPLACEMENTS,
    refine_item_category,
)


PROGRAM_NAME = "ReclassifyReceiptHistory"
PRICE_COLUMNS = (
    "qty",
    "ut_pre",
    "to_pre",
    "ut_tax_excluded",
    "to_tax_excluded",
    "ut_tax_included",
    "to_tax_included",
)


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を取得する。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="再分類対象のユーザーID")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=ROOT.parent / "backups" / "receipt-reclassification",
        help="バックアップおよび結果レポートの出力先",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="指定時のみDBへ反映する。未指定時はドライランを行う。",
    )
    return parser.parse_args()


def select_details(connection: Any, user_id: str) -> list[dict[str, Any]]:
    """対象ユーザーの有効なレシート明細を取得する。"""
    sql = """
        SELECT
            d.id, d.ret_id, d.item_name, d.cat1, d.cat2, d.tax_rate,
            d.qty, d.ut, d.ut_pre, d.to_pre,
            d.ut_tax_excluded, d.to_tax_excluded,
            d.ut_tax_included, d.to_tax_included,
            d.cre_prog, d.upd_prog, d.cre_dt, d.cre_tm,
            d.upd_dt, d.upd_tm, d.cre_user_id, d.upd_user_id,
            d.del_flag, d.created_at
        FROM kakeibo.receipt_detail d
        WHERE d.cre_user_id = %(user_id)s
          AND d.del_flag = 0
          AND EXISTS (
              SELECT 1
              FROM kakeibo.receipt_info r
              WHERE r.ret_id = d.ret_id
                AND r.cre_user_id = d.cre_user_id
                AND r.del_flag = 0
          )
        ORDER BY d.id
    """
    return [dict(row) for row in connection.execute(sql, {"user_id": user_id}).fetchall()]


def select_valid_categories(connection: Any, user_id: str) -> set[tuple[str, str]]:
    """ユーザーが現在利用できる大分類と小分類の組み合わせを取得する。"""
    sql = """
        SELECT category1_name, category2_name
        FROM kakeibo.receipt_info_category2
        WHERE cre_user_id = %(user_id)s
          AND del_flag = 0
    """
    rows = connection.execute(sql, {"user_id": user_id}).fetchall()
    return {(str(row["category1_name"]), str(row["category2_name"])) for row in rows}


def build_change(
    detail: dict[str, Any],
    valid_categories: set[tuple[str, str]],
) -> dict[str, Any] | None:
    """一明細の再分類差分を作成する。変更不要の場合はNoneを返す。"""
    current_cat1 = str(detail.get("cat1") or "").strip() or "その他"
    current_cat2 = str(detail.get("cat2") or "").strip() or "未分類"
    current_pair = (current_cat1, current_cat2)
    is_legacy_transport = current_cat1 == "交通" and current_cat2 in {
        "ガソリン", "駐車場", "高速料金", "高速道路",
    }
    is_unresolved = current_cat1 in {"", "その他"} or current_cat2 in {"", "未分類", "その他"}
    # 2026-11-10 Codex: 確定済みの最新分類は保持し、旧分類と未分類だけを再判定する。
    if (
        current_pair not in LEGACY_EXPENSE_CATEGORY_REPLACEMENTS
        and not is_legacy_transport
        and not is_unresolved
    ):
        return None

    new_cat1, new_cat2, _suggested_tax_rate = refine_item_category(
        detail.get("item_name"),
        current_cat1,
        current_cat2,
        detail.get("tax_rate"),
    )
    if (new_cat1, new_cat2) not in valid_categories:
        fallback = ("その他", "未分類")
        if fallback not in valid_categories:
            raise ValueError(f"利用可能な分類に再分類先がありません: {new_cat1}/{new_cat2}")
        new_cat1, new_cat2 = fallback

    if current_pair == (new_cat1, new_cat2):
        return None
    return {
        "id": detail["id"],
        "ret_id": detail["ret_id"],
        "item_name": detail.get("item_name"),
        "old_cat1": detail.get("cat1"),
        "old_cat2": detail.get("cat2"),
        "old_tax_rate": detail.get("tax_rate"),
        "new_cat1": new_cat1,
        "new_cat2": new_cat2,
        "tax_rate": detail.get("tax_rate"),
    }


def build_changes(
    details: Iterable[dict[str, Any]],
    valid_categories: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    """全明細の再分類差分を作成する。"""
    changes = []
    for detail in details:
        change = build_change(detail, valid_categories)
        if change:
            changes.append(change)
    return changes


def select_immutable_metrics(connection: Any, user_id: str) -> dict[str, str]:
    """再分類で不変であるべき件数・数量・金額を文字列で取得する。"""
    sum_columns = ",\n".join(
        f"COALESCE(SUM(d.{column}), 0)::text AS {column}" for column in PRICE_COLUMNS
    )
    sql = f"""
        SELECT COUNT(*)::text AS detail_count, {sum_columns}
        FROM kakeibo.receipt_detail d
        WHERE d.cre_user_id = %(user_id)s
          AND d.del_flag = 0
          AND EXISTS (
              SELECT 1
              FROM kakeibo.receipt_info r
              WHERE r.ret_id = d.ret_id
                AND r.cre_user_id = d.cre_user_id
                AND r.del_flag = 0
          )
    """
    row = connection.execute(sql, {"user_id": user_id}).fetchone()
    return {key: str(value) for key, value in dict(row).items()}


def immutable_metrics_equal(before: dict[str, str], after: dict[str, str]) -> bool:
    """件数を厳密比較し、浮動小数点の集計誤差だけを許容する。"""
    if before.get("detail_count") != after.get("detail_count"):
        return False
    return all(
        math.isclose(float(before[column]), float(after[column]), rel_tol=0.0, abs_tol=0.000001)
        for column in PRICE_COLUMNS
    )


def write_json_with_hash(path: Path, payload: Any) -> str:
    """JSONを保存し、同時にSHA-256検証ファイルを作成する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="ascii",
    )
    return digest


def transition_summary(changes: Iterable[dict[str, Any]]) -> dict[str, int]:
    """分類変更の内訳を件数順で返す。"""
    counts = Counter(
        f"{row['old_cat1']}/{row['old_cat2']} -> {row['new_cat1']}/{row['new_cat2']}"
        for row in changes
    )
    return dict(counts.most_common())


def apply_changes(
    connection: Any,
    changes: list[dict[str, Any]],
    user_id: str,
) -> int:
    """楽観ロック付きで分類差分だけを更新する。"""
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    sql = """
        UPDATE kakeibo.receipt_detail
        SET cat1 = %(new_cat1)s,
            cat2 = %(new_cat2)s,
            upd_prog = %(upd_prog)s,
            upd_dt = %(upd_dt)s,
            upd_tm = %(upd_tm)s,
            upd_user_id = %(user_id)s
        WHERE id = %(id)s
          AND cre_user_id = %(user_id)s
          AND del_flag = 0
          AND cat1 IS NOT DISTINCT FROM %(old_cat1)s
          AND cat2 IS NOT DISTINCT FROM %(old_cat2)s
          AND tax_rate IS NOT DISTINCT FROM %(old_tax_rate)s
    """
    updated = 0
    # 2026-11-10 Codex: 途中更新や同時編集を検出するため、一件ずつ楽観条件を確認する。
    for change in changes:
        params = {
            **change,
            "upd_prog": PROGRAM_NAME,
            "upd_dt": now.strftime("%Y%m%d"),
            "upd_tm": now.strftime("%H%M%S"),
            "user_id": user_id,
        }
        rowcount = connection.execute(sql, params).rowcount
        if rowcount != 1:
            raise RuntimeError(f"同時更新を検出しました。明細ID: {change['id']}")
        updated += rowcount
    return updated


def validate_updated_categories(
    connection: Any,
    user_id: str,
    valid_categories: set[tuple[str, str]],
) -> None:
    """更新後の全明細が有効な分類を参照していることを確認する。"""
    details = select_details(connection, user_id)
    invalid = [
        row for row in details if (str(row.get("cat1")), str(row.get("cat2"))) not in valid_categories
    ]
    if invalid:
        raise RuntimeError(f"無効な分類が{len(invalid)}件残っています。")


def main() -> int:
    """ドライランまたはバックアップ付き再分類を実行する。"""
    args = parse_args()
    database_url = os.environ.get("KAKEIBO_DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("環境変数 KAKEIBO_DATABASE_URL を設定してください。")

    from psycopg import connect
    from psycopg.rows import dict_row

    timestamp = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d_%H%M%S")
    mode = "apply" if args.apply else "dry-run"
    with connect(database_url, row_factory=dict_row) as connection:
        # 2026-11-10 Codex: 実行中の追加登録を集計差分と誤認しないよう、同一スナップショットで検証する。
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        details = select_details(connection, args.user_id)
        valid_categories = select_valid_categories(connection, args.user_id)
        if not valid_categories:
            raise RuntimeError("有効な分類マスターがありません。")
        before_metrics = select_immutable_metrics(connection, args.user_id)
        changes = build_changes(details, valid_categories)
        report = {
            "executedAt": timestamp,
            "mode": mode,
            "userId": args.user_id,
            "detailCount": len(details),
            "changeCount": len(changes),
            "unchangedCount": len(details) - len(changes),
            "metrics": before_metrics,
            "transitions": transition_summary(changes),
            "changes": changes,
        }

        report_path = args.backup_dir / f"receipt_reclassification_{mode}_{timestamp}.json"
        if not args.apply:
            write_json_with_hash(report_path, report)
            connection.rollback()
            print(json.dumps({**report, "changes": changes[:20], "reportPath": str(report_path)}, ensure_ascii=False, indent=2, default=str))
            return 0

        # 2026-11-10 Codex: DB更新前に全有効明細を退避し、復元可能な状態を必ず確保する。
        backup_path = args.backup_dir / f"receipt_details_backup_{timestamp}.json"
        backup_digest = write_json_with_hash(
            backup_path,
            {
                "createdAt": timestamp,
                "userId": args.user_id,
                "metrics": before_metrics,
                "details": details,
            },
        )
        updated_count = apply_changes(connection, changes, args.user_id)
        after_metrics = select_immutable_metrics(connection, args.user_id)
        if not immutable_metrics_equal(before_metrics, after_metrics):
            raise RuntimeError("件数・数量・金額の不変条件に違反したためロールバックします。")
        validate_updated_categories(connection, args.user_id, valid_categories)
        connection.commit()

        report.update({
            "updatedCount": updated_count,
            "backupPath": str(backup_path),
            "backupSha256": backup_digest,
            "reportPath": str(report_path),
            "afterMetrics": after_metrics,
        })
        write_json_with_hash(report_path, report)
        print(json.dumps({**report, "changes": changes[:20]}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
