"""入金の更新Lambda。"""

import json

from src.api.kakeibo.income.income_update_delete.incomeUpdateDelete import IncomeUpdateDelete

def lambda_handler(event, context):
    body = json.loads(event.get("body") or "{}") if isinstance(event.get("body"), str) else dict(event.get("body") or {})
    body["action"] = "update"
    body["id"] = (event.get("pathParameters") or {}).get("id") or body.get("id")
    return IncomeUpdateDelete().lambda_handler({**event, "body": body}, context)
