import json
from unittest.mock import MagicMock, patch

from src.batch.auto_input_targets.auto_input_suica.autoInput_Suica import AutoInput_Suica


def make_batch():
    batch = AutoInput_Suica.__new__(AutoInput_Suica)
    batch.database = MagicMock()
    batch.logger = MagicMock()
    batch.connection_type = "SUICA"
    batch.supplier_name = "東日本旅客鉄道株式会社"
    batch.invoice_registration_number = "T9011001029597"
    batch.item_prefix = "Suica"
    batch.supplier_image = ""
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
    batch.database.select.side_effect = [[staging_row], []]
    batch.update_auto_input_status = MagicMock()

    registration_api = MagicMock()
    registration_api.call.return_value = {
        "statusCode": 409,
        "body": {"errorCode": "1000062"},
    }

    with (
        patch(
            "src.batch.auto_input_targets.auto_input_suica.autoInput_Suica.NewReceiptRegistration",
            return_value=registration_api,
        ),
    ):
        registered, duplicates = batch.register_pending_expenses("user-1")

    assert (registered, duplicates) == (0, 1)
    batch.update_auto_input_status.assert_called_once_with(staging_row, "user-1", "DUPLICATE")


def test_registered_receipt_is_removed_before_registration_api_call():
    batch = make_batch()
    staging_row = {
        "id": 8,
        "SOURCE_KEY": "history-8",
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
    batch.database.select.side_effect = [
        [staging_row],
        [{"RET_DT": "20260605", "RET_TM": "000000", "TOA_PRICE": 209}],
    ]
    batch.update_auto_input_status = MagicMock()
    registration_api = MagicMock()

    with patch(
        "src.batch.auto_input_targets.auto_input_suica.autoInput_Suica.NewReceiptRegistration",
        return_value=registration_api,
    ):
        registered, duplicates = batch.register_pending_expenses("user-1")

    assert (registered, duplicates) == (0, 1)
    registration_api.call.assert_not_called()
    batch.update_auto_input_status.assert_called_once_with(staging_row, "user-1", "DUPLICATE")


def test_same_staging_history_is_removed_before_total_calculation():
    batch = make_batch()
    history = {
        "date": "2026-06-05",
        "entryType": "transport",
        "entryPlace": "A",
        "exitType": "exit",
        "exitPlace": "B",
        "balance": 1000,
        "amount": -209,
    }
    first_row = {"id": 9, "RET_CONT": json.dumps(history)}
    duplicate_row = {"id": 10, "RET_CONT": json.dumps(history)}
    batch.database.select.side_effect = [[first_row, duplicate_row], []]
    batch.update_auto_input_status = MagicMock()
    registration_api = MagicMock()
    registration_api.call.return_value = {"statusCode": 201, "body": {"receiptId": "receipt-1"}}

    with patch(
        "src.batch.auto_input_targets.auto_input_suica.autoInput_Suica.NewReceiptRegistration",
        return_value=registration_api,
    ):
        registered, duplicates = batch.register_pending_expenses("user-1")

    assert (registered, duplicates) == (1, 1)
    receipt_info = registration_api.call.call_args.kwargs["body"]["receiptInfo"]
    assert receipt_info["receiptDetailCount"] == 1
    assert receipt_info["totalPrice"] == 209
    assert batch.update_auto_input_status.call_args_list == [
        ((duplicate_row, "user-1", "DUPLICATE"),),
        ((first_row, "user-1", "3"),),
    ]


def test_pending_query_includes_empty_and_fetched_status_only():
    batch = make_batch()
    batch.database.select.return_value = []

    assert batch.register_pending_expenses("user-1") == (0, 0)

    sql, params = batch.database.select.call_args.args
    assert "COALESCE(AUTO_INPUT_STATUS, '') IN ('', 'FETCHED')" in sql
    assert params["USER_ID"] == "user-1"
