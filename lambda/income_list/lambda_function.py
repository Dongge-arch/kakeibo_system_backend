from src.api.income.income.incomeApi import IncomeApi
import json

def _body(event):
    if isinstance(event.get("body"), str):
        return json.loads(event.get("body") or "{}")
    return event.get("body") or {}

def _set_body(event, body):
    event["body"] = body
    return event

def lambda_handler(event, context):
    body = _body(event)
    query = event.get("queryStringParameters") or {}
    path = event.get("pathParameters") or {}
    body["action"] = "list"
    body["month"] = query.get("month")
    body["dateFrom"] = query.get("dateFrom")
    body["dateTo"] = query.get("dateTo")
    event = _set_body(event, body)
    return IncomeApi().lambda_handler(event, context)
