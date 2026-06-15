import json
from unittest.mock import MagicMock, patch

from src.batch.auto_input_suica.autoInput_Suica import AutoInput_Suica


def make_batch():
    batch = AutoInput_Suica.__new__(AutoInput_Suica)
    batch.database = MagicMock()
    batch.logger = MagicMock()
    return batch


def test_save_history_rows_matches_legacy_row_without_source_key():
    batch = make_batch()
    batch.database.select.return_value = [{"id": 1}]
    row = {
        "date": "2026-06-05",
        "entryType": "transport",
        "entryPlace": "A",
        "exitType": "exit",
        "exitPlace": "B",
        "balance": 1000,
        "amount": -209,
    }

    assert batch.save_history_rows([row], "user-1") == 0
    batch.database.insert.assert_not_called()

    params = batch.database.select.call_args.args[1]
    assert params["RET_DT"] == "20260605"
    assert json.loads(params["RET_CONT"]) == row


def test_duplicate_receipt_marks_staging_rows_and_continues():
    batch = make_batch()
    staging_row = {
        "id": 7,
        "RET_CONT": json.dumps({
            "date": "2026-06-05",
            "entryType": "transport",
            "entryPlace": "A",
            "exitType": "exit",
            "exitPlace": "B",
            "balance": 1000,
            "amount": -209,
        }),
    }
    batch.database.select.return_value = [staging_row]
    batch.update_auto_input_status = MagicMock()

    registration_api = MagicMock()
    registration_api.call.return_value = {
        "statusCode": 409,
        "body": {"errorCode": "1000062"},
    }

    with (
        patch(
            "src.batch.auto_input_suica.autoInput_Suica.NewReceiptRegistration",
            return_value=registration_api,
        ),
    ):
        registered, duplicates = batch.register_pending_expenses("user-1")

    assert (registered, duplicates) == (0, 1)
    batch.update_auto_input_status.assert_called_once_with(staging_row, "user-1", "DUPLICATE")


def test_pending_query_includes_empty_and_fetched_status_only():
    batch = make_batch()
    batch.database.select.return_value = []

    assert batch.register_pending_expenses("user-1") == (0, 0)

    sql, params = batch.database.select.call_args.args
    assert "COALESCE(AUTO_INPUT_STATUS, '') IN ('', 'FETCHED')" in sql
    assert params["USER_ID"] == "user-1"
