# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Home Kakeibo System Contributors

import os
import re
import threading
from typing import Any, Dict, List, Optional

from src.common.auth_context import get_current_user_id


class PostgresqlRow(dict):
    """PostgreSQLの小文字化された列名を既存API名でも参照できる行オブジェクト。"""

    _camel_aliases = {
        "analysisid": "analysisId",
        "aioutputjson": "aiOutputJson",
        "autodark": "autoDark",
        "budgetamount": "budgetAmount",
        "budgetenabled": "budgetEnabled",
        "budgetperiod": "budgetPeriod",
        "category1name": "category1Name",
        "category2name": "category2Name",
        "cachedtokens": "cachedTokens",
        "createddate": "createdDate",
        "createdtime": "createdTime",
        "darkmode": "darkMode",
        "editedreceiptjson": "editedReceiptJson",
        "imagebase64": "imageBase64",
        "imagemimetype": "imageMimeType",
        "invoiceregistrationnumber": "invoiceRegistrationNumber",
        "itemname": "itemName",
        "outputtokens": "outputTokens",
        "prompttokens": "promptTokens",
        "receiptdate": "receiptDate",
        "receiptid": "receiptId",
        "receipttime": "receiptTime",
        "requestcount": "requestCount",
        "supplierlogo": "supplierLogo",
        "suppliername": "supplierName",
        "salarycategoryname": "salaryCategoryName",
        "taxflag": "taxFlag",
        "taxrate": "taxRate",
        "thoughtstokens": "thoughtsTokens",
        "totalprice": "totalPrice",
        "totaltokens": "totalTokens",
        "unitprice": "unitPrice",
    }

    def __init__(self, row: Dict[str, Any]):
        normalized = {}
        for key, value in dict(row).items():
            normalized[key] = value
            if isinstance(key, str):
                normalized.setdefault(key.upper(), value)
                normalized.setdefault(key.lower(), value)
                alias = self._camel_aliases.get(key.lower())
                if alias:
                    normalized.setdefault(alias, value)
        super().__init__(normalized)

    def _resolve_key(self, key):
        if not isinstance(key, str) or dict.__contains__(self, key):
            return key
        lower_key = key.lower()
        if dict.__contains__(self, lower_key):
            return lower_key
        upper_key = key.upper()
        if dict.__contains__(self, upper_key):
            return upper_key
        for existing_key in dict.keys(self):
            if isinstance(existing_key, str) and existing_key.lower() == lower_key:
                return existing_key
        return key

    def get(self, key, default=None):
        return dict.get(self, self._resolve_key(key), default)

    def __getitem__(self, key):
        return dict.__getitem__(self, self._resolve_key(key))

    def __contains__(self, key):
        return dict.__contains__(self, self._resolve_key(key))

    def pop(self, key, default=None):
        resolved = self._resolve_key(key)
        if dict.__contains__(self, resolved):
            return dict.pop(self, resolved)
        return default


