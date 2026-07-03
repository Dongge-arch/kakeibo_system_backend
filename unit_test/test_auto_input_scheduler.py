from src.batch.auto_input_scheduler import autoInputScheduler


class FakeDatabase:
    def select(self, _sql):
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
