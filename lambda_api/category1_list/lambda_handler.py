from src.api.kakeibo.master.category1.category1Reference import Category1Reference
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
    body["action"] = "list_category1"
    event = _set_body(event, body)
    return Category1Reference().lambda_handler(event, context)
