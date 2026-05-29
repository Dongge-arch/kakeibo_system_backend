import importlib.util
import os
import sys
import types
import unittest


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


if __name__ == "__main__":
    unittest.main()
