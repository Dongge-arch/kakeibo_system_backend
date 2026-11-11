# -*- coding: utf-8 -*-

"""出費源と小票の照合条件を確認する。"""

from src.api.kakeibo.expense_source.expenseSourceBase import ExpenseSourceBase


class MatchingOnlyExpenseSource(ExpenseSourceBase):
    def main(self, request_dict):
        return {}


def matcher():
    return object.__new__(MatchingOnlyExpenseSource)


def test_match_score_requires_exact_amount_and_date_window():
    source = {"AMOUNT": 1200, "TRANSACTION_DT": "2026-11-11", "MERCHANT_NAME": "セブンイレブン"}
    same = {"TOA_PRICE": 1200, "RET_DT": "2026-11-09", "SUP_NAME": "セブン-イレブン"}
    wrong_amount = {**same, "TOA_PRICE": 1201}
    too_old = {**same, "RET_DT": "2026-11-07"}
    assert matcher().match_score(source, same) >= 85
    assert matcher().match_score(source, wrong_amount) == 0
    assert matcher().match_score(source, too_old) == 0


def test_candidate_order_prefers_similar_merchant():
    source = {"AMOUNT": -980, "TRANSACTION_DT": "2026-11-11", "MERCHANT_NAME": "ウェルシア薬局"}
    receipts = [
        {"RET_ID": "1", "TOA_PRICE": 980, "RET_DT": "2026-11-11", "SUP_NAME": "別の店"},
        {"RET_ID": "2", "TOA_PRICE": 980, "RET_DT": "2026-11-11", "SUP_NAME": "ウエルシア薬局"},
    ]
    candidates = matcher().candidate_receipts(source, receipts)
    assert candidates[0]["receiptId"] == "2"
