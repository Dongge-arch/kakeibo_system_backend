from pathlib import Path

from src.batch.kakeibo.auto_input_scheduler import autoInputScheduler


class FakeDatabase:
    def read_sql(self, name, location=None):
        return (Path(location).parent / "sql" / f"{name}.sql").read_text(encoding="utf-8")

    def select(self, _sql, _params=None):
        return [{"CRE_USER_ID": "user-1", "CONNECTION_TYPE": "BELC"}]


class FakeBatch:
    def call(self, body, headers):
        return {
            "statusCode": 200,
            "body": {
                "totalFetched": 11,
                "alreadyRegistered": 0,
                "needToRegister": 11,
                "registered": 0,
                "failed": 11,
            },
        }


def test_scheduler_counts_batch_body_failures_as_failed(monkeypatch):
    monkeypatch.setitem(autoInputScheduler.AUTO_INPUT_BATCHES, "BELC", FakeBatch)

    scheduler = autoInputScheduler.AutoInputScheduler.__new__(
        autoInputScheduler.AutoInputScheduler
    )
    scheduler.database = FakeDatabase()

    result = scheduler.main({})
    body = result["body"]

    assert body["succeededCount"] == 0
    assert body["failedCount"] == 1
    assert body["results"][0]["statusCode"] == 200


def test_scheduler_separates_aws_and_server_connections():
    scheduler = autoInputScheduler.AutoInputScheduler.__new__(
        autoInputScheduler.AutoInputScheduler
    )

    assert scheduler.resolve_target_connections({}) == ("ETC",)
    assert scheduler.resolve_target_connections({"source": "armbian-server"}) == (
        "BELC",
        "AMAZON",
        "NITORI",
        "CAINZ",
        "MUJI",
    )


def test_scheduler_selects_only_valid_database_connections():
    sql = Path(
        "src/batch/kakeibo/auto_input_scheduler/sql/SELECT_KAKEIBO_AUTO_INPUT_INFO.sql"
    ).read_text(encoding="utf-8")

    assert "ENABLED = 1" in sql
    assert "COALESCE(LOGIN_ID_1, '') <> ''" in sql
    assert "COALESCE(LOGIN_PW_1, '') <> ''" in sql
    assert "DEL_FLAG = 0" in sql


def test_scheduler_accepts_server_batch_class_override(monkeypatch):
    monkeypatch.setitem(autoInputScheduler.AUTO_INPUT_BATCHES, "NITORI", FakeBatch)
    scheduler = autoInputScheduler.AutoInputScheduler.__new__(
        autoInputScheduler.AutoInputScheduler
    )

    assert scheduler.batch_class_for("NITORI") is FakeBatch
    assert scheduler.batch_class_for("UNKNOWN") is None
