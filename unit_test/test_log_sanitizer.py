from src.common.log_sanitizer import (
    summarize_request_body,
    summarize_request_headers,
    summarize_response,
)


def test_request_log_summaries_do_not_include_values():
    headers = summarize_request_headers({
        "authorization": "Bearer secret",
        "content-length": "42",
        "origin": "https://example.test",
    })
    body = summarize_request_body({"action": "run", "password": "secret"})

    assert "secret" not in str(headers)
    assert "secret" not in str(body)
    assert body == {"action": "run", "bodyKeys": ["action", "password"]}


def test_response_log_summary_counts_collections_without_logging_rows():
    summary = summarize_response({
        "statusCode": 200,
        "body": {
            "receiptDetails": [{"itemName": "private item"}] * 3,
            "registeredCount": 2,
        },
    })

    assert summary == {
        "statusCode": 200,
        "receiptDetailsCount": 3,
        "registeredCount": 2,
    }
