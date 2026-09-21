"""入金の参照Lambda。"""

import json

from src.api.kakeibo.income.income_reference.incomeReference import IncomeReference

def lambda_handler(event, context):
    # GETの検索条件をAPIの本文形式に揃える。
    body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else dict(event.get("body") or {})
    query = event.get("queryStringParameters") or {}
    body.update({key: query.get(key) for key in ("month", "dateFrom", "dateTo")})
    return IncomeReference().lambda_handler({**event, "body": body}, context)
