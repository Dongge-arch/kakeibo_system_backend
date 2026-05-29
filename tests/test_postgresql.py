import importlib.util
import os
import sys
import types
import unittest

from src.common.auth_context import reset_current_user_id, set_current_user_id


class FakeCursor:
    def __init__(self):
        self.rowcount = 0


class FakeConnector:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return FakeCursor()

    def commit(self):
        pass

    def close(self):
        pass


class PostgreSQLAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_yaml = types.ModuleType("yaml")
        sys.modules["yaml"] = fake_yaml

        fake_config_package = types.ModuleType("src.common.config")
        fake_config_module = types.ModuleType("src.common.config.config")
        fake_config_module.APP_CONFIG = {
            "logging": {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "custom": {
                        "format": "%(message)s",
                    },
                },
                "handlers": {},
                "loggers": {},
            }
        }
        fake_config_package.APP_CONFIG = fake_config_module.APP_CONFIG
        sys.modules["src.common.config"] = fake_config_package
        sys.modules["src.common.config.config"] = fake_config_module

        fake_psycopg = types.ModuleType("psycopg")
        fake_rows = types.ModuleType("psycopg.rows")

        def fake_connect(database_url, row_factory=None):
            return FakeConnector()

        fake_rows.dict_row = object()
        fake_psycopg.connect = fake_connect

        sys.modules["psycopg"] = fake_psycopg
        sys.modules["psycopg.rows"] = fake_rows

        module_path = os.path.join(os.getcwd(), "src", "common", "database", "postgresql.py")
        spec = importlib.util.spec_from_file_location("postgresql_module", module_path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_postgresql_row_initializes_base_logger(self):
        row = self.module.PostgresqlRow({"itemName": "apple"})

        self.assertEqual(row["itemName"], "apple")
        self.assertTrue(hasattr(row, "logger"))

    def test_postgresql_initializes_base_logger(self):
        db = self.module.Postgresql("postgresql://example", initialize_schema=False)

        self.assertTrue(hasattr(db, "logger"))
        self.assertEqual(db.connector.__class__.__name__, "FakeConnector")

    def test_do_sql_with_retry_converts_runtime_user_scope_placeholders(self):
        db = self.module.Postgresql("postgresql://example", initialize_schema=False)
        token = set_current_user_id("tester")
        try:
            sql, params = db.apply_user_scope("SELECT * FROM ai_usage_log", {}, "select")

            db.do_sql_with_retry(sql, params)

            executed_sql, executed_params = db.connector.executed[-1]
            self.assertEqual(
                executed_sql.rstrip(),
                "SELECT * FROM ai_usage_log\nWHERE ai_usage_log.CRE_USER_ID = %(__current_user_id)s",
            )
            self.assertEqual(executed_params["__current_user_id"], "tester")
        finally:
            reset_current_user_id(token)

    def test_scope_insert_preserves_psycopg_placeholders(self):
        db = self.module.Postgresql("postgresql://example", initialize_schema=False)
        token = set_current_user_id("tester")
        try:
            sql_path = os.path.join(
                os.getcwd(),
                "src",
                "api",
                "receipt",
                "new_receipt_registration",
                "sql",
                "INSERT_INV_NUM.sql",
            )
            with open(sql_path, "r", encoding="utf-8") as sql_file:
                sql = sql_file.read()

            params = {
                "CRE_PROG": "NewReceiptRegistration",
                "UPD_PROG": "NewReceiptRegistration",
                "INV_REG_NUM": "123",
                "SUP_NAME": "ABC",
                "TAX_FLAG": 1,
                "CRE_DT": "20260529",
                "CRE_TM": "101010",
                "UPD_DT": "20260529",
                "UPD_TM": "101010",
                "DEL_FLAG": 0,
            }

            transformed_sql, transformed_params = db.apply_user_scope(sql, params, "insert")
            db.do_sql_with_retry(transformed_sql, transformed_params)

            executed_sql, executed_params = db.connector.executed[-1]
            self.assertIn("%(CRE_PROG)s", executed_sql)
            self.assertIn("%(UPD_PROG)s", executed_sql)
            self.assertIn("CRE_USER_ID", executed_sql)
            self.assertIn("UPD_USER_ID", executed_sql)
            self.assertIn("%(__current_user_id)s", executed_sql)
            self.assertNotIn("%(CRE_PROG,", executed_sql)
            self.assertEqual(executed_params["CRE_PROG"], "NewReceiptRegistration")
            self.assertEqual(executed_params["__current_user_id"], "tester")
        finally:
            reset_current_user_id(token)


if __name__ == "__main__":
    unittest.main()
