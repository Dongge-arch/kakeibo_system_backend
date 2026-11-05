# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

"""既存の商品分類と店舗分類を拡張版マスタへ安全に移行する。"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import uuid

import psycopg
from psycopg.rows import dict_row


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.common.category_catalog import (  # noqa: E402
    DEFAULT_EXPENSE_CATEGORIES,
    PLACE_CATEGORIES,
    classify_supplier_category,
    refine_item_category,
)


MIGRATION_PROGRAM = "CategoryMigration20261106"
BACKUP_TABLES = (
    "invoice_registration",
    "receipt_detail",
    "receipt_info_category1",
    "receipt_info_category2",
)
LEGACY_PLACE_CATEGORIES = {
    "コンビニ", "スーパー", "ドラッグストア", "飲食", "ネット通販",
    "交通", "公共料金", "その他",
}
MANAGED_PLACE_CATEGORIES = set(PLACE_CATEGORIES) | LEGACY_PLACE_CATEGORIES


def parse_args() -> argparse.Namespace:
    """コマンドライン引数を取得する。"""
    parser = argparse.ArgumentParser(description="商品・店舗分類の拡張と既存データ移行")
    parser.add_argument("--apply", action="store_true", help="DBへ反映する。省略時はロールバックして件数だけ表示する。")
    parser.add_argument("--user-id", action="append", default=[], help="対象ユーザーID。複数回指定可能。")
    return parser.parse_args()


def active_user_ids(connection: psycopg.Connection, selected: list[str]) -> list[str]:
    """データを持つ有効ユーザー、または明示指定されたユーザーを返す。"""
    if selected:
        rows = connection.execute(
            """
            SELECT USER_ID
            FROM kakeibo.USER_INFO
            WHERE COALESCE(DEL_FLAG, 0) = 0 AND USER_ID = ANY(%s)
            ORDER BY ID
            """,
            (selected,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT U.USER_ID
            FROM kakeibo.USER_INFO U
            WHERE COALESCE(U.DEL_FLAG, 0) = 0
              AND (
                EXISTS (SELECT 1 FROM kakeibo.RECEIPT_DETAIL D WHERE D.CRE_USER_ID = U.USER_ID)
                OR EXISTS (SELECT 1 FROM kakeibo.INVOICE_REGISTRATION I WHERE I.CRE_USER_ID = U.USER_ID)
              )
            ORDER BY U.ID
            """
        ).fetchall()
    return [str(row["user_id"]) for row in rows]


