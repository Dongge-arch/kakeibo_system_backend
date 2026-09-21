from src.api.kakeibo.receipt.recurring_expense.update_delete.recurringExpenseUpdateDelete import RecurringExpenseUpdateDelete
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
    body["action"] = "delete"
    body["id"] = path.get("rule_id")
    event = _set_body(event, body)
    return RecurringExpenseUpdateDelete().lambda_handler(event, context)