class Postgresql:
    """
    NeonなどのPostgreSQLへ接続するDBアダプタ。
    """

    # CREATE TABLEを複数プロセスで同時実行しないためのプロセス内lock。
    _schema_lock = threading.Lock()
    # 既に初期化済みのDB URLを記録し、同一プロセス内の再実行を避ける。
    _initialized_urls = set()
    # PostgreSQL advisory lock用の固定ID。
    _advisory_lock_id = 74060219849901
    _owned_tables = {
        # ログインユーザー別にCRE_USER_IDで絞り込む対象テーブル。
        "receipt_info",
        "receipt_detail",
        "invoice_registration",
        "receipt_info_category1",
        "receipt_info_category2",
        "salary_info_category",
        "salary_info",
        "budget_info",
        "setting_table",
        "ai_usage_log",
        "ai_receipt_analysis",
        "recurring_expense",
    }
    _reserved_aliases = {
        # SELECTスコープ付与時に予約語をaliasと誤判定しないための一覧。
        "WHERE",
        "JOIN",
        "LEFT",
        "RIGHT",
        "INNER",
        "OUTER",
        "ORDER",
        "GROUP",
        "LIMIT",
        "ON",
        "USING",
    }

    def __init__(self, database_url: str, initialize_schema: bool = True) -> None:
        """
        PostgreSQL接続を初期化し、必要に応じてスキーマを作成する。

        Args:
            database_url(str): PostgreSQL接続URL。
            initialize_schema(bool): 起動時にCREATE TABLEを実行するかどうか。
        """
        if not database_url:
            raise ValueError("PostgreSQL database url is required.")

        from psycopg import connect
        from psycopg.rows import dict_row

        # SQLファイル読み込み結果のキャッシュ。
        self._sql_cache = {}
        self.connector = connect(database_url, row_factory=dict_row)
        print("DB TYPE: postgresql")

        if initialize_schema:
            self.initialize_schema_once(database_url)
        self.connector.execute("SET search_path TO kakeibo")
        self.connector.commit()

        # 既存SQLの :NAME 形式を psycopg の %(NAME)s 形式へ変換する。
        self._pattern = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")

    def read_sql(self, sqlname: str, location=None):
        """
        指定名のSQLファイルを読み込み、以後はメモリキャッシュから返す。

        Args:
            sqlname(str): 読み込むSQLファイル名。拡張子は含めない。
            location(str | None): 呼び出し元ファイル。指定時は同階層のsqlフォルダを見る。

        Returns:
            str: SQL文字列。
        """
        if self._sql_cache.get(sqlname):
            return self._sql_cache.get(sqlname)

        if not location:
            path = os.path.join(os.path.dirname(__file__), "sql", f"{sqlname}.sql")
        else:
            path = os.path.join(os.path.dirname(location), "sql", f"{sqlname}.sql")

        with open(path, "r", encoding="utf-8") as file:
            sql = file.read()

        self._sql_cache[sqlname] = sql
        return sql

    def __del__(self):
        """
        オブジェクト破棄時にDB接続を閉じる。
        """
        self.close()

    def select(self, sql: str, params: Optional[Any] = None) -> List[Dict]:
        """
        SELECT文を実行し、結果を辞書のリストで返す。

        Args:
            sql(str): 実行するSELECT文。
            params(Optional[Any]): SQLに渡す名前付きパラメータ。

        Returns:
            List[Dict]: 検索結果行のリスト。
        """
        sql, params = self.apply_user_scope(sql, params or {}, "select")
        sql = self.convert_placeholders(sql)
        cursor = self.connector.cursor()
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [PostgresqlRow(dict(row)) for row in rows]

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        任意のSQLを実行し、更新件数を返す。

        Args:
            sql(str): 実行するSQL文。
            params(Optional[Dict[str, Any]]): SQLに渡す名前付きパラメータ。

        Returns:
            int: 更新件数。
        """
        sql, params = self.apply_user_scope(sql, params or {}, "execute")
        sql = self.convert_placeholders(sql)
        cursor = self.connector.cursor()
        cursor.execute(sql, params)
        self.connector.commit()
        return cursor.rowcount

    def insert(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        INSERT文を実行し、PostgreSQLの更新件数を返す。

        Args:
            sql(str): 実行するINSERT文。
            params(Optional[Dict[str, Any]]): SQLに渡す名前付きパラメータ。

        Returns:
            int: 更新件数。
        """
        sql, params = self.apply_user_scope(sql, params or {}, "insert")
        sql = self.convert_placeholders(sql)
        cursor = self.connector.cursor()
        cursor.execute(sql, params)
        self.connector.commit()
        return cursor.rowcount

    def update(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        UPDATE文を実行し、更新件数を返す。

        Args:
            sql(str): 実行するUPDATE文。
            params(Optional[Dict[str, Any]]): SQLに渡す名前付きパラメータ。

        Returns:
            int: 更新件数。
        """
        return self.execute(sql, params)

    def execute_many(self, sql: str, params_list: List[Dict[str, Any]]) -> None:
        """
        複数パラメータで同一SQLをまとめて実行する。

        Args:
            sql(str): 実行するSQL文。
            params_list(List[Dict[str, Any]]): SQLに渡すパラメータ一覧。
        """
        sql = self.convert_placeholders(sql)
        cursor = self.connector.cursor()
        cursor.executemany(sql, params_list)
        self.connector.commit()

    def begin(self):
        """
        明示的にトランザクションを開始する。
        """
        self.connector.execute("BEGIN")

    def commit(self):
        """
        現在のトランザクションをコミットする。
        """
        self.connector.commit()

    def rollback(self):
        """
        現在のトランザクションをロールバックする。
        """
        self.connector.rollback()

    def convert_placeholders(self, sql: str) -> str:
        """
        既存SQLの名前付きプレースホルダをpsycopg形式へ変換する。

        Args:
            sql(str): 変換対象のSQL文。

        Returns:
            str: psycopg形式のプレースホルダへ変換したSQL文。
        """
        return self._pattern.sub(lambda m: f"%({m.group(1)})s", sql)

    def apply_user_scope(self, sql: str, params: Dict[str, Any], operation: str):
        """
        業務テーブルのSQLへ現在ユーザー条件を自動付与する。

        Args:
            sql(str): 実行予定のSQL文。
            params(Dict[str, Any]): SQLに渡す名前付きパラメータ。
            operation(str): 呼び出し元のDB操作名。

        Returns:
            tuple[str, Dict[str, Any]]: ユーザー条件を反映したSQLとパラメータ。
        """
        # FastAPI middlewareがContextVarに入れた現在ユーザーID。
        user_id = get_current_user_id()
        if not user_id:
            return sql, params

        params = dict(params or {})
        params.setdefault("__current_user_id", user_id)
        stripped = self.strip_leading_comments(sql)
        command = stripped.split(None, 1)[0].lower() if stripped else ""

        if command == "insert":
            return self.scope_insert(sql, params)
        if command == "update":
            return self.scope_update(sql, params)
        if command == "select":
            return self.scope_select(sql, params)

        return sql, params

    def scope_insert(self, sql: str, params: Dict[str, Any]):
        """
        INSERT文へ作成ユーザー・更新ユーザー列を自動付与する。

        Args:
            sql(str): 実行予定のINSERT文。
            params(Dict[str, Any]): SQLに渡す名前付きパラメータ。

        Returns:
            tuple[str, Dict[str, Any]]: 所有者列を反映したSQLとパラメータ。
        """
        match = re.search(
            r"INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return sql, params

        table = match.group(1).lower()
        if table not in self._owned_tables:
            return sql, params

        columns = match.group(2)
        values = match.group(3)
        upper_columns = columns.upper()
        add_columns = []
        add_values = []
        if "CRE_USER_ID" not in upper_columns:
            add_columns.append("CRE_USER_ID")
            add_values.append(":__current_user_id")
        if "UPD_USER_ID" not in upper_columns:
            add_columns.append("UPD_USER_ID")
            add_values.append(":__current_user_id")

        if not add_columns:
            return sql, params

        new_columns = f"{columns.rstrip()},\n    " + ",\n    ".join(add_columns)
        new_values = f"{values.rstrip()},\n    " + ",\n    ".join(add_values)
        sql = sql[:match.start(2)] + new_columns + sql[match.end(2):match.start(3)] + new_values + sql[match.end(3):]
        return sql, params

    def strip_leading_comments(self, sql: str) -> str:
        """
        SQL先頭のコメントを除外し、命令種別を判定しやすくする。

        Args:
            sql(str): 判定対象のSQL文。

        Returns:
            str: 先頭コメントを除いたSQL文。
        """
        stripped = sql.lstrip()
        while stripped.startswith("--"):
            _, _, stripped = stripped.partition("\n")
            stripped = stripped.lstrip()
        while stripped.startswith("/*"):
            _, marker, remainder = stripped.partition("*/")
            if not marker:
                break
            stripped = remainder.lstrip()
        return stripped

    def scope_update(self, sql: str, params: Dict[str, Any]):
        """
        UPDATE文へ更新ユーザー列とユーザー所有条件を自動付与する。

        Args:
            sql(str): 実行予定のUPDATE文。
            params(Dict[str, Any]): SQLに渡す名前付きパラメータ。

        Returns:
            tuple[str, Dict[str, Any]]: 所有条件を反映したSQLとパラメータ。
        """
        match = re.search(r"UPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+SET\s+", sql, re.IGNORECASE)
        if not match:
            return sql, params

        table = match.group(1).lower()
        if table not in self._owned_tables:
            return sql, params

        if "UPD_USER_ID" not in sql.upper():
            insert_at = match.end()
            sql = sql[:insert_at] + "UPD_USER_ID = :__current_user_id,\n" + sql[insert_at:]

        condition = f"{table}.CRE_USER_ID = :__current_user_id"
        return self.append_condition(sql, condition), params

    def scope_select(self, sql: str, params: Dict[str, Any]):
        """
        SELECT文へユーザー所有条件を自動付与する。

        Args:
            sql(str): 実行予定のSELECT文。
            params(Dict[str, Any]): SQLに渡す名前付きパラメータ。

        Returns:
            tuple[str, Dict[str, Any]]: 所有条件を反映したSQLとパラメータ。
        """
        conditions = []
        for table in self._owned_tables:
            for match in re.finditer(
                rf"\b(?:FROM|JOIN)\s+{table}\b(?:\s+(?:AS\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?",
                sql,
                re.IGNORECASE,
            ):
                alias = match.group(1) or table
                if alias.upper() in self._reserved_aliases:
                    alias = table
                condition = f"{alias}.CRE_USER_ID = :__current_user_id"
                if condition not in conditions:
                    conditions.append(condition)

        for condition in conditions:
            sql = self.append_condition(sql, condition)
        return sql, params

    def append_condition(self, sql: str, condition: str) -> str:
        """
        SQL末尾のORDER/GROUP/LIMIT前にAND条件を差し込む。

        Args:
            sql(str): 条件を追加するSQL文。
            condition(str): 追加するAND条件。

        Returns:
            str: 条件追加後のSQL文。
        """
        if condition in sql:
            return sql

        boundary = re.search(r"\b(ORDER\s+BY|GROUP\s+BY|LIMIT)\b", sql, re.IGNORECASE)
        prefix = sql[:boundary.start()] if boundary else sql
        suffix = sql[boundary.start():] if boundary else ""
        joiner = "\nAND " if re.search(r"\bWHERE\b", prefix, re.IGNORECASE) else "\nWHERE "
        return prefix.rstrip().rstrip(";") + joiner + condition + "\n" + suffix

    def initialize_schema_once(self, database_url: str) -> None:
        """
        PostgreSQL側の排他ロックを使い、CREATE文を安全に一度だけ実行する。

        Args:
            database_url(str): 初期化対象のPostgreSQL接続URL。
        """
        # Lambdaや複数ワーカーで同時起動してもCREATE競合しないようにする。
        if database_url in self._initialized_urls:
            return

        with self._schema_lock:
            if database_url in self._initialized_urls:
                return

            locked = False
            try:
                self.connector.execute("SELECT pg_advisory_lock(%s)", (self._advisory_lock_id,))
                locked = True
                for statement in self.split_statements(
                    self.read_sql("CREATE_TABLES_POSTGRES", location=__file__)
                ):
                    self.connector.execute(statement)
                self.connector.commit()
                self._initialized_urls.add(database_url)
            except Exception:
                self.connector.rollback()
                raise
            finally:
                if locked:
                    try:
                        self.connector.execute("SELECT pg_advisory_unlock(%s)", (self._advisory_lock_id,))
                        self.connector.commit()
                    except Exception:
                        self.connector.rollback()

    def split_statements(self, sql: str) -> List[str]:
        """
        CREATE文をPostgreSQLへ1文ずつ実行できる形へ分割する。

        Args:
            sql(str): 複数文を含むSQL文字列。

        Returns:
            List[str]: 実行単位に分割したSQL文一覧。
        """
        statements = []
        current = []
        for line in sql.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            current.append(line)
            if stripped.endswith(";"):
                statement = "\n".join(current).strip()
                if statement:
                    statements.append(statement)
                current = []
        remaining = "\n".join(current).strip()
        if remaining:
            statements.append(remaining)
        return statements

    def table_columns(self, table: str) -> set:
        """
        指定テーブルの列名を取得する。既存のマイグレーション補助処理用。
        """
        rows = self.select(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'kakeibo'
              AND table_name = :table
            """,
            {"table": table.lower()},
        )
        return {str(row.get("column_name") or "").upper() for row in rows}

    def close(self):
        """
        DB接続を安全に閉じる。
        """
        try:
            if hasattr(self, "connector") and self.connector:
                self.connector.close()
        except Exception:
            pass