def ensure_backup_schema(connection: psycopg.Connection) -> None:
    """移行前データを保存する共通バックアップ表を準備する。"""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS kakeibo.CATEGORY_MIGRATION_BACKUP (
            ID BIGSERIAL PRIMARY KEY,
            MIGRATION_ID TEXT NOT NULL,
            TABLE_NAME TEXT NOT NULL,
            ROW_ID BIGINT NOT NULL,
            USER_ID TEXT NOT NULL,
            BEFORE_DATA JSONB NOT NULL,
            CREATED_AT TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (MIGRATION_ID, TABLE_NAME, ROW_ID)
        )
        """
    )


def backup_user_rows(connection: psycopg.Connection, migration_id: str, user_id: str) -> dict[str, int]:
    """更新対象ユーザーの分類関連データを行単位で保存する。"""
    counts: dict[str, int] = {}
    for table_name in BACKUP_TABLES:
        result = connection.execute(
            f"""
            INSERT INTO kakeibo.CATEGORY_MIGRATION_BACKUP
                (MIGRATION_ID, TABLE_NAME, ROW_ID, USER_ID, BEFORE_DATA)
            SELECT %s, %s, SOURCE.ID, %s, TO_JSONB(SOURCE)
            FROM kakeibo.{table_name} SOURCE
            WHERE SOURCE.CRE_USER_ID = %s
            ON CONFLICT (MIGRATION_ID, TABLE_NAME, ROW_ID) DO NOTHING
            """,
            (migration_id, table_name, user_id, user_id),
        )
        counts[table_name] = result.rowcount
    return counts


def insert_master_row(
    connection: psycopg.Connection,
    table_name: str,
    user_id: str,
    category1: str,
    category2: str | None = None,
    tax_rate: float | None = None,
) -> bool:
    """分類マスタを重複させずに追加し、削除済みなら再有効化する。"""
    if table_name == "receipt_info_category1":
        existing = connection.execute(
            """
            SELECT ID, COALESCE(DEL_FLAG, 0) AS DEL_FLAG
            FROM kakeibo.RECEIPT_INFO_CATEGORY1
            WHERE CRE_USER_ID = %s AND CATEGORY1_NAME = %s
            ORDER BY COALESCE(DEL_FLAG, 0), ID LIMIT 1
            """,
            (user_id, category1),
        ).fetchone()
    else:
        existing = connection.execute(
            """
            SELECT ID, COALESCE(DEL_FLAG, 0) AS DEL_FLAG
            FROM kakeibo.RECEIPT_INFO_CATEGORY2
            WHERE CRE_USER_ID = %s AND CATEGORY1_NAME = %s AND CATEGORY2_NAME = %s
            ORDER BY COALESCE(DEL_FLAG, 0), ID LIMIT 1
            """,
            (user_id, category1, category2),
        ).fetchone()

    now = datetime.now()
    if existing:
        if int(existing["del_flag"] or 0) == 0:
            return False
        connection.execute(
            f"""
            UPDATE kakeibo.{table_name}
            SET DEL_FLAG = 0, UPD_PROG = %s, UPD_DT = %s, UPD_TM = %s, UPD_USER_ID = %s
            WHERE ID = %s
            """,
            (MIGRATION_PROGRAM, now.strftime("%Y%m%d"), now.strftime("%H%M%S"), user_id, existing["id"]),
        )
        return True

    common = (
        MIGRATION_PROGRAM,
        MIGRATION_PROGRAM,
        now.strftime("%Y%m%d"),
        now.strftime("%H%M%S"),
        now.strftime("%Y%m%d"),
        now.strftime("%H%M%S"),
        user_id,
        user_id,
    )
    if table_name == "receipt_info_category1":
        connection.execute(
            """
            INSERT INTO kakeibo.RECEIPT_INFO_CATEGORY1
                (CRE_PROG, UPD_PROG, CATEGORY1_NAME, CRE_DT, CRE_TM, UPD_DT, UPD_TM,
                 CRE_USER_ID, UPD_USER_ID, DEL_FLAG)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """,
            (common[0], common[1], category1, *common[2:]),
        )
    else:
        connection.execute(
            """
            INSERT INTO kakeibo.RECEIPT_INFO_CATEGORY2
                (CRE_PROG, UPD_PROG, CATEGORY1_NAME, CATEGORY2_NAME, TAX_RATE,
                 CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            """,
            (common[0], common[1], category1, category2, tax_rate, *common[2:]),
        )
    return True


def ensure_category_master(connection: psycopg.Connection, user_id: str) -> dict[str, int]:
    """拡張版の大分類・小分類をユーザーのマスタへ追加する。"""
    category1_rows = connection.execute(
        """
        SELECT ID, CATEGORY1_NAME, COALESCE(DEL_FLAG, 0) AS DEL_FLAG
        FROM kakeibo.RECEIPT_INFO_CATEGORY1 WHERE CRE_USER_ID = %s ORDER BY ID
        """,
        (user_id,),
    ).fetchall()
    category2_rows = connection.execute(
        """
        SELECT ID, CATEGORY1_NAME, CATEGORY2_NAME, COALESCE(DEL_FLAG, 0) AS DEL_FLAG
        FROM kakeibo.RECEIPT_INFO_CATEGORY2 WHERE CRE_USER_ID = %s ORDER BY ID
        """,
        (user_id,),
    ).fetchall()
    active1 = {row["category1_name"] for row in category1_rows if int(row["del_flag"] or 0) == 0}
    deleted1 = {
        row["category1_name"]: row["id"]
        for row in category1_rows if int(row["del_flag"] or 0) != 0
    }
    active2 = {
        (row["category1_name"], row["category2_name"])
        for row in category2_rows if int(row["del_flag"] or 0) == 0
    }
    deleted2 = {
        (row["category1_name"], row["category2_name"]): row["id"]
        for row in category2_rows if int(row["del_flag"] or 0) != 0
    }
    now = datetime.now()
    date_value = now.strftime("%Y%m%d")
    time_value = now.strftime("%H%M%S")
    insert1: list[tuple[object, ...]] = []
    insert2: list[tuple[object, ...]] = []
    reactivate1: list[tuple[object, ...]] = []
    reactivate2: list[tuple[object, ...]] = []

    for category1, children in DEFAULT_EXPENSE_CATEGORIES.items():
        if category1 not in active1:
            if category1 in deleted1:
                reactivate1.append((MIGRATION_PROGRAM, date_value, time_value, user_id, deleted1[category1]))
            else:
                insert1.append((
                    MIGRATION_PROGRAM, MIGRATION_PROGRAM, category1,
                    date_value, time_value, date_value, time_value, user_id, user_id,
                ))
        for category2, tax_rate in children:
            key = (category1, category2)
            if key in active2:
                continue
            if key in deleted2:
                reactivate2.append((
                    tax_rate, MIGRATION_PROGRAM, date_value, time_value, user_id, deleted2[key],
                ))
            else:
                insert2.append((
                    MIGRATION_PROGRAM, MIGRATION_PROGRAM, category1, category2, tax_rate,
                    date_value, time_value, date_value, time_value, user_id, user_id,
                ))

    with connection.cursor() as cursor:
        if reactivate1:
            cursor.executemany(
                """
                UPDATE kakeibo.RECEIPT_INFO_CATEGORY1
                SET DEL_FLAG = 0, UPD_PROG = %s, UPD_DT = %s, UPD_TM = %s, UPD_USER_ID = %s
                WHERE ID = %s
                """,
                reactivate1,
            )
        if insert1:
            cursor.executemany(
                """
                INSERT INTO kakeibo.RECEIPT_INFO_CATEGORY1
                    (CRE_PROG, UPD_PROG, CATEGORY1_NAME, CRE_DT, CRE_TM, UPD_DT, UPD_TM,
                     CRE_USER_ID, UPD_USER_ID, DEL_FLAG)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                """,
                insert1,
            )
        if reactivate2:
            cursor.executemany(
                """
                UPDATE kakeibo.RECEIPT_INFO_CATEGORY2
                SET DEL_FLAG = 0, TAX_RATE = %s, UPD_PROG = %s, UPD_DT = %s, UPD_TM = %s, UPD_USER_ID = %s
                WHERE ID = %s
                """,
                reactivate2,
            )
        if insert2:
            cursor.executemany(
                """
                INSERT INTO kakeibo.RECEIPT_INFO_CATEGORY2
                    (CRE_PROG, UPD_PROG, CATEGORY1_NAME, CATEGORY2_NAME, TAX_RATE,
                     CRE_DT, CRE_TM, UPD_DT, UPD_TM, CRE_USER_ID, UPD_USER_ID, DEL_FLAG)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                """,
                insert2,
            )
    return {
        "category1": len(insert1) + len(reactivate1),
        "category2": len(insert2) + len(reactivate2),
    }


def migrate_details(connection: psycopg.Connection, user_id: str) -> tuple[int, list[dict[str, object]]]:
    """商品名と旧分類から、安全に判定できる明細だけを更新する。"""
    rows = connection.execute(
        """
        SELECT ID, ITEM_NAME, CAT1, CAT2, TAX_RATE
        FROM kakeibo.RECEIPT_DETAIL
        WHERE CRE_USER_ID = %s AND COALESCE(DEL_FLAG, 0) = 0
        ORDER BY ID
        """,
        (user_id,),
    ).fetchall()
    changes: list[dict[str, object]] = []
    update_params: list[tuple[object, ...]] = []
    now = datetime.now()
    for row in rows:
        category1, category2, tax_rate = refine_item_category(
            row["item_name"], row["cat1"], row["cat2"], row["tax_rate"]
        )
        current_rate = float(row["tax_rate"] or 0.10)
        if (
            category1 == str(row["cat1"] or "").strip()
            and category2 == str(row["cat2"] or "").strip()
            and abs(tax_rate - current_rate) < 0.0001
        ):
            continue
        update_params.append((
            category1, category2, tax_rate, MIGRATION_PROGRAM,
            now.strftime("%Y%m%d"), now.strftime("%H%M%S"), user_id,
            row["id"], user_id,
        ))
        if len(changes) < 30:
            changes.append({
                "itemName": row["item_name"],
                "before": [row["cat1"], row["cat2"]],
                "after": [category1, category2],
            })
    if update_params:
        # 2026-11-06 Codex: クラウドDBへの往復を抑え、全履歴を1つのトランザクションで更新する。
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE kakeibo.RECEIPT_DETAIL
                SET CAT1 = %s, CAT2 = %s, TAX_RATE = %s,
                    UPD_PROG = %s, UPD_DT = %s, UPD_TM = %s, UPD_USER_ID = %s
                WHERE ID = %s AND CRE_USER_ID = %s
                """,
                update_params,
            )
    return len(update_params), changes


