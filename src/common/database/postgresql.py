# -*- coding: utf-8 -*-

import os
import re
import threading
from typing import Any, Dict, List, Optional

from src.common.base import Base


class PostgresqlRow(dict, Base):
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
        "taxexcludedtotalprice": "taxExcludedTotalPrice",
        "taxexcludedunitprice": "taxExcludedUnitPrice",
        "taxincludedtotalprice": "taxIncludedTotalPrice",
        "taxincludedunitprice": "taxIncludedUnitPrice",
        "to_tax_excluded": "taxExcludedTotalPrice",
        "ut_tax_excluded": "taxExcludedUnitPrice",
        "to_tax_included": "taxIncludedTotalPrice",
        "ut_tax_included": "taxIncludedUnitPrice",
        "thoughtstokens": "thoughtsTokens",
        "totalprice": "totalPrice",
        "totaltokens": "totalTokens",
        "unitprice": "unitPrice",
    }

    def __init__(self, row: Dict[str, Any]):
        Base.__init__(self, self.__class__.__name__)
        dict.__init__(self)
        normalized = {}
        for key, value in dict(row).items():
            normalized[key] = value
            if isinstance(key, str):
                alias = self._camel_aliases.get(key.lower())
                if alias:
                    normalized.setdefault(alias, value)
        self.update(normalized)

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


class Postgresql(Base):
    _schema_lock = threading.Lock()
    _initialized_urls = set()
    _advisory_lock_id = 74060219849901
    _connect_retry_count = 20

    def __init__(self, database_url: str, initialize_schema: bool = True) -> None:
        super().__init__(self.__class__.__name__)
        if not database_url:
            raise ValueError("PostgreSQL database url is required.")

        from psycopg import connect
        from psycopg.rows import dict_row

        self._sql_cache = {}
        self.connector = self.connect_with_retry(connect, database_url, dict_row)

        if initialize_schema:
            self.initialize_schema_once(database_url)
        self.connector.execute("SET search_path TO kakeibo")
        self._pattern = re.compile(r":([a-zA-Z_][a-zA-Z0-9_]*)")

    def connect_with_retry(self, connect_func, database_url: str, dict_row):
        last_error = None
        for attempt in range(1, self._connect_retry_count + 1):
            try:
                return connect_func(database_url, row_factory=dict_row)
            except Exception as exc:
                last_error = exc
                if attempt >= self._connect_retry_count:
                    break
                self.logger.info(f"PostgreSQL connection failed ({attempt}/{self._connect_retry_count}); retrying.")
        raise last_error

    def read_sql(self, sqlname: str, location=None):
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
        self.commit()
        self.close()

    def select(self, sql: str, params: Optional[Any] = None) -> List[Dict]:
        result = self.do_sql_with_retry(sql, params)
        rows = result.fetchall()
        self.logger.info("select 実行しました。")
        return [PostgresqlRow(dict(row)) for row in rows]

    def execute(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        result = self.do_sql_with_retry(sql, params)
        return self.extract_rowcount(result)

    def insert(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        result = self.do_sql_with_retry(sql, params)
        self.logger.info("insert 実行しました。")
        return self.extract_rowcount(result)

    def update(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        result = self.do_sql_with_retry(sql, params)
        self.logger.info("update 実行しました。")
        return self.extract_rowcount(result)

    def execute_many(self, sql: str, params_list: List[Dict[str, Any]]) -> int:
        result = self.do_sql_with_retry(sql, params_list)
        return self.extract_rowcount(result)

    def begin(self):
        self.connector.execute("BEGIN")

    def commit(self):
        try:
            self.connector.commit()
            self.logger.info("コミット完了")
        except Exception:
            pass

    def rollback(self):
        self.connector.rollback()
        self.logger.info("ロールバック完了")

    def extract_rowcount(self, result: Any) -> int:
        if isinstance(result, dict):
            return int(result.get("rowcount") or 0)
        return int(getattr(result, "rowcount", 0) or 0)

    def initialize_schema_once(self, database_url: str) -> None:
        if database_url in self._initialized_urls:
            return
        with self._schema_lock:
            if database_url in self._initialized_urls:
                return
            locked = False
            try:
                self.connector.execute("SELECT pg_advisory_lock(%s)", (self._advisory_lock_id,))
                locked = True
                for statement in self.split_statements(self.read_sql("CREATE_TABLES_POSTGRES", location=__file__)):
                    self.connector.execute(statement)
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
        rows = self.select(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'kakeibo'
              AND table_name = %(table)s
            """,
            {"table": table.lower()},
        )
        return {str(row.get("column_name") or "").upper() for row in rows}

    def close(self):
        try:
            if hasattr(self, "connector") and self.connector:
                self.connector.close()
        except Exception as exc:
            self.logger.warning(f"Failed to close PostgreSQL connection: {exc}", exc_info=True)

    def do_sql_with_retry(self, sql: str, params: Optional[Dict[str, Any]] = None):
        last_error = None
        for attempt in range(1, self._connect_retry_count + 1):
            try:
                return self.connector.execute(sql, params)
            except Exception as exc:
                self.logger.warning(f"PostgreSQL operation failed on attempt {attempt}: {exc}")
                last_error = exc
                self.rollback()
                if attempt >= self._connect_retry_count:
                    break
                self.logger.info(f"PostgreSQL operation failed ({attempt}/{self._connect_retry_count}); retrying.")
        raise last_error
