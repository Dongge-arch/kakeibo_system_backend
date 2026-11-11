# -*- coding: utf-8 -*-

"""決済履歴HTMLとGmail金額解析の回帰テスト。"""

from src.batch.kakeibo.auto_input_targets.auto_input_financial.autoInput_Financial import (
    AutoInput_Financial,
)
from src.batch.kakeibo.auto_input_targets.auto_input_gmail.gmailReceiptImporter import (
    GmailReceiptImporter,
)


def financial_parser():
    parser = object.__new__(AutoInput_Financial)
    parser.service = type("Service", (), {"connection_type": "PAYPAY"})()
    return parser


def test_currency_symbol_uses_only_number_on_the_right():
    assert AutoInput_Financial.parse_currency_amount("商品番号 571747 数量 20 ¥1,280") == 1280
    assert GmailReceiptImporter.currency_amount("注文番号 918522 合計 ￥3,480") == 3480


def test_history_parser_does_not_use_quantity_as_amount():
    rows = financial_parser().parse_history_html(
        """<table><tr data-transaction-id='a1'><td>2026/11/11</td>
        <td>セブン-イレブン 商品番号 802479 数量 20</td><td>¥208</td></tr></table>"""
    )
    assert len(rows) == 1
    assert rows[0]["amount"] == 208


def test_gmail_requires_receipt_subject_and_currency_amount():
    body = "ご請求合計 ¥1,500"
    encoded = __import__("base64").urlsafe_b64encode(body.encode()).decode().rstrip("=")
    message = {
        "internalDate": "1794355200000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "ご注文を承りました"},
                {"name": "From", "value": "テストストア <shop@example.com>"},
            ],
            "body": {"data": encoded},
        },
    }
    result = GmailReceiptImporter.parse_message(message)
    assert result is not None
    assert result["amount"] == 1500
    assert result["merchant"] == "テストストア"