def migrate_suppliers(connection: psycopg.Connection, user_id: str) -> tuple[int, list[dict[str, object]]]:
    """店舗名と登録商品の分類比率から店舗分類を更新する。"""
    usage_rows = connection.execute(
        """
        SELECT R.INV_REG_NUM, D.CAT1, D.CAT2, COUNT(*) AS ITEMS
        FROM kakeibo.RECEIPT_INFO R
        JOIN kakeibo.RECEIPT_DETAIL D
          ON D.RET_ID = R.RET_ID AND D.CRE_USER_ID = R.CRE_USER_ID
         AND COALESCE(D.DEL_FLAG, 0) = 0
        WHERE R.CRE_USER_ID = %s AND COALESCE(R.DEL_FLAG, 0) = 0
        GROUP BY R.INV_REG_NUM, D.CAT1, D.CAT2
        """,
        (user_id,),
    ).fetchall()
    usage: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in usage_rows:
        usage[str(row["inv_reg_num"] or "")].append({
            "category1": row["cat1"],
            "category2": row["cat2"],
            "count": row["items"],
        })

    suppliers = connection.execute(
        """
        SELECT ID, INV_REG_NUM, SUP_NAME, SUP_CATEGORY
        FROM kakeibo.INVOICE_REGISTRATION
        WHERE CRE_USER_ID = %s AND COALESCE(DEL_FLAG, 0) = 0
        ORDER BY ID
        """,
        (user_id,),
    ).fetchall()
    changes: list[dict[str, object]] = []
    now = datetime.now()
    update_params: list[tuple[object, ...]] = []
    for row in suppliers:
        current = str(row["sup_category"] or "").strip() or "その他"
        # 2026-11-06 Codex: 標準・旧分類は再判定し、利用者が独自登録した分類だけを保護する。
        if current not in MANAGED_PLACE_CATEGORIES:
            continue
        next_category = classify_supplier_category(
            row["sup_name"], usage.get(str(row["inv_reg_num"] or ""), []),
        )
        if current == next_category:
            continue
        update_params.append((
            next_category, MIGRATION_PROGRAM, now.strftime("%Y%m%d"),
            now.strftime("%H%M%S"), user_id, row["id"], user_id,
        ))
        if len(changes) < 30:
            changes.append({
                "supplierName": row["sup_name"],
                "before": current,
                "after": next_category,
            })
    if update_params:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                UPDATE kakeibo.INVOICE_REGISTRATION
                SET SUP_CATEGORY = %s, UPD_PROG = %s, UPD_DT = %s, UPD_TM = %s, UPD_USER_ID = %s
                WHERE ID = %s AND CRE_USER_ID = %s
                """,
                update_params,
            )
    return len(update_params), changes


def migrate_user(
    connection: psycopg.Connection,
    user_id: str,
    migration_id: str,
    apply_changes: bool,
) -> dict[str, object]:
    """1ユーザー分のバックアップ、マスタ追加、履歴更新を実行する。"""
    backup_counts = backup_user_rows(connection, migration_id, user_id) if apply_changes else {}
    master = ensure_category_master(connection, user_id)
    detail_count, detail_samples = migrate_details(connection, user_id)
    supplier_count, supplier_samples = migrate_suppliers(connection, user_id)
    return {
        "userId": user_id,
        "backupRows": backup_counts,
        "masterAdded": master,
        "detailUpdated": detail_count,
        "supplierUpdated": supplier_count,
        "detailSamples": detail_samples,
        "supplierSamples": supplier_samples,
    }


def main() -> int:
    """移行処理を実行し、JSON形式で結果を表示する。"""
    args = parse_args()
    database_url = os.environ.get("KAKEIBO_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("KAKEIBO_DATABASE_URLを設定してください。")

    migration_id = f"category-{datetime.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}"
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        if args.apply:
            ensure_backup_schema(connection)
        users = active_user_ids(connection, args.user_id)
        results = [
            migrate_user(connection, user_id, migration_id, args.apply)
            for user_id in users
        ]
        if args.apply:
            connection.commit()
        else:
            connection.rollback()
        print(json.dumps({
            "mode": "apply" if args.apply else "preview",
            "migrationId": migration_id if args.apply else None,
            "users": results,
        }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
